# Architecture

## Layers

```
Browser  (React 18 · TypeScript · React Three Fiber · zustand)           ← renders frames, never simulates
   ↕ WebSocket /ws (frames, status) + REST /api/*
Python 3.11 backend (FastAPI + uvicorn) — windtunnel/server.py
   ├─ Experiment: baseline World + intervention World stepped in lock-step (thread pool, asyncio loop)
   ├─ InterventionParser: Apple Foundation Models via `fm serve` (guided JSON) → validated ChangePlan; rule fallback
   ├─ AgentDecisionEngine: Heuristic | Laya | Needle | Recorded, wrapped in CachedDecisionEngine
   ├─ analysis: causal orders, divergence, emergence, key people, networks, k-means clusters
   ├─ batch: multiprocessing Monte Carlo (no frames), summaries, surprises
   └─ store: SQLite (experiments, runs, metrics, events, decisions, snapshots, batches)
```

The **World** (`windtunnel/engine.py`) is the only thing that changes organisational state. Decision engines return a
*distribution over bounded actions plus a confidence*; the World samples with its own seeded RNG, applies deterministic
effects (`interventions/primitives.apply_action`) and records an `Event` with explicit `causes`. Interventions are
composable primitives (`apply_change`) scheduled over a transition period.

Renderer and batch runner both consume the same World; frames are only produced when `record_frames=True`.

## Why these technologies

| Choice | Why |
|---|---|
| Python for the core | fast to iterate on rules; 100-person org steps in ~5 ms, 500-person in ~50 ms (heuristic engine); batch parallelises with `multiprocessing` |
| `fm serve` for Apple FM | Apple's first-party CLI (macOS 27, `/usr/bin/fm`) exposes the on-device model as an OpenAI-style Chat Completions server with `response_format: json_schema` guided generation. No Xcode build, no third-party bridge. The official `apple-fm-sdk` Python package exists but needs Xcode; `fm serve` needs nothing. |
| Laya (`pip install laya`) | non-autoregressive, calibrated `noul`/`choice`/`score` answers in one forward pass on MPS |
| Cactus Needle 3 (`pip install cactus-needle`) | 8–29 MB native tool-calling model, grammar-constrained output, calibrated confidence |
| React Three Fiber | declarative scene, instanced meshes for employees/work/info, drei helpers |
| zustand | tiny store for frames/metrics/events; frames are appended, never mutated |
| SQLite (stdlib) | zero infrastructure, one local file |

## Data flow per month

1. `/api/play` (or the play loop) calls `Experiment.step()` → each World `.step()` (see SIMULATION_MODEL.md).
2. Each step returns `{frame, metrics, timing}`; the server broadcasts `{"type":"frame", baseline:{…}, intervention:{…}}`.
3. The client appends frames; the 3D scene renders the latest (or the scrubbed) frame and animates *within* the month:
   employees glide to new positions, work items travel along arcs from → to, information pulses hop between people.
4. Inspectors (`/api/employee`, `/api/team`), `/api/effects`, `/api/why`, `/api/network`, `/api/diagnostics` read live state.

## Forking

`World.fork()` deep-copies everything (RNG state included) and `schedule_plan()` registers the intervention root
event and its scheduled primitives. Exogenous randomness (arrivals, absence, external exits, errors, information
sharing, decision sampling) uses **common random numbers** keyed by `(seed, month, tag, entity)`, so the two worlds
experience identical luck unless their state differs. This is what makes baseline/intervention differences causal.

## Files

```
backend/windtunnel/
  model.py           dataclasses: Employee, Team, Department, Process, WorkItem, InfoPacket, Event, Vacancy
  orggen.py          synthetic organisation templates + utilisation calibration
  config.py          SimConfig — every tunable physics parameter
  engine.py          World: monthly tick, physics, decisions hook, events, frames, fork, inspectors
  context.py         context compression → DecisionRequest
  actions.py         bounded action catalogue (questions for Laya, docstrings for Needle)
  decisions/         base, heuristic, laya_engine, needle_engine, recorded, cache
  interventions/     schema (pydantic + flat AFM schema), parser (fm serve + rules), primitives (actions + changes)
  analysis.py        causal orders, why, divergence, effects, emergence, networks, clusters
  batch.py           Monte Carlo runner + summariser
  store.py           SQLite
  server.py          FastAPI + WebSocket
frontend/src/        App, lib/{store,api,types}, scene/{Scene,Employees,Teams,Flows,Paths,palette}, ui/*
scripts/             dev.mjs (launcher), batch_cli.py
tests/               pytest suite
```
