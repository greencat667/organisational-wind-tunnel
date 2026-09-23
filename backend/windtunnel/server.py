"""FastAPI + WebSocket front end for the wind tunnel service (localhost). All behaviour lives in ``service.py``; this
module only translates HTTP/WebSocket to service calls and broadcasts the service's messages to connected clients.
The browser build uses the same service through ``browser.py`` instead."""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from .service import SCENARIOS, VERSION, Experiment, Service, ServiceError  # noqa: F401  (re-exported for scripts/tests)

app = FastAPI(title="Organisational Wind Tunnel", version=VERSION)
# Only the local UI may call the API from a browser. A wildcard here let any web page open in the same browser drive
# the simulator (and read its data) through the user's localhost.
_UI_PORT = os.environ.get("WINDTUNNEL_UI_PORT", "5180")
ALLOWED_ORIGINS = [f"http://127.0.0.1:{_UI_PORT}", f"http://localhost:{_UI_PORT}"]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"])


class Hub:
    """Connected WebSocket clients, plus the bridge from the service's (synchronous, possibly off-loop) emits to them."""

    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        # WINDTUNNEL_APPLE_FM=0 skips the Apple model entirely (rules only) — useful when `fm` is installed but slow or wedged
        self.service = Service(emit=self.emit, use_fm=os.environ.get("WINDTUNNEL_APPLE_FM", "1") != "0")
        self.service.client_count = lambda: len(self.clients)

    def emit(self, msg: dict[str, Any]) -> None:
        """Called by the service, from the event loop or from a worker thread."""
        if self.loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            self.loop.create_task(self.broadcast(msg))
        else:
            asyncio.run_coroutine_threadsafe(self.broadcast(msg), self.loop).result(timeout=30)

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

    async def play_loop(self) -> None:
        while True:
            wait = await asyncio.to_thread(self.service.tick)
            await asyncio.sleep(wait)


hub = Hub()
svc = hub.service


@app.on_event("startup")
async def _startup():
    hub.loop = asyncio.get_running_loop()
    asyncio.create_task(hub.play_loop())


def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ServiceError as exc:
        raise HTTPException(exc.status, exc.detail)


async def call_off_loop(fn, *args, **kwargs):
    """Service calls that step the simulation or emit run in a thread, so emits can hop back onto the loop."""
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except ServiceError as exc:
        raise HTTPException(exc.status, exc.detail)


# ------------------------------------------------------------------------------------- models
class NewExperiment(BaseModel):
    template: str = "prototype"
    seed: int = 7
    engine: str = "heuristic"
    settle_months: int = 3
    scale: float = 1.0
    utilisation: float = 0.75
    decisions_per_month: Optional[int] = None


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
    return svc.health()


@app.get("/api/scenarios")
def scenarios():
    return svc.scenarios()


@app.get("/api/experiment")
def get_experiment():
    return call(svc.get_experiment)


@app.post("/api/experiment")
def new_experiment(req: NewExperiment):
    return call(svc.new_experiment, **req.model_dump())


@app.post("/api/load/{exp_id}")
def load_experiment(exp_id: str, month: Optional[int] = None, engine: str = "heuristic"):
    return call(svc.load_experiment, exp_id, month, engine)


@app.post("/api/interpret")
def interpret(req: InterpretRequest, fast: bool = False):
    return call(svc.interpret, req.text, fast)


@app.post("/api/run")
async def run(req: RunRequest):
    return await call_off_loop(svc.run, req.plan, req.text)


@app.post("/api/discard")
async def discard():
    return await call_off_loop(svc.discard)


@app.post("/api/play")
async def play(req: PlayRequest):
    return await call_off_loop(svc.play, req.playing, req.speed, req.steps, req.until_month)


@app.get("/api/employee/{world}/{eid}")
def employee(world: str, eid: str):
    return call(svc.employee, world, eid)


@app.get("/api/team/{world}/{tid}")
def team(world: str, tid: str):
    return call(svc.team, world, tid)


@app.get("/api/events/{world}")
def events(world: str, significant: bool = True, since: int = 0):
    return call(svc.events, world, significant, since)


@app.get("/api/why/{world}/{event_id}")
def why(world: str, event_id: int):
    return call(svc.why, world, event_id)


@app.get("/api/effects")
def effects(min_effect: float = 0.5):
    return call(svc.effects, min_effect)


@app.get("/api/network/{world}")
def network(world: str):
    return call(svc.network, world)


@app.get("/api/decisions/{world}")
def decisions(world: str, agent: Optional[str] = None, last: int = 200):
    return call(svc.decisions, world, agent, last)


@app.get("/api/diagnostics")
def diagnostics():
    return call(svc.diagnostics)


@app.post("/api/explain")
def explain(req: ExplainRequest):
    return call(svc.explain, req.prompt)


@app.post("/api/save")
def save():
    return call(svc.save)


@app.get("/api/experiments")
def list_experiments():
    return call(svc.list_experiments)


@app.get("/api/export/{world}/{what}")
def export(world: str, what: str, fmt: str = "json"):
    content, media = call(svc.export, world, what, fmt)
    if media == "text/csv":
        return PlainTextResponse(content, media_type="text/csv")
    return JSONResponse(content)


@app.post("/api/batch")
async def start_batch(req: BatchRequest):
    # parsing free text may call the Apple model (seconds), so prepare off the loop too
    prep = await call_off_loop(svc.batch_prepare, req.plan, req.text, req.n, req.months, req.engine, req.seed0)
    job_id = prep["job"]["id"]
    asyncio.create_task(asyncio.to_thread(svc.run_batch_here, job_id, prep["args"]))
    return {"job_id": job_id}


@app.get("/api/batch/{job_id}")
def get_batch(job_id: str):
    return call(svc.get_batch, job_id)


# --------------------------------------------------------------------------------- websocket
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:     # browsers always send Origin; other local tools may omit it
        await websocket.close(code=1008)
        return
    await websocket.accept()
    hub.clients.add(websocket)
    exp = svc.ensure_experiment()
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
