# CostGoblin: AWS cost estimates from the public price list

Estimate monthly/yearly AWS costs for **EC2 (+EBS), S3, RDS and data transfer**, compare scenarios side by side, and save them. Prices come from AWS's public price-list files, so **no AWS account or credentials are needed**.

> Independent learning project. Not affiliated with, endorsed by or sponsored by Amazon Web Services. Estimates use list prices and are not a bill.

The pricing maths was modelled on how AWS's own calculator works (studied from the files it serves to browsers: 730-hour months, decimal arithmetic, graduated tiers, the EBS snapshot formula); see `docs/recon-tools/` for the scripts used.

## Quick start

```powershell
cd backend
python -m venv .venv ; .venv\Scripts\activate
pip install -r requirements.txt
python -m app.pricing.ingest --regions ap-south-1 --download     # builds data/prices.db (big download, once)
python -m uvicorn app.main:create_app --factory --port 8000

cd ..\frontend            # second terminal; open it at a path with an UPPERCASE drive letter: Vitest breaks on lowercase `e:\` paths on Windows
npm install ; npm run dev                                         # http://localhost:5173
```

One process, production style: `npm run build` in `frontend/`, then run the uvicorn command above and open http://127.0.0.1:8000 (the API serves the built UI).
AWS: [deploy/aws/](deploy/aws/) (one EC2 instance + HTTPS, about $14/month, untested). Render: `render.yaml`.
Docker: `docker compose up --build` (needs a built `backend/data/prices.db`; see Dockerfile).

Tests: `python -m pytest -q` (backend, 103) · `npm test` (frontend, 16) · CI in `.github/workflows/ci.yml`.

## What it prices

| Service | Covered |
|---|---|
| EC2 | On-Demand (with utilisation), Reserved (Standard/Convertible, 1/3 yr, 3 payment options), **Savings Plans (Compute / EC2 Instance)**, "find cheaper alternatives" |
| EBS | gp3, gp2, io1, io2 (tiered IOPS), st1, sc1, snapshots |
| S3 | tiered storage, requests, retrieval (Standard, Standard-IA, One Zone-IA, Glacier IR) |
| RDS | Single/Multi-AZ instances, storage, provisioned IOPS, Reserved |
| Data transfer | internet egress tiers + free 100 GB, inter-region, cross-AZ |

Plus: multi-item scenarios, side-by-side comparison on effective monthly cost, saved scenarios (anonymous per-browser session), a "Show calculation" view on every line.

## Layout

```
backend/   FastAPI + Decimal engine + SQLite price store + offline ingest
frontend/  React + TypeScript + Tailwind + Vite
docs/      helper scripts used to study the AWS calculator
Dockerfile, compose.yaml, .github/workflows/   delivery
deploy/aws/ EC2 deployment guide
```

## Status

Everything above works and is tested (103 backend + 16 frontend tests; CI is green; the `build-image` workflow built and published the Docker image, which also proves the Dockerfile builds).

Not verified:
- Totals have not been compared against calculator.aws's own UI. The EBS and transfer formulas are checked against AWS's *published* pricing examples (`backend/tests/test_aws_published_examples.py`); Savings Plans, RDS Multi-AZ and S3 tiering rest on hand calculations against the price files.
- Nobody has run the container on a real host yet; `render.yaml` and `deploy/aws/` are untested.
- Assumptions beyond the price files (Savings Plan partial upfront = 50 %, cross-AZ billed twice, free 100 GB applied before tiers, gp3/io2 constants) are marked in `backend/app/engine/calculators.py`.
