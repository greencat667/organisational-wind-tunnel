"""The wind tunnel as a service, independent of any transport.

Owns the live experiment (baseline + intervention worlds), the play loop's state, analysis, persistence and batch
jobs. Two thin front ends drive it: ``server.py`` (FastAPI + WebSocket on localhost) and ``browser.py`` (Pyodide in a
Web Worker, for the static build). Anything that would be broadcast to clients goes through the ``emit`` callback.
"""
from __future__ import annotations

import os
import re
import threading
import time
import uuid
from typing import Any, Callable, Optional

from . import analysis, batch
from .config import SimConfig
from .decisions import CachedDecisionEngine, make_engine
from .engine import World
from .interventions.parser import InterventionParser, rule_parse
from .interventions.primitives import describe_plan, schedule_plan
from .interventions.schema import ChangePlan, validate_plan
from .model import to_dict
from .store import Store

VERSION = "0.1.0"


class ServiceError(Exception):
    """An error with an HTTP-style status, turned into a response by whichever front end is in use."""

    def __init__(self, status: int, detail: str = ""):
        super().__init__(detail)
        self.status = status
        self.detail = detail


SCENARIOS = [
    {"id": "admin_cut", "name": "Admin cut", "text": "Reduce administrative capacity by 20% while maintaining existing frontline delivery."},
    {"id": "ai_automation", "name": "AI automation", "text": "Automate 40% of routine finance and operations work over 18 months."},
    {"id": "flatten", "name": "Flatten structure", "text": "Remove one management layer and increase team autonomy."},
    {"id": "funding_shock", "name": "Funding shock", "text": "Organisation income falls 15% next year."},
    {"id": "rapid_growth", "name": "Rapid growth", "text": "Demand for services doubles over two years."},
    {"id": "ai_backend", "name": "Automate back end", "text": "Automate the back office: deploy AI agents to take 70% of routine finance, HR and administrative work over 6 months, and do not replace leavers in those teams."},
    {"id": "ai_supervisors", "name": "Supervisory roles", "text": "Convert half of the administrative and finance roles into supervisors of AI agent teams, with agents handling 80% of routine work."},
    {"id": "ai_loops", "name": "AI workflow loops", "text": "Let AI run the procurement, invoicing and expenses workflows end to end for 80% of cases, with humans handling exceptions and approvals."},
    {"id": "ai_loops_delegated", "name": "AI loops + approvals", "text": "Let AI run the procurement, invoicing and expenses workflows end to end for 80% of cases, including approvals, with humans handling exceptions only."},
    {"id": "merge", "name": "Merge teams", "text": "Merge the fundraising and communications teams."},
]


class Experiment:
    """Holds one baseline world and (optionally) one intervention world, stepping them in lock-step."""

    def __init__(self, template: str, seed: int, engine_name: str, months_settle: int = 3, scale: float = 1.0,
                 utilisation: float = 0.75, decisions_per_month: Optional[int] = None, config: Optional[SimConfig] = None):
        self.id = uuid.uuid4().hex[:10]
        self.template = template
        self.seed = seed
        self.engine_name = engine_name
        self.settle = months_settle
        self.scale = scale
        self.engine = self._make_engine(engine_name)
        if config is None:
            cfg = SimConfig()
            cfg.target_utilisation = utilisation
            if decisions_per_month:
                cfg.max_decisions_per_month = decisions_per_month          # same cap for every engine = fair comparison
            elif engine_name == "laya":
                cfg.max_decisions_per_month = int(os.environ.get("WINDTUNNEL_AI_DECISIONS_PER_MONTH", "24"))   # keep AI engines interactive
        else:
            cfg = config                                                    # replaying a saved experiment: its config wins
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
        return CachedDecisionEngine(eng) if name == "laya" else eng

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

    @classmethod
    def from_saved(cls, store: Store, exp_id: str, up_to_month: Optional[int] = None, live_engine: str = "heuristic") -> "Experiment":
        """Rebuild a saved experiment by deterministic replay: same seed, same config, recorded decisions per world.
        Optionally stop at ``up_to_month`` (fork from that date) and continue with a live engine."""
        from .decisions import RecordedDecisionEngine
        saved = store.load_experiment(exp_id)
        if not saved:
            raise KeyError(exp_id)
        cfg = SimConfig(**{k: v for k, v in (saved.get("config") or {}).items() if k in SimConfig.__dataclass_fields__})
        runs = {r["label"]: r for r in store.list_runs(exp_id)}
        base_dec = store.load_run_decisions(runs["baseline"]["id"]) if "baseline" in runs else []
        scale = float((saved.get("config") or {}).get("_scale", 1.0))
        exp = cls(saved["template"], saved["seed"], live_engine, months_settle=0, config=cfg, scale=scale)
        # A pure reload keeps the id; a fork from an earlier month is a new experiment, so saving it can never
        # overwrite (and leave stale rows in) the run it was forked from.
        exp.id = exp_id if up_to_month is None else uuid.uuid4().hex[:10]
        exp.baseline.decision_engine = RecordedDecisionEngine(base_dec, source_engine=saved["engine"])
        target = saved.get("months", 0) if up_to_month is None else min(up_to_month, saved.get("months", 0))
        fork_month = saved.get("fork_month")
        plan = validate_plan(saved["plan"]) if saved.get("plan") else None
        while exp.baseline.month < target:
            if plan and fork_month is not None and exp.baseline.month == fork_month and exp.intervention is None:
                exp.fork(plan, saved.get("intervention_text", ""))
                int_dec = store.load_run_decisions(runs["intervention"]["id"]) if "intervention" in runs else []
                exp.intervention.decision_engine = RecordedDecisionEngine(int_dec, source_engine=saved["engine"])
            exp.step()
        if plan and fork_month is not None and exp.intervention is None and exp.baseline.month == fork_month:
            exp.fork(plan, saved.get("intervention_text", ""))
        for w in exp.worlds():                      # continue live from here
            w.decision_engine = exp.engine
        exp.replayed_from = {"experiment_id": exp_id, "months": target, "recorded_engine": saved["engine"]}
        return exp

    def status(self) -> dict[str, Any]:
        eng = self.engine
        return {"id": self.id, "template": self.template, "seed": self.seed, "engine": self.engine_name, "engine_info": eng.describe(),
                "engine_stats": eng.stats(), "engine_error": getattr(self, "engine_error", None), "month": self.baseline.month,
                "label": self.baseline.date_label(), "forked": self.intervention is not None, "fork_month": self.fork_month,
                "plan": self.plan.model_dump() if self.plan else None, "intervention_text": self.intervention_text,
                "playing": self.playing, "speed": self.speed, "headcount": len([e for e in self.baseline.employees.values() if e.status == "active"]),
                "mean_step_ms": round(1000 * sum(self.step_times) / len(self.step_times), 1) if self.step_times else None,
                "utilisation": self.baseline.config.target_utilisation, "decisions_per_month": self.baseline.config.max_decisions_per_month,
                "replayed_from": getattr(self, "replayed_from", None), "last_error": getattr(self, "last_error", None),
                "agreement": {w.label: w.agreement_report() for w in self.worlds()} if self.engine_name != "heuristic" else None}




class Service:
    def __init__(self, emit: Optional[Callable[[dict[str, Any]], None]] = None, store_path: Optional[str] = None,
                 use_fm: bool = True, allow_model_engines: bool = True, max_batch: int = 5000):
        self.experiment: Optional[Experiment] = None
        self.emit = emit or (lambda msg: None)
        self.parser = InterventionParser(use_fm=use_fm)
        self.store = Store(store_path) if store_path else Store()
        self.batch_jobs: dict[str, dict[str, Any]] = {}
        self.allow_model_engines = allow_model_engines     # False in the browser: Laya can't run there
        self.max_batch = max_batch
        self.client_count: Callable[[], int] = lambda: 0

    # ----------------------------------------------------------------------------- experiment lifecycle
    def ensure_experiment(self) -> Experiment:
        if self.experiment is None:
            self.experiment = Experiment(os.environ.get("WINDTUNNEL_TEMPLATE", "prototype"), int(os.environ.get("WINDTUNNEL_SEED", "7")),
                                         self._engine_name(os.environ.get("WINDTUNNEL_ENGINE", "heuristic")))
        return self.experiment

    def _engine_name(self, name: str) -> str:
        return name if self.allow_model_engines else "heuristic"

    def health(self) -> dict[str, Any]:
        return {"ok": True, "version": VERSION}

    def scenarios(self) -> list[dict[str, str]]:
        return SCENARIOS

    def get_experiment(self) -> dict[str, Any]:
        exp = self.ensure_experiment()
        with exp.lock:
            return {"status": exp.status(), "structure": exp.baseline.structure(),
                    "frames": {w.label: w.frames for w in exp.worlds()},
                    "metrics": {w.label: w.metrics_history for w in exp.worlds()},
                    "events": {w.label: [to_dict(e) for e in w.events if e.significant] for w in exp.worlds()}}

    def new_experiment(self, template: str = "prototype", seed: int = 7, engine: str = "heuristic", settle_months: int = 3,
                       scale: float = 1.0, utilisation: float = 0.75, decisions_per_month: Optional[int] = None) -> dict[str, Any]:
        if self.experiment:
            self.experiment.playing = False
        self.experiment = Experiment(template, seed, self._engine_name(engine), settle_months, scale, utilisation, decisions_per_month)
        return self.get_experiment()

    def load_experiment(self, exp_id: str, month: Optional[int] = None, engine: str = "heuristic") -> dict[str, Any]:
        """Rebuild a saved experiment by replay (optionally only up to `month` = fork from that date)."""
        if self.experiment:
            self.experiment.playing = False
        try:
            self.experiment = Experiment.from_saved(self.store, exp_id, month, self._engine_name(engine))
        except KeyError:
            raise ServiceError(404, f"no saved experiment {exp_id}")
        return self.get_experiment()

    # ----------------------------------------------------------------------------- interventions
    def interpret(self, text: str, fast: bool = False) -> dict[str, Any]:
        """fast=True returns the rule-based interpretation immediately (the UI then asks again for the Apple model's)."""
        exp = self.ensure_experiment()
        hint = ", ".join(t.name for t in exp.baseline.teams.values())
        t0 = time.perf_counter()
        if fast:
            plan = rule_parse(text)
            return {"plan": plan.model_dump(), "source": "rules", "error": None, "latency_ms": round((time.perf_counter() - t0) * 1000),
                    "interpreted": describe_plan(exp.baseline, plan), "raw": None, "fast": True}
        plan = self.parser.parse(text, org_hint=hint)
        return {"plan": plan.model_dump(), "source": self.parser.last_source, "error": self.parser.last_error,
                "latency_ms": round((time.perf_counter() - t0) * 1000), "interpreted": describe_plan(exp.baseline, plan),
                "raw": self.parser.last_raw if self.parser.last_source == "apple_fm" else None}

    def run(self, plan: dict[str, Any], text: str = "") -> dict[str, Any]:
        exp = self.ensure_experiment()
        try:
            p = validate_plan(plan)
        except Exception as exc:
            raise ServiceError(400, f"invalid plan: {exc}")
        if not p.changes:
            raise ServiceError(400, "nothing to run: the plan has no changes")
        exp.fork(p, text)
        self.store.save_experiment(self._experiment_record(exp, name=text[:60]))
        self.emit({"type": "forked", "status": exp.status(), "structure": exp.intervention.structure(),
                   "frame": exp.intervention.frames[-1] if exp.intervention.frames else None})
        return {"status": exp.status(), "interpreted": describe_plan(exp.baseline, p)}

    def discard(self) -> dict[str, Any]:
        exp = self.ensure_experiment()
        exp.discard_intervention()
        self.emit({"type": "status", "status": exp.status()})
        return exp.status()

    # ----------------------------------------------------------------------------- time
    def play(self, playing: Optional[bool] = None, speed: Optional[float] = None, steps: Optional[int] = None,
             until_month: Optional[int] = None) -> dict[str, Any]:
        exp = self.ensure_experiment()
        if speed is not None:
            exp.speed = max(0.1, speed)
        if steps:
            exp.playing = False
            for _ in range(min(int(steps), 600)):
                self.emit({"type": "frame", **exp.step()})
        if until_month is not None:
            exp.target_month = until_month
            exp.playing = True
        if playing is not None:
            exp.playing = playing
        self.emit({"type": "status", "status": exp.status()})
        return exp.status()

    def tick(self) -> float:
        """One iteration of the play loop: step if playing, emit the frame, and return how long to wait before the next
        call (seconds). Front ends call this in their own loop (asyncio on the server, setTimeout in the browser)."""
        exp = self.experiment
        if exp is None or not exp.playing:
            return 0.05
        if exp.target_month is not None and exp.baseline.month >= exp.target_month:
            exp.playing = False
            exp.target_month = None
            self.emit({"type": "status", "status": exp.status()})
            return 0.05
        t0 = time.perf_counter()
        try:
            out = exp.step()
        except Exception as exc:   # never let one bad step kill the loop for the rest of the session
            exp.playing = False
            exp.last_error = f"step failed at month {exp.baseline.month}: {exc!r}"[:300]
            self.emit({"type": "status", "status": exp.status()})
            return 0.05
        self.emit({"type": "frame", **out})
        dt = time.perf_counter() - t0
        return max(0.0, (1.0 / exp.speed) - dt) if exp.speed < 1000 else 0.0

    # ----------------------------------------------------------------------------- inspection
    def _world(self, label: str) -> World:
        exp = self.ensure_experiment()
        if label == "baseline":
            return exp.baseline
        if label == "intervention" and exp.intervention:
            return exp.intervention
        raise ServiceError(404, f"no world {label}")

    def employee(self, world: str, eid: str) -> dict[str, Any]:
        exp = self.ensure_experiment()
        with exp.lock:
            w = self._world(world)
            if eid not in w.employees:
                raise ServiceError(404, f"no employee {eid}")
            return w.employee_detail(eid)

    def team(self, world: str, tid: str) -> dict[str, Any]:
        exp = self.ensure_experiment()
        with exp.lock:
            w = self._world(world)
            if tid not in w.teams:
                raise ServiceError(404, f"no team {tid}")
            return w.team_detail(tid)

    def events(self, world: str, significant: bool = True, since: int = 0) -> list[dict[str, Any]]:
        w = self._world(world)
        return [to_dict(e) for e in w.events if (e.significant or not significant) and e.month >= since]

    def why(self, world: str, event_id: int) -> dict[str, Any]:
        exp = self.ensure_experiment()
        w = self._world(world)
        with exp.lock:
            res = analysis.why(w.events, int(event_id))
        for n in res["nodes"]:
            n["date"] = w.date_label(n["month"])
        for c in res["chain"]:
            c["date"] = w.date_label(c["month"])
        return res

    def effects(self, min_effect: float = 0.5) -> dict[str, Any]:
        exp = self.ensure_experiment()
        if not exp.intervention:
            return {"effects": [], "emergence": [], "note": "no intervention running"}
        with exp.lock:
            rep = analysis.classify_effects(exp.intervention, exp.baseline, float(min_effect))
            rep["emergence"] = analysis.detect_emergence(exp.intervention, exp.baseline)
            rep["divergence_by_team"] = self._team_divergence(exp)
        return rep

    def network(self, world: str) -> dict[str, Any]:
        exp = self.ensure_experiment()
        w = self._world(world)
        with exp.lock:
            return {"informal": analysis.informal_network(w), "formal": analysis.formal_network(w)}

    def decisions(self, world: str, agent: Optional[str] = None, last: int = 200) -> list[dict[str, Any]]:
        w = self._world(world)
        log = [d for d in w.decision_log if agent is None or d["agent_id"] == agent]
        return log[-int(last):]

    def diagnostics(self) -> dict[str, Any]:
        exp = self.ensure_experiment()
        try:
            import resource
            rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
        except Exception:          # not available in the browser (Pyodide)
            rss_mb = 0
        return {"status": exp.status(), "timing": {w.label: w.timing for w in exp.worlds()}, "engine": exp.engine.describe(), "engine_stats": exp.engine.stats(),
                "apple_fm": {"available": self.parser.fm.available, "healthy": self.parser.use_fm and self.parser.fm.healthy(), "calls": self.parser.fm.calls,
                             "failures": self.parser.fm.failures, "last_latency_ms": round(self.parser.fm.last_latency_ms), "last_source": self.parser.last_source,
                             "last_error": self.parser.last_error},
                "memory_mb": round(rss_mb), "active_work_items": {w.label: sum(len(t.queue) for t in w.teams.values()) for w in exp.worlds()},
                "active_agents": {w.label: len([e for e in w.employees.values() if e.status == "active"]) for w in exp.worlds()},
                "decisions_total": {w.label: len(w.decision_log) for w in exp.worlds()}, "clients": self.client_count(),
                "agreement": {w.label: w.agreement_report() for w in exp.worlds()}}

    def explain(self, prompt: str) -> dict[str, Any]:
        text = self.parser.explain(prompt)
        return {"text": text, "source": "apple_fm" if text else "none", "error": self.parser.last_error}

    # ----------------------------------------------------------------------------- persistence
    def _experiment_record(self, exp: Experiment, name: str) -> dict[str, Any]:
        return {"id": exp.id, "template": exp.template, "seed": exp.seed, "engine": exp.engine_name, "intervention_text": exp.intervention_text,
                "plan": exp.plan.model_dump() if exp.plan else None, "config": {**exp.baseline.config.to_dict(), "_scale": exp.scale},
                "months": exp.baseline.month, "name": name, "fork_month": exp.fork_month}

    def save(self) -> dict[str, Any]:
        exp = self.ensure_experiment()
        versions = {"engine": exp.engine.describe(), "windtunnel": VERSION}
        ids = {}
        self.store.save_experiment(self._experiment_record(exp, name=exp.intervention_text[:60] or "baseline"))
        for w in exp.worlds():
            rid = f"{exp.id}-{w.label}"
            self.store.save_run(w, exp.id, rid, versions)
            ids[w.label] = rid
        return {"experiment_id": exp.id, "runs": ids}

    def list_experiments(self) -> dict[str, Any]:
        return {"experiments": self.store.list_experiments(), "runs": self.store.list_runs(), "batches": self.store.list_batches()}

    def export(self, world: str, what: str, fmt: str = "json") -> tuple[Any, str]:
        """Returns (content, media type): rows for JSON, text for CSV."""
        w = self._world(world)
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
            rows = [{"team": t.id, "item": i, **{k: v for k, v in to_dict(w.work_items[i]).items() if k != "path"}}
                    for t in w.teams.values() for i in t.queue if i in w.work_items]
        else:
            raise ServiceError(404, f"nothing to export called {what}")
        if fmt == "csv":
            return _csv(rows), "text/csv"
        return rows, "application/json"

    # ----------------------------------------------------------------------------- batches
    def batch_prepare(self, plan: Optional[dict[str, Any]] = None, text: Optional[str] = None, n: int = 100, months: int = 36,
                      engine: str = "heuristic", seed0: int = 1000) -> dict[str, Any]:
        """Validate a batch request and register the job. Returns the job and the per-world arguments, so a front end
        can run the worlds however it likes (a process pool here, a pool of Web Workers in the browser)."""
        exp = self.ensure_experiment()
        if not (1 <= int(n) <= self.max_batch) or not (1 <= int(months) <= 240):
            raise ServiceError(400, f"n must be 1–{self.max_batch} and months 1–240")
        try:
            if plan:
                p = validate_plan(plan)
            elif exp.plan:
                p = exp.plan
            elif text:
                p = self.parser.parse(text)
            else:
                raise ServiceError(400, "no plan")
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(400, f"invalid plan: {exc}")
        if not p.changes:
            raise ServiceError(400, "nothing to run: the plan has no changes")
        engine = self._engine_name(engine)
        job_id = uuid.uuid4().hex[:8]
        # same organisation settings as the interactive run: its config, scale and fork month
        settle = exp.fork_month if exp.fork_month is not None else exp.settle
        args = batch.make_args(exp.template, p, int(n), int(months), settle, engine, int(seed0), exp.baseline.config, exp.scale)
        job = {"id": job_id, "done": 0, "n": int(n), "status": "running", "result": None, "started": time.time(), "plan": p.model_dump(),
               "months": int(months), "engine": engine}
        self.batch_jobs[job_id] = job
        return {"job": job, "args": args, "template": exp.template}

    def batch_progress(self, job_id: str, done: int) -> None:
        job = self.batch_jobs.get(job_id)
        if job:
            job["done"] = done

    def batch_finish(self, job_id: str, results: Optional[list[dict[str, Any]]] = None, error: Optional[str] = None,
                     elapsed_s: float = 0.0) -> dict[str, Any]:
        job = self.batch_jobs[job_id]
        exp = self.ensure_experiment()
        if error is not None:
            job["status"] = "error"
            job["error"] = error[:300]
        else:
            res = batch.assemble(results or [], exp.template, job["months"], job["engine"], elapsed_s)
            job["result"] = {k: v for k, v in res.items() if k != "runs"}
            job["result"]["runs"] = [{k: r[k] for k in ("seed", "base", "int", "effects", "emergence")} for r in res["runs"]]
            job["result"]["histories"] = [{"seed": r["seed"], "base": r["base_hist"], "int": r["int_hist"]} for r in res["runs"][:200]]
            job["status"] = "done"
            job["done"] = job["n"]
            self.store.save_batch(job_id, exp.id, job["n"], job["engine"], job["months"], res["summary"],
                                  [(r["seed"], "intervention", r["int"]) for r in res["runs"]] + [(r["seed"], "baseline", r["base"]) for r in res["runs"]])
        self.emit({"type": "batch", "job": {k: v for k, v in job.items() if k != "result"}})
        return {k: v for k, v in job.items() if k != "result"}

    def run_batch_here(self, job_id: str, args: list, progress: Optional[Callable[[int, int], None]] = None) -> None:
        """Run a prepared batch in this process (a process pool for the heuristic engine), then finish it."""
        t0 = time.perf_counter()
        try:
            results = batch.run_args(args, progress=lambda i, n: (self.batch_progress(job_id, i), progress and progress(i, n)))
        except Exception as exc:
            self.batch_finish(job_id, error=repr(exc))
            return
        self.batch_finish(job_id, results=results, elapsed_s=time.perf_counter() - t0)

    def get_batch(self, job_id: str) -> dict[str, Any]:
        job = self.batch_jobs.get(job_id)
        if not job:
            b = self.store.load_batch(job_id)
            if not b:
                raise ServiceError(404, f"no batch {job_id}")
            return {"id": job_id, "status": "done", "result": {"summary": b["summary"], "runs": b["runs"]}}
        return job

    # ----------------------------------------------------------------------------- routing (browser front end)
    def dispatch(self, method: str, path: str, query: Optional[dict[str, Any]] = None, body: Optional[dict[str, Any]] = None) -> tuple[int, Any]:
        """Route an HTTP-shaped request to the service: the browser uses this in place of the FastAPI server, so the
        frontend's API calls are the same in both. Returns (status, body)."""
        q = {k: v for k, v in (query or {}).items() if v is not None and v != ""}
        b = body or {}
        method = method.upper()
        try:
            for m, pattern, fn in self._routes():
                if m != method:
                    continue
                match = re.fullmatch(pattern, path)
                if match:
                    return 200, fn(q, b, *match.groups())
            raise ServiceError(404, f"no route {method} {path}")
        except ServiceError as exc:
            return exc.status, {"detail": exc.detail}

    def _routes(self):
        num = lambda q, k, d, cast=float: cast(q[k]) if k in q else d
        flag = lambda q, k, d: str(q[k]).lower() in ("1", "true", "yes") if k in q else d
        return [
            ("GET", r"/health", lambda q, b: self.health()),
            ("GET", r"/scenarios", lambda q, b: self.scenarios()),
            ("GET", r"/experiment", lambda q, b: self.get_experiment()),
            ("POST", r"/experiment", lambda q, b: self.new_experiment(**{k: v for k, v in b.items() if k in (
                "template", "seed", "engine", "settle_months", "scale", "utilisation", "decisions_per_month")})),
            ("POST", r"/load/([\w-]+)", lambda q, b, i: self.load_experiment(i, num(q, "month", None, int), q.get("engine", "heuristic"))),
            ("POST", r"/interpret", lambda q, b: self.interpret(b.get("text", ""), flag(q, "fast", False))),
            ("POST", r"/run", lambda q, b: self.run(b.get("plan") or {}, b.get("text", ""))),
            ("POST", r"/discard", lambda q, b: self.discard()),
            ("POST", r"/play", lambda q, b: self.play(b.get("playing"), b.get("speed"), b.get("steps"), b.get("until_month"))),
            ("GET", r"/employee/(\w+)/([\w-]+)", lambda q, b, w, e: self.employee(w, e)),
            ("GET", r"/team/(\w+)/([\w-]+)", lambda q, b, w, t: self.team(w, t)),
            ("GET", r"/events/(\w+)", lambda q, b, w: self.events(w, flag(q, "significant", True), num(q, "since", 0, int))),
            ("GET", r"/why/(\w+)/(\d+)", lambda q, b, w, e: self.why(w, int(e))),
            ("GET", r"/effects", lambda q, b: self.effects(num(q, "min_effect", 0.5))),
            ("GET", r"/network/(\w+)", lambda q, b, w: self.network(w)),
            ("GET", r"/decisions/(\w+)", lambda q, b, w: self.decisions(w, q.get("agent"), num(q, "last", 200, int))),
            ("GET", r"/diagnostics", lambda q, b: self.diagnostics()),
            ("POST", r"/explain", lambda q, b: self.explain(b.get("prompt", ""))),
            ("POST", r"/save", lambda q, b: self.save()),
            ("GET", r"/experiments", lambda q, b: self.list_experiments()),
            ("GET", r"/export/(\w+)/(\w+)", lambda q, b, w, what: self.export(w, what, q.get("fmt", "json"))[0]),
            ("GET", r"/batch/(\w+)", lambda q, b, i: self.get_batch(i)),
        ]

    @staticmethod
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
