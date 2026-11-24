"""FastAPI application.

Request flow (see study.md):
    browser -> /api/estimate -> routes -> engine.estimate.calculate
            -> engine.calculators.calc_* -> pricing.store (SQLite) -> Decimal maths -> JSON
"""

from __future__ import annotations

import os
import uuid
from collections import defaultdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .engine import estimate as est
from .engine.rightsizing import find_alternatives
from .engine.calculators import S3_LABELS
from .pricing.ingest import DEFAULT_DB
from .pricing.store import PriceNotFound, PriceStore, connect
from .scenarios import MAX_PER_SESSION, ScenarioRepo
from .schemas import CompareRequest, CompareResult, EstimateResult, SavedScenario, Scenario

SESSION_COOKIE = "ccc_session"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def create_app(price_db: str | Path | None = None, scenario_db: str | Path | None = None, static_dir: str | Path | None = None) -> FastAPI:
    price_db = price_db or os.environ.get("PRICE_DB", DEFAULT_DB)
    scenario_db = scenario_db or os.environ.get("SCENARIO_DB", DATA_DIR / "scenarios.db")
    # Production: one container serves the API *and* the built React app (same origin).
    static_dir = Path(static_dir or os.environ.get("STATIC_DIR", DATA_DIR.parent.parent / "frontend" / "dist"))
    secure_cookie = os.environ.get("COOKIE_SECURE", "") == "1"  # set behind HTTPS
    if not Path(price_db).exists():
        raise FileNotFoundError(
            f"Price database not found at {price_db}. Build it first:\n"
            "    python -m app.pricing.ingest --regions ap-south-1 --download"
        )

    app = FastAPI(title="Cloud Cost Calculator API", version="0.1.0",
                  description="Estimates AWS list-price costs for EC2/EBS, S3 and RDS. Not affiliated with AWS.")
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    app.state.store = PriceStore(connect(price_db))
    app.state.repo = ScenarioRepo(scenario_db)

    def store() -> PriceStore:
        return app.state.store

    def repo() -> ScenarioRepo:
        return app.state.repo

    def session_id(request: Request, response: Response) -> str:
        sid = request.cookies.get(SESSION_COOKIE)
        if not sid or len(sid) != 32:
            sid = uuid.uuid4().hex
            response.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="lax", secure=secure_cookie, max_age=60 * 60 * 24 * 365)
        return sid

    # ------------------------------------------------------------ system --
    @app.get("/api/health")
    def health():
        return {"status": "healthy"}

    @app.get("/api/meta")
    def meta(s: PriceStore = Depends(store)):
        rows = s.meta()
        regions: dict[str, dict] = defaultdict(dict)
        for r in rows:
            regions[r["region"]][r["service"]] = r["publication_date"][:10]
        return {"regions": [{"region": k, "price_list_dates": v} for k, v in sorted(regions.items())]}

    # ----------------------------------------------------------- catalog --
    @app.get("/api/catalog/ec2")
    def catalog_ec2(region: str, s: PriceStore = Depends(store)):
        by_type: dict[str, dict] = {}
        for p in s.products("ec2", region, "ec2_instance"):
            entry = by_type.setdefault(p["instanceType"], {
                "instance_type": p["instanceType"], "family": p.get("instanceFamily"), "vcpu": p.get("vcpu"),
                "memory": p.get("memory"), "network": p.get("networkPerformance"), "storage": p.get("storage"),
                "current_generation": p.get("currentGeneration") == "Yes", "os": [],
            })
            entry["os"].append(p["operatingSystem"])
        if not by_type:
            raise HTTPException(404, f"No EC2 prices loaded for region '{region}'")
        return {"region": region, "instances": sorted(by_type.values(), key=lambda e: e["instance_type"])}

    @app.get("/api/catalog/rds")
    def catalog_rds(region: str, s: PriceStore = Depends(store)):
        engines: dict[tuple, dict] = {}
        instances: dict[str, dict] = {}
        for p in s.products("rds", region, "rds_instance"):
            engine = p["databaseEngine"]
            if engine.startswith("Aurora") or "on-premise" in engine:
                continue  # Aurora bills I/O differently; Outposts is out of scope
            combo = (engine, p.get("databaseEdition") or "", p.get("licenseModel") or "")
            engines[combo] = {"engine": combo[0], "edition": combo[1], "license_model": combo[2]}
            inst = instances.setdefault(p["instanceType"], {
                "instance_type": p["instanceType"], "vcpu": p.get("vcpu"), "memory": p.get("memory"),
                "family": p.get("instanceFamily"), "combos": set(),
            })
            inst["combos"].add("|".join(combo))
        if not instances:
            raise HTTPException(404, f"No RDS prices loaded for region '{region}'")
        for inst in instances.values():
            inst["combos"] = sorted(inst["combos"])
        return {"region": region, "engines": sorted(engines.values(), key=lambda e: (e["engine"], e["edition"], e["license_model"])),
                "instances": sorted(instances.values(), key=lambda e: e["instance_type"])}

    @app.get("/api/ec2/alternatives")
    def ec2_alternatives(region: str, instance_type: str, os: str = "Linux", s: PriceStore = Depends(store)):
        """Cheaper current-generation instances with at least the same vCPU and memory."""
        try:
            base, alts = find_alternatives(s, region, instance_type, os)
        except PriceNotFound as exc:
            raise HTTPException(404, str(exc))
        return {
            "instance_type": instance_type, "hourly": str(base),
            "alternatives": [{"instance_type": a.instance_type, "vcpu": a.vcpu, "memory_gib": str(a.memory_gib),
                              "hourly": str(a.hourly), "saving_pct": str(a.saving_pct), "arm": a.arm} for a in alts],
        }

    @app.get("/api/catalog/dt")
    def catalog_dt(region: str, s: PriceStore = Depends(store)):
        dests = s.products("dt", region, "dt_interregion")
        if not dests:
            raise HTTPException(404, f"No data-transfer prices loaded for region '{region}'")
        out = sorted(({"region": d["to_region"], "name": d["to_name"]} for d in dests), key=lambda d: d["name"])
        return {"region": region, "destinations": out}

    @app.get("/api/catalog/s3")
    def catalog_s3():
        return {"storage_classes": [{"id": k, "label": v} for k, v in S3_LABELS.items()]}

    # ---------------------------------------------------------- estimate --
    @app.post("/api/estimate", response_model=EstimateResult)
    def estimate(scenario: Scenario, s: PriceStore = Depends(store)):
        return est.calculate(scenario, s)

    @app.post("/api/compare", response_model=CompareResult)
    def compare(body: CompareRequest, s: PriceStore = Depends(store)):
        return est.compare(body.scenarios, s)

    # --------------------------------------------------- saved scenarios --
    @app.get("/api/scenarios", response_model=list[SavedScenario])
    def list_scenarios(sid: str = Depends(session_id), r: ScenarioRepo = Depends(repo)):
        return r.list(sid)

    @app.post("/api/scenarios", response_model=SavedScenario, status_code=201)
    def create_scenario(scenario: Scenario, sid: str = Depends(session_id), r: ScenarioRepo = Depends(repo)):
        if r.count(sid) >= MAX_PER_SESSION:
            raise HTTPException(409, f"Limit of {MAX_PER_SESSION} saved scenarios reached")
        return r.create(sid, scenario)

    @app.get("/api/scenarios/{scenario_id}", response_model=SavedScenario)
    def get_scenario(scenario_id: str, sid: str = Depends(session_id), r: ScenarioRepo = Depends(repo)):
        found = r.get(sid, scenario_id)
        if not found:
            raise HTTPException(404, "Scenario not found")
        return found

    @app.put("/api/scenarios/{scenario_id}", response_model=SavedScenario)
    def update_scenario(scenario_id: str, scenario: Scenario, sid: str = Depends(session_id), r: ScenarioRepo = Depends(repo)):
        found = r.update(sid, scenario_id, scenario)
        if not found:
            raise HTTPException(404, "Scenario not found")
        return found

    @app.delete("/api/scenarios/{scenario_id}", status_code=204)
    def delete_scenario(scenario_id: str, sid: str = Depends(session_id), r: ScenarioRepo = Depends(repo)):
        if not r.delete(sid, scenario_id):
            raise HTTPException(404, "Scenario not found")

    # Mounted LAST so every /api/... route above wins; "/" then serves index.html.
    if (static_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="ui")

    return app

