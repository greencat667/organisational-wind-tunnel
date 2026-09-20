"""SQLite persistence for experiments, runs, snapshots, events, metrics and decisions. Local file only."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Optional

DEFAULT_PATH = os.environ.get("WINDTUNNEL_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "windtunnel.sqlite"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, created REAL, name TEXT, template TEXT, seed INTEGER, engine TEXT,
    intervention_text TEXT, plan_json TEXT, config_json TEXT, months INTEGER, notes TEXT, fork_month INTEGER);
CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, experiment_id TEXT, label TEXT, seed INTEGER, engine TEXT, months INTEGER,
    created REAL, model_versions TEXT, final_metrics_json TEXT);
CREATE TABLE IF NOT EXISTS metrics (run_id TEXT, month INTEGER, json TEXT, PRIMARY KEY (run_id, month));
CREATE TABLE IF NOT EXISTS events (run_id TEXT, event_id INTEGER, month INTEGER, kind TEXT, significant INTEGER, json TEXT, PRIMARY KEY (run_id, event_id));
CREATE TABLE IF NOT EXISTS decisions (run_id TEXT, seq INTEGER, month INTEGER, agent_id TEXT, engine TEXT, action TEXT, json TEXT, PRIMARY KEY (run_id, seq));
CREATE TABLE IF NOT EXISTS snapshots (run_id TEXT, month INTEGER, json TEXT, PRIMARY KEY (run_id, month));
CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, created REAL, experiment_id TEXT, n INTEGER, engine TEXT, months INTEGER, summary_json TEXT);
CREATE TABLE IF NOT EXISTS batch_runs (batch_id TEXT, seed INTEGER, label TEXT, final_json TEXT, PRIMARY KEY (batch_id, seed, label));
"""


class Store:
    def __init__(self, path: str = DEFAULT_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(experiments)").fetchall()]
        if "fork_month" not in cols:
            self.conn.execute("ALTER TABLE experiments ADD COLUMN fork_month INTEGER")
            self.conn.commit()

    # ------------------------------------------------------------- experiments
    def save_experiment(self, exp: dict[str, Any]) -> None:
        self.conn.execute("INSERT OR REPLACE INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          (exp["id"], exp.get("created", time.time()), exp.get("name", ""), exp["template"], exp["seed"], exp["engine"],
                           exp.get("intervention_text", ""), json.dumps(exp.get("plan")), json.dumps(exp.get("config", {})), exp.get("months", 0), exp.get("notes", ""),
                           exp.get("fork_month")))
        self.conn.commit()

    def list_experiments(self) -> list[dict[str, Any]]:
        cur = self.conn.execute("SELECT id, created, name, template, seed, engine, intervention_text, months, fork_month FROM experiments ORDER BY created DESC")
        return [dict(zip(("id", "created", "name", "template", "seed", "engine", "intervention_text", "months", "fork_month"), r)) for r in cur.fetchall()]

    def load_experiment(self, exp_id: str) -> Optional[dict[str, Any]]:
        r = self.conn.execute("SELECT * FROM experiments WHERE id=?", (exp_id,)).fetchone()
        if not r:
            return None
        keys = ("id", "created", "name", "template", "seed", "engine", "intervention_text", "plan_json", "config_json", "months", "notes", "fork_month")
        d = dict(zip(keys, r))
        d["plan"] = json.loads(d.pop("plan_json") or "null")
        d["config"] = json.loads(d.pop("config_json") or "{}")
        return d

    # -------------------------------------------------------------------- runs
    def save_run(self, world, experiment_id: str, run_id: str, model_versions: dict[str, Any]) -> None:
        c = self.conn
        c.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?)",
                  (run_id, experiment_id, world.label, world.seed, getattr(world.decision_engine, "name", "?"), world.month, time.time(),
                   json.dumps(model_versions), json.dumps(world.metrics_history[-1] if world.metrics_history else {})))
        c.executemany("INSERT OR REPLACE INTO metrics VALUES (?,?,?)", [(run_id, m["month"], json.dumps(m)) for m in world.metrics_history])
        from .model import to_dict
        c.executemany("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?)",
                      [(run_id, e.id, e.month, e.kind, int(e.significant), json.dumps(to_dict(e))) for e in world.events])
        c.executemany("INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?,?)",
                      [(run_id, i, d["month"], d["agent_id"], d["engine"], d["action"], json.dumps(d)) for i, d in enumerate(world.decision_log)])
        c.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?)", (run_id, world.month, json.dumps(world.export_state())))
        c.commit()

    def load_run_metrics(self, run_id: str) -> list[dict[str, Any]]:
        cur = self.conn.execute("SELECT json FROM metrics WHERE run_id=? ORDER BY month", (run_id,))
        return [json.loads(r[0]) for r in cur.fetchall()]

    def load_run_events(self, run_id: str, significant_only: bool = False) -> list[dict[str, Any]]:
        q = "SELECT json FROM events WHERE run_id=?" + (" AND significant=1" if significant_only else "") + " ORDER BY event_id"
        return [json.loads(r[0]) for r in self.conn.execute(q, (run_id,)).fetchall()]

    def load_run_decisions(self, run_id: str) -> list[dict[str, Any]]:
        return [json.loads(r[0]) for r in self.conn.execute("SELECT json FROM decisions WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()]

    def list_runs(self, experiment_id: Optional[str] = None) -> list[dict[str, Any]]:
        q = "SELECT id, experiment_id, label, seed, engine, months, created FROM runs" + (" WHERE experiment_id=?" if experiment_id else "") + " ORDER BY created DESC"
        cur = self.conn.execute(q, (experiment_id,) if experiment_id else ())
        return [dict(zip(("id", "experiment_id", "label", "seed", "engine", "months", "created"), r)) for r in cur.fetchall()]

    # ------------------------------------------------------------------ batches
    def save_batch(self, batch_id: str, experiment_id: str, n: int, engine: str, months: int, summary: dict[str, Any], rows: list[tuple[int, str, dict]]) -> None:
        self.conn.execute("INSERT OR REPLACE INTO batches VALUES (?,?,?,?,?,?,?)", (batch_id, time.time(), experiment_id, n, engine, months, json.dumps(summary)))
        self.conn.executemany("INSERT OR REPLACE INTO batch_runs VALUES (?,?,?,?)", [(batch_id, seed, label, json.dumps(final)) for seed, label, final in rows])
        self.conn.commit()

    def list_batches(self) -> list[dict[str, Any]]:
        cur = self.conn.execute("SELECT id, created, experiment_id, n, engine, months, summary_json FROM batches ORDER BY created DESC")
        out = []
        for r in cur.fetchall():
            d = dict(zip(("id", "created", "experiment_id", "n", "engine", "months"), r[:6]))
            d["summary"] = json.loads(r[6])
            out.append(d)
        return out

    def load_batch(self, batch_id: str) -> Optional[dict[str, Any]]:
        r = self.conn.execute("SELECT id, created, experiment_id, n, engine, months, summary_json FROM batches WHERE id=?", (batch_id,)).fetchone()
        if not r:
            return None
        d = dict(zip(("id", "created", "experiment_id", "n", "engine", "months"), r[:6]))
        d["summary"] = json.loads(r[6])
        d["runs"] = [{"seed": s, "label": l, "final": json.loads(f)} for s, l, f in self.conn.execute("SELECT seed, label, final_json FROM batch_runs WHERE batch_id=?", (batch_id,)).fetchall()]
        return d
