# Architecture

## Layers

```
Browser  (React 18 · TypeScript · React Three Fiber · zustand)           ← renders frames, never simulates
   ↕ WebSocket /ws (frames, status) + REST /api/*   — or, in the browser build, postMessage to a Web Worker
Front end: windtunnel/server.py (FastAPI + uvicorn)  |  windtunnel/browser.py (Pyodide in a Web Worker)
Service: windtunnel/service.py — everything below, transport-agnostic
   ├─ Experiment: baseline World + intervention World stepped in lock-step (play loop state; front ends drive tick())
   ├─ InterventionParser: Apple Foundation Models via `fm serve` (guided JSON) → validated ChangePlan; rule fallback
   ├─ AgentDecisionEngine: Heuristic | Laya | Recorded, wrapped in CachedDecisionEngine
   ├─ analysis: causal orders, divergence, emergence, key people, networks, k-means clusters
   ├─ batch: Monte Carlo (no frames) on a process pool, or a Web Worker pool in the browser; summaries, surprises
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
| React Three Fiber | declarative scene, instanced meshes for employees/work/info, drei helpers |
| zustand | tiny store for frames/metrics/events; frames are appended, never mutated |
| SQLite (stdlib) | zero infrastructure, one local file |

## Data flow per month

1. `/api/play` (or the play loop) calls `Experiment.step()` → each World `.step()` (see SIMULATION_MODEL.md).
2. Each step returns `{frame, metrics, timing}`; the server broadcasts `{"type":"frame", baseline:{…}, intervention:{…}}`.
3. The client appends frames; the 3D scene renders the latest (or the scrubbed) frame and animates *within* the month:
   employees glide to new positions, work items travel along arcs from → to, information pulses hop between people.
4. Inspectors (`/api/employee`, `/api/team`), `/api/effects`, `/api/why`, `/api/network`, `/api/diagnostics` read live state.

## Save, load, fork from any date
`/api/save` writes experiments, runs, metrics, events, decisions and a snapshot to SQLite. `/api/load/{id}` rebuilds an
experiment by **deterministic replay**: same template, seed and config, with each world's recorded decisions replayed by
`RecordedDecisionEngine`, so the reloaded state is byte-identical to what was saved (tested). `/api/load/{id}?month=M`
replays only to month M and hands both worlds to a live engine — fork from any date. Replay is cheap (~0.3 s for
36 months of a 100-person organisation) and needs no deserialiser.

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
  actions.py         bounded action catalogue (questions for Laya, descriptions, labels)
  decisions/         base, heuristic, laya_engine, recorded, cache
  interventions/     schema (pydantic + flat AFM schema), parser (fm serve + rules), primitives (actions + changes)
  analysis.py        causal orders, why, divergence, effects, emergence, networks, clusters
  batch.py           Monte Carlo runner + summariser
  store.py           SQLite
  server.py          FastAPI + WebSocket
frontend/src/        App, lib/{store,api,types}, scene/{Scene,Employees,Teams,Flows,Paths,palette}, ui/*
scripts/             dev.mjs (launcher), batch_cli.py
tests/               pytest suite
```
