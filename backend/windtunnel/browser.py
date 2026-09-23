"""Browser front end for the wind tunnel service: runs inside Pyodide in a Web Worker (the static build).

The worker calls these functions with JSON strings and gets JSON strings back — plain text crosses the JS/Python
boundary cheaply and predictably. Each call also returns the messages the service emitted meanwhile (frames, status,
forked, batch), which the worker forwards to the page exactly as the server's WebSocket would.

The Apple model and Laya can't run in a browser, so this build is rules-only; everything else is the same code as the
local server.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from .service import Service

_events: list[dict[str, Any]] = []
_svc: Optional[Service] = None


def init(store_path: str, max_batch: int = 1000) -> str:
    global _svc
    _svc = Service(emit=_events.append, store_path=store_path, use_fm=False, allow_model_engines=False, max_batch=max_batch)
    _svc.ensure_experiment()
    return _reply({"ok": True})


def request(method: str, path: str, query_json: str, body_json: str) -> str:
    status, body = _svc.dispatch(method, path, json.loads(query_json or "{}"), json.loads(body_json or "null"))
    return _reply({"status": status, "body": body})


def tick() -> str:
    return _reply({"wait": _svc.tick()})


def batch_prepare(body_json: str) -> str:
    b = json.loads(body_json or "{}")
    try:
        prep = _svc.batch_prepare(b.get("plan"), b.get("text"), b.get("n", 24), b.get("months", 36), b.get("engine", "heuristic"), b.get("seed0", 1000))
    except Exception as exc:          # ServiceError or anything else: report it like the server would
        return _reply({"status": getattr(exc, "status", 500), "body": {"detail": getattr(exc, "detail", repr(exc))}})
    return _reply({"status": 200, "body": {"job_id": prep["job"]["id"], "args": prep["args"]}})


def batch_progress(job_id: str, done: int) -> str:
    _svc.batch_progress(job_id, int(done))
    return _reply({})


def batch_finish(job_id: str, results_json: str, error: str, elapsed_s: float) -> str:
    _svc.batch_finish(job_id, results=json.loads(results_json or "[]"), error=error or None, elapsed_s=float(elapsed_s))
    return _reply({})


def run_one(args_json: str) -> str:
    """Batch worker entry point: one baseline/intervention world pair, no rendering."""
    from . import batch
    return json.dumps(batch.run_one(json.loads(args_json)))


def _reply(payload: dict[str, Any]) -> str:
    out = json.dumps({**payload, "events": list(_events)}, default=str)
    _events.clear()
    return out
