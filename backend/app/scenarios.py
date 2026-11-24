"""Saved scenarios (SQLite). Each browser gets an anonymous session id (cookie);
a session only ever sees its own rows. No login, as decided in the plan."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .schemas import SavedScenario, Scenario

DDL = """
CREATE TABLE IF NOT EXISTS scenario (
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    name       TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scenario_session ON scenario (session_id, updated_at);
"""

MAX_PER_SESSION = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ScenarioRepo:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(DDL)

    @staticmethod
    def _row(r: sqlite3.Row) -> SavedScenario:
        return SavedScenario(
            id=r["id"], name=r["name"], scenario=Scenario.model_validate_json(r["body"]),
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    def list(self, session_id: str) -> list[SavedScenario]:
        rows = self.conn.execute(
            "SELECT * FROM scenario WHERE session_id = ? ORDER BY updated_at DESC", (session_id,)
        ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, session_id: str, scenario_id: str) -> SavedScenario | None:
        r = self.conn.execute(
            "SELECT * FROM scenario WHERE id = ? AND session_id = ?", (scenario_id, session_id)
        ).fetchone()
        return self._row(r) if r else None

    def count(self, session_id: str) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM scenario WHERE session_id = ?", (session_id,)).fetchone()[0]

    def create(self, session_id: str, scenario: Scenario) -> SavedScenario:
        sid, now = uuid.uuid4().hex, _now()
        self.conn.execute(
            "INSERT INTO scenario (id, session_id, name, body, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (sid, session_id, scenario.name, scenario.model_dump_json(), now, now),
        )
        self.conn.commit()
        return self.get(session_id, sid)  # type: ignore[return-value]

    def update(self, session_id: str, scenario_id: str, scenario: Scenario) -> SavedScenario | None:
        cur = self.conn.execute(
            "UPDATE scenario SET name = ?, body = ?, updated_at = ? WHERE id = ? AND session_id = ?",
            (scenario.name, scenario.model_dump_json(), _now(), scenario_id, session_id),
        )
        self.conn.commit()
        return self.get(session_id, scenario_id) if cur.rowcount else None

    def delete(self, session_id: str, scenario_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM scenario WHERE id = ? AND session_id = ?", (scenario_id, session_id))
        self.conn.commit()
        return cur.rowcount > 0
