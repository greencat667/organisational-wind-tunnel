"""FastAPI + WebSocket server. Owns the live experiment (baseline + intervention worlds), streams frames,
serves inspectors, analysis, batch runs and persistence. Everything runs on localhost."""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from typing import Any, Optional


from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from . import analysis, batch
from .config import SimConfig
from .decisions import CachedDecisionEngine, make_engine
from .engine import World
from .interventions.parser import InterventionParser
from .interventions.primitives import describe_plan, schedule_plan
from .interventions.schema import ChangePlan, validate_plan
from .model import to_dict
from .store import Store

app = FastAPI(title="Organisational Wind Tunnel", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SCENARIOS = [
    {"id": "admin_cut", "name": "Admin cut", "text": "Reduce administrative capacity by 20% while maintaining existing frontline delivery."},
    {"id": "ai_automation", "name": "AI automation", "text": "Automate 40% of routine finance and operations work over 18 months."},
    {"id": "flatten", "name": "Flatten structure", "text": "Remove one management layer and increase team autonomy."},
    {"id": "funding_shock", "name": "Funding shock", "text": "Organisation income falls 15% next year."},
    {"id": "rapid_growth", "name": "Rapid growth", "text": "Demand for services doubles over two years."},
    {"id": "ai_agents", "name": "AI agent teams", "text": "Deploy AI agents to handle 60% of back-office work over 12 months, with admin staff becoming supervisors of agent teams."},
    {"id": "merge", "name": "Merge teams", "text": "Merge the fundraising and communications teams."},
]


class Experiment:
    """Holds one baseline world and (optionally) one intervention world, stepping them in lock-step."""

    def __init__(self, template: str, seed: int, engine_name: str, months_settle: int = 3, scale: float = 1.0):
        self.id = uuid.uuid4().hex[:10]
        self.template = template
        self.seed = seed
        self.engine_name = engine_name
        self.engine = self._make_engine(engine_name)
        cfg = SimConfig()
        if engine_name in ("laya", "needle"):
            cfg.max_decisions_per_month = int(os.environ.get("WINDTUNNEL_AI_DECISIONS_PER_MONTH", "24"))   # keep AI engines interactive
        self.baseline = World(template, seed, "baseline", decision_engine=self.engine, config=cfg, scale=scale)
        self.intervention: Optional[World] = None
        self.plan: Optional[ChangePlan] = None
        self.intervention_text = ""
        self.fork_month: Optional[int] = None
        self.lock = threading.Lock()
        self.playing = False
        self.speed = 1.0            # months per second
        self.target_month: Optional[int] = None
        self.created = time.time()
        self.step_times: list[float] = []
        for _ in range(months_settle):
            self.baseline.step()

    def _make_engine(self, name: str):
        try:
            eng = make_engine(name)
            self.engine_error = None
        except Exception as exc:
            eng = make_engine("heuristic")
            self.engine_error = f"{name}: {exc!r}"[:200]
        return CachedDecisionEngine(eng) if name in ("laya", "needle") else eng

    def worlds(self) -> list[World]:
        return [w for w in (self.baseline, self.intervention) if w is not None]

    def step(self) -> dict[str, Any]:
        with self.lock:
            t0 = time.perf_counter()
            out = {"month": None}
            for w in self.worlds():
                r = w.step()
                out[w.label] = {"frame": r["frame"], "metrics": r["metrics"], "timing": r["timing"]}
                out["month"] = r["month"]
                out["label"] = r["label"]
            self.step_times.append(time.perf_counter() - t0)
            self.step_times = self.step_times[-60:]
            return out

    def fork(self, plan: ChangePlan, text: str) -> None:
        with self.lock:
            self.intervention = self.baseline.fork("intervention")
            self.plan = plan
            self.intervention_text = text
            self.fork_month = self.baseline.month
            schedule_plan(self.intervention, plan)

    def discard_intervention(self) -> None:
        with self.lock:
            self.intervention = None
            self.plan = None
            self.fork_month = None

    def status(self) -> dict[str, Any]:
        eng = self.engine
        return {"id": self.id, "template": self.template, "seed": self.seed, "engine": self.engine_name, "engine_info": eng.describe(),
                "engine_stats": eng.stats(), "engine_error": getattr(self, "engine_error", None), "month": self.baseline.month,
                "label": self.baseline.date_label(), "forked": self.intervention is not None, "fork_month": self.fork_month,
                "plan": self.plan.model_dump() if self.plan else None, "intervention_text": self.intervention_text,
                "playing": self.playing, "speed": self.speed, "headcount": len([e for e in self.baseline.employees.values() if e.status == "active"]),
                "mean_step_ms": round(1000 * sum(self.step_times) / len(self.step_times), 1) if self.step_times else None}


class Hub:
    def __init__(self):
        self.experiment: Optional[Experiment] = None
        self.clients: set[WebSocket] = set()
        self.parser = InterventionParser()
        self.store = Store()
        self.batch_jobs: dict[str, dict[str, Any]] = {}
        self.loop_task: Optional[asyncio.Task] = None

    async def broadcast(self, msg: dict[str, Any]) -> None:
        dead = []
        data = json.dumps(msg)
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    def ensure_experiment(self) -> Experiment:
        if self.experiment is None:
            self.experiment = Experiment(os.environ.get("WINDTUNNEL_TEMPLATE", "prototype"), int(os.environ.get("WINDTUNNEL_SEED", "7")),
                                         os.environ.get("WINDTUNNEL_ENGINE", "heuristic"))
        return self.experiment

    async def play_loop(self) -> None:
        while True:
            exp = self.experiment
            if exp is None or not exp.playing:
                await asyncio.sleep(0.05)
                continue
            if exp.target_month is not None and exp.baseline.month >= exp.target_month:
                exp.playing = False
                exp.target_month = None
                await self.broadcast({"type": "status", "status": exp.status()})
                continue
            t0 = time.perf_counter()
            out = await asyncio.to_thread(exp.step)
            await self.broadcast({"type": "frame", **out})
            dt = time.perf_counter() - t0
            wait = max(0.0, (1.0 / exp.speed) - dt) if exp.speed < 1000 else 0.0
            await asyncio.sleep(wait)


hub = Hub()


@app.on_event("startup")
async def _startup():
    hub.loop_task = asyncio.create_task(hub.play_loop())


# ------------------------------------------------------------------------------------- models
class NewExperiment(BaseModel):
    template: str = "prototype"
    seed: int = 7
    engine: str = "heuristic"
    settle_months: int = 3
    scale: float = 1.0


class InterpretRequest(BaseModel):
    text: str


class RunRequest(BaseModel):
    plan: dict[str, Any]
    text: str = ""


class PlayRequest(BaseModel):
    playing: Optional[bool] = None
    speed: Optional[float] = None
    steps: Optional[int] = None
    until_month: Optional[int] = None


class BatchRequest(BaseModel):
    plan: Optional[dict[str, Any]] = None
    text: Optional[str] = None
    n: int = 100
    months: int = 36
    engine: str = "heuristic"
    seed0: int = 1000


class ExplainRequest(BaseModel):
    prompt: str


# ------------------------------------------------------------------------------------- routes
@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version}


@app.get("/api/scenarios")
def scenarios():
    return SCENARIOS


@app.get("/api/experiment")
def get_experiment():
    exp = hub.ensure_experiment()
    return {"status": exp.status(), "structure": exp.baseline.structure(),
            "frames": {w.label: w.frames for w in exp.worlds()},
            "metrics": {w.label: w.metrics_history for w in exp.worlds()},
            "events": {w.label: [to_dict(e) for e in w.events if e.significant] for w in exp.worlds()}}


@app.post("/api/experiment")
def new_experiment(req: NewExperiment):
    if hub.experiment:
        hub.experiment.playing = False
    hub.experiment = Experiment(req.template, req.seed, req.engine, req.settle_months, req.scale)
    return get_experiment()


@app.post("/api/interpret")
def interpret(req: InterpretRequest):
    exp = hub.ensure_experiment()
    hint = ", ".join(t.name for t in exp.baseline.teams.values())
    t0 = time.perf_counter()
    plan = hub.parser.parse(req.text, org_hint=hint)
    return {"plan": plan.model_dump(), "source": hub.parser.last_source, "error": hub.parser.last_error,
            "latency_ms": round((time.perf_counter() - t0) * 1000), "interpreted": describe_plan(exp.baseline, plan),
            "raw": hub.parser.last_raw if hub.parser.last_source == "apple_fm" else None}


@app.post("/api/run")
async def run(req: RunRequest):
    exp = hub.ensure_experiment()
    try:
        plan = validate_plan(req.plan)
    except Exception as exc:
        raise HTTPException(400, f"invalid plan: {exc}")
    exp.fork(plan, req.text)
    hub.store.save_experiment({"id": exp.id, "template": exp.template, "seed": exp.seed, "engine": exp.engine_name, "intervention_text": req.text,
                               "plan": plan.model_dump(), "config": exp.baseline.config.to_dict(), "months": exp.baseline.month, "name": req.text[:60]})
    await hub.broadcast({"type": "forked", "status": exp.status(), "structure": exp.intervention.structure(),
                         "frame": exp.intervention.frames[-1] if exp.intervention.frames else None})
    return {"status": exp.status(), "interpreted": describe_plan(exp.baseline, plan)}


@app.post("/api/discard")
async def discard():
    exp = hub.ensure_experiment()
    exp.discard_intervention()
    await hub.broadcast({"type": "status", "status": exp.status()})
    return exp.status()


@app.post("/api/play")
async def play(req: PlayRequest):
    exp = hub.ensure_experiment()
    if req.speed is not None:
        exp.speed = max(0.1, req.speed)
    if req.steps:
        exp.playing = False
        for _ in range(req.steps):
            out = await asyncio.to_thread(exp.step)
            await hub.broadcast({"type": "frame", **out})
    if req.until_month is not None:
        exp.target_month = req.until_month
        exp.playing = True
    if req.playing is not None:
        exp.playing = req.playing
    await hub.broadcast({"type": "status", "status": exp.status()})
    return exp.status()


@app.get("/api/employee/{world}/{eid}")
def employee(world: str, eid: str):
    exp = hub.ensure_experiment()
    w = _world(exp, world)
    if eid not in w.employees:
        raise HTTPException(404)
    return w.employee_detail(eid)


@app.get("/api/team/{world}/{tid}")
def team(world: str, tid: str):
    exp = hub.ensure_experiment()
    w = _world(exp, world)
    if tid not in w.teams:
        raise HTTPException(404)
    return w.team_detail(tid)


@app.get("/api/events/{world}")
def events(world: str, significant: bool = True, since: int = 0):
    w = _world(hub.ensure_experiment(), world)
    return [to_dict(e) for e in w.events if (e.significant or not significant) and e.month >= since]


@app.get("/api/why/{world}/{event_id}")
def why(world: str, event_id: int):
    w = _world(hub.ensure_experiment(), world)
    res = analysis.why(w.events, event_id)
    for n in res["nodes"]:
        n["date"] = w.date_label(n["month"])
    for c in res["chain"]:
        c["date"] = w.date_label(c["month"])
    return res


@app.get("/api/effects")
def effects(min_effect: float = 0.5):
    exp = hub.ensure_experiment()
    if not exp.intervention:
        return {"effects": [], "emergence": [], "note": "no intervention running"}
    rep = analysis.classify_effects(exp.intervention, exp.baseline, min_effect)
    rep["emergence"] = analysis.detect_emergence(exp.intervention, exp.baseline)
    rep["divergence_by_team"] = _team_divergence(exp)
    return rep


@app.get("/api/network/{world}")
def network(world: str):
    w = _world(hub.ensure_experiment(), world)
    return {"informal": analysis.informal_network(w), "formal": analysis.formal_network(w)}


@app.get("/api/decisions/{world}")
def decisions(world: str, agent: Optional[str] = None, last: int = 200):
    w = _world(hub.ensure_experiment(), world)
    log = [d for d in w.decision_log if agent is None or d["agent_id"] == agent]
    return log[-last:]


@app.get("/api/diagnostics")
def diagnostics():
    exp = hub.ensure_experiment()
    import resource
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    return {"status": exp.status(), "timing": {w.label: w.timing for w in exp.worlds()}, "engine": exp.engine.describe(), "engine_stats": exp.engine.stats(),
            "apple_fm": {"available": hub.parser.fm.available, "healthy": hub.parser.fm.healthy(), "calls": hub.parser.fm.calls, "failures": hub.parser.fm.failures,
                         "last_latency_ms": round(hub.parser.fm.last_latency_ms), "last_source": hub.parser.last_source, "last_error": hub.parser.last_error},
            "memory_mb": round(rss_mb), "active_work_items": {w.label: sum(len(t.queue) for t in w.teams.values()) for w in exp.worlds()},
            "active_agents": {w.label: len([e for e in w.employees.values() if e.status == "active"]) for w in exp.worlds()},
            "decisions_total": {w.label: len(w.decision_log) for w in exp.worlds()}, "clients": len(hub.clients)}


@app.post("/api/explain")
def explain(req: ExplainRequest):
    text = hub.parser.explain(req.prompt)
    return {"text": text, "source": "apple_fm" if text else "none", "error": hub.parser.last_error}


@app.post("/api/save")
def save():
    exp = hub.ensure_experiment()
    versions = {"engine": exp.engine.describe(), "windtunnel": app.version}
    ids = {}
    hub.store.save_experiment({"id": exp.id, "template": exp.template, "seed": exp.seed, "engine": exp.engine_name, "intervention_text": exp.intervention_text,
                               "plan": exp.plan.model_dump() if exp.plan else None, "config": exp.baseline.config.to_dict(), "months": exp.baseline.month, "name": exp.intervention_text[:60] or "baseline"})
    for w in exp.worlds():
        rid = f"{exp.id}-{w.label}"
        hub.store.save_run(w, exp.id, rid, versions)
        ids[w.label] = rid
    return {"experiment_id": exp.id, "runs": ids}


@app.get("/api/experiments")
def list_experiments():
    return {"experiments": hub.store.list_experiments(), "runs": hub.store.list_runs(), "batches": hub.store.list_batches()}


@app.get("/api/export/{world}/{what}")
def export(world: str, what: str, fmt: str = "json"):
    w = _world(hub.ensure_experiment(), world)
    if what == "metrics":
        rows = w.metrics_history
    elif what == "events":
        rows = [to_dict(e) for e in w.events]
    elif what == "decisions":
        rows = w.decision_log
    elif what == "employees":
        rows = [to_dict(e) for e in w.employees.values()]
    elif what == "teams":
        rows = [to_dict(t) for t in w.teams.values()]
    elif what == "queues":
        rows = [{"team": t.id, "item": i, **{k: v for k, v in to_dict(w.work_items[i]).items() if k != "path"}} for t in w.teams.values() for i in t.queue if i in w.work_items]
    else:
        raise HTTPException(404)
    if fmt == "csv":
        return PlainTextResponse(_csv(rows), media_type="text/csv")
    return JSONResponse(rows)


@app.post("/api/batch")
async def start_batch(req: BatchRequest):
    exp = hub.ensure_experiment()
    if req.plan:
        plan = validate_plan(req.plan)
    elif exp.plan:
        plan = exp.plan
    elif req.text:
        plan = hub.parser.parse(req.text)
    else:
        raise HTTPException(400, "no plan")
    job_id = uuid.uuid4().hex[:8]
    job = {"id": job_id, "done": 0, "n": req.n, "status": "running", "result": None, "started": time.time(), "plan": plan.model_dump()}
    hub.batch_jobs[job_id] = job

    def progress(i, n):
        job["done"] = i

    async def runner():
        try:
            res = await asyncio.to_thread(batch.run_batch, exp.template, plan, req.n, req.months, 3, req.engine, req.seed0, None, 1.0, None, progress)
            job["result"] = {k: v for k, v in res.items() if k != "runs"}
            job["result"]["runs"] = [{k: r[k] for k in ("seed", "base", "int", "effects", "emergence")} for r in res["runs"]]
            job["result"]["histories"] = [{"seed": r["seed"], "base": r["base_hist"], "int": r["int_hist"]} for r in res["runs"][:200]]
            job["status"] = "done"
            hub.store.save_batch(job_id, exp.id, req.n, req.engine, req.months, res["summary"], [(r["seed"], "intervention", r["int"]) for r in res["runs"]] + [(r["seed"], "baseline", r["base"]) for r in res["runs"]])
        except Exception as exc:
            job["status"] = "error"
            job["error"] = repr(exc)[:300]
        await hub.broadcast({"type": "batch", "job": {k: v for k, v in job.items() if k != "result"}})

    asyncio.create_task(runner())
    return {"job_id": job_id}


@app.get("/api/batch/{job_id}")
def get_batch(job_id: str):
    job = hub.batch_jobs.get(job_id)
    if not job:
        b = hub.store.load_batch(job_id)
        if not b:
            raise HTTPException(404)
        return {"id": job_id, "status": "done", "result": {"summary": b["summary"], "runs": b["runs"]}}
    return job


# --------------------------------------------------------------------------------- websocket
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    hub.clients.add(websocket)
    exp = hub.ensure_experiment()
    try:
        await websocket.send_text(json.dumps({"type": "hello", "status": exp.status()}))
        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                continue
            if data.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "t": time.time()}))
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(websocket)


# ------------------------------------------------------------------------------------ helpers
def _world(exp: Experiment, label: str) -> World:
    if label == "baseline":
        return exp.baseline
    if label == "intervention" and exp.intervention:
        return exp.intervention
    raise HTTPException(404, f"no world {label}")


def _team_divergence(exp: Experiment) -> dict[str, float]:
    b = exp.baseline.metrics_history[-1]["teams"]
    x = exp.intervention.metrics_history[-1]["teams"]
    out = {}
    for tid in x:
        if tid in b:
            out[tid] = round(abs(x[tid]["backlog_months"] - b[tid]["backlog_months"]) * 2 + abs(x[tid]["workload"] - b[tid]["workload"])
                             + 0.3 * abs(x[tid]["headcount"] - b[tid]["headcount"]) + abs(x[tid]["management_load"] - b[tid]["management_load"]), 3)
    return out


def _csv(rows: list[dict]) -> str:
    import csv
    import io
    if not rows:
        return ""
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys and not isinstance(r[k], (dict, list)):
                keys.append(k)
    buf = io.StringIO()
    wri = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    wri.writeheader()
    for r in rows:
        wri.writerow({k: r.get(k) for k in keys})
    return buf.getvalue()
