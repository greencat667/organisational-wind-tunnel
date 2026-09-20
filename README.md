# Organisational Wind Tunnel

An AI-powered 3D organisational simulator that runs entirely on your Mac. Describe a change in plain English
("Reduce administrative capacity by 20% while protecting frontline delivery"), watch a synthetic organisation of
persistent employee agents respond over simulated months and years, and trace the second- and third-order
consequences back to their causes.

> **This is an exploratory organisational simulation, not a prediction of employee behaviour or organisational
> outcomes.** Use it for hypothesis generation, second-order thinking, stress-testing and surfacing dependencies —
> never for assessing, scoring or making decisions about real people. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## What it is

```
USER INTERVENTION  →  Apple Foundation Model  →  validated CHANGE PLAN  →  ORGANISATION SIMULATION
                                                                              ↓
                                                        Laya / Needle / rules: bounded agent decisions
                                                                              ↓
                                                            deterministic organisational physics
                                                                              ↓
                                                              updated organisation → next month ↺
```

* **Four separated layers.** A language model only *interprets* interventions and *explains* results; small
  decision models (Laya, Cactus Needle 3) or rules make thousands of bounded employee/manager decisions; a
  deterministic engine owns time, work, queues, capacity, skills, money, recruitment, absence, information and
  relationships; a Three.js world makes the system visible.
* **Consequences are not scripted.** The intervention changes the environment. Agents respond. Their responses
  change the environment for others. Cascades (or their absence) emerge from the rules.
* **Baseline vs intervention** run from the same seed with *common random numbers*, so every divergence is caused
  by the change, not by luck. A causal event graph lets you click any effect and ask **WHY DID THIS HAPPEN?**
* **Many worlds.** Run hundreds or thousands of seeds without rendering and read the outcome *frequencies within the
  model*, clusters and distant "surprises".
* **Fully local.** Apple Foundation Models via macOS's built-in `fm serve`, Laya via PyTorch/MPS, Needle 3 via its
  native library. No cloud APIs, no telemetry.

## Quick start (Apple Silicon, macOS 26/27)

```bash
cd "personal-projects/065 - Organisational Wind Tunnel"
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r backend/requirements.txt
(cd frontend && npm install)
./windtunnel.sh            # backend :8765 + frontend :5180
```

Open <http://127.0.0.1:5180>. Optional: `WINDTUNNEL_ENGINE=laya ./windtunnel.sh` (or `needle`), `WINDTUNNEL_TEMPLATE=charity500`.
Apple Intelligence must be enabled for the intervention parser to use the on-device model (`fm available` should say
"System model available"); otherwise a rule-based parser is used and the UI says so.

The critical demo: press **play** on the healthy organisation → type *Reduce administrative capacity by 20% while
maintaining existing frontline delivery* → **SIMULATE CHANGE** → check the interpreted plan → **RUN EXPERIMENT** →
**+3 yrs** → open **Effects** → click a second-order effect → read the causal chain → drag the time scrubber back.

## Batch runs from the command line

```bash
.venv/bin/python scripts/batch_cli.py --n 500 --months 36 --text "Reduce administrative capacity by 20%"
```

## Tests

```bash
.venv/bin/python -m pytest -q tests     # 34 tests: physics, determinism, forking, interventions, causality, AI mechanics, store, adapters
(cd frontend && npm run smoke)          # Playwright end-to-end smoke test against the real servers
.venv/bin/python scripts/batch_cli.py --n 100 --sweep target_utilisation=0.65,0.75,0.85   # sensitivity sweep
```

## Documentation

| Doc | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | layers, modules, data flow, technology choices and why |
| [docs/SIMULATION_MODEL.md](docs/SIMULATION_MODEL.md) | every simulation assumption: organisation, work, processes, physics, psychology, information, finance |
| [docs/AGENT_DECISIONS.md](docs/AGENT_DECISIONS.md) | decision engine abstraction, triggers, context compression, actions, confidence routing, cache |
| [docs/LAYA.md](docs/LAYA.md) · [docs/NEEDLE.md](docs/NEEDLE.md) · [docs/APPLE_FOUNDATION_MODELS.md](docs/APPLE_FOUNDATION_MODELS.md) | verified APIs, how each model is used, measured latency, pitfalls |
| [docs/AI_SCENARIOS.md](docs/AI_SCENARIOS.md) | AI agent pools, supervision, exceptions, silent errors, incidents, deskilling, attrition-based downsizing, delegated approvals; measured outcomes |
| [docs/VALIDATION.md](docs/VALIDATION.md) | what has been checked, how historical validation would work |
| [docs/PRIVACY.md](docs/PRIVACY.md) · [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | privacy design; what this tool is and is not |

## AI-impact scenarios

Three shipped chips — **Automate back end**, **Supervisory roles**, **AI workflow loops** (plus a delegated-approvals variant) — exercise the AI primitives: agent pools that need human supervision, exceptions returning to staff, hidden defects surfacing downstream, incidents, skill atrophy and attrition-based downsizing. See [docs/AI_SCENARIOS.md](docs/AI_SCENARIOS.md).

## Status

First vertical slice, built 2026-09-20: 100-person / 8-team synthetic organisation (a 500-person, 27-team template
also ships), real work items flowing through 14 processes, monthly simulation, heuristic + Laya + Needle + recorded
decision engines, Apple FM intervention parser with rule fallback, Three.js world with instanced employees and
animated work/information flow, baseline/intervention split universe, time scrubber, event timeline, employee and
team inspectors with decision replay, effects classifier, emergence detector, WHY chains, Monte Carlo batch runner
with clusters and surprises, SQLite save/export, developer diagnostics. Measured numbers are in the docs.
