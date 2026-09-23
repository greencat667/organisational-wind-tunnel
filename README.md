# Organisational Wind Tunnel

A 3D organisational simulator, with AI as an optional extra rather than the engine room. Describe a change in plain
English ("Reduce administrative capacity by 20% while protecting frontline delivery"), watch a synthetic
organisation of persistent employee agents respond over simulated months and years, and trace the second- and
third-order consequences back to their causes.

> **This is an exploratory organisational simulation, not a prediction of employee behaviour or organisational
> outcomes.** Use it for hypothesis generation, second-order thinking, stress-testing and surfacing dependencies —
> never for assessing, scoring or making decisions about real people. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

[![The Organisational Wind Tunnel: Simulating AI's Second-Order Effects](https://img.youtube.com/vi/U7b4nGF48SU/maxresdefault.jpg)](https://www.youtube.com/watch?v=U7b4nGF48SU)

**Try it in your browser, nothing to install: <https://greencat667.github.io/organisational-wind-tunnel/>** · **New here? Start with the [user guide](docs/GUIDE.md)** — a screenshot walkthrough of the demo and every panel.

## What it is

```
USER INTERVENTION  →  parser (rules, or an LLM if one's available)  →  validated CHANGE PLAN  →  SIMULATION
                                                                              ↓
                                                    bounded agent decisions: rules, or a small model if selected
                                                                              ↓
                                                            deterministic organisational physics
                                                                              ↓
                                                              updated organisation → next month ↺
```

* **AI-optional, not AI-dependent.** By default, every decision in the wind tunnel — interpreting your intervention
  and every employee/manager choice — is made by fast, deterministic rules. You can swap either one for a model
  (Apple's on-device model for interpretation; Laya for agent decisions) to see how it changes
  things, but nothing about running the simulator or reading its output requires a model, a GPU, or an API key.
* **Consequences are not scripted.** The intervention changes the environment. Agents respond. Their responses
  change the environment for others. Cascades (or their absence) emerge from the rules, not from a script.
* **Baseline vs intervention** run from the same seed with *common random numbers*, so every divergence is caused
  by the change, not by luck. A causal event graph lets you click any effect and ask **WHY DID THIS HAPPEN?**
* **Many worlds.** Run hundreds or thousands of seeds without rendering and read the outcome *frequencies within the
  model*, clusters and distant "surprises". Verified to hold up at 10,000+ simulated employees.
* **Fully local, no telemetry.** The deterministic core is pure Python and needs nothing beyond the pinned
  dependencies. The optional AI extras below add no network calls either — everything runs on-device.

## Run it in a browser, with nothing installed

The simulation also runs entirely in the browser (Python compiled to WebAssembly), so the rules-based wind tunnel can
be published as a free static site — every visitor gets their own organisation, on their own machine.
`cd frontend && npm run build:static` builds it; [docs/HOSTING.md](docs/HOSTING.md) covers Cloudflare/GitHub Pages and
what differs (no Laya or Apple model; saves live in the browser).

## Quick start (any machine with Python 3.11 and Node)

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm install)
./windtunnel.sh            # backend :8765 + frontend :5180
```

Open <http://127.0.0.1:5180>. This runs the deterministic path end to end: a rule-based parser turns your English
into a change plan, and rule-based agents make every decision. Nothing here needs a particular OS, chip, or model
download.

The critical demo: press **play** on the healthy organisation → type *Reduce administrative capacity by 20% while
maintaining existing frontline delivery* → **SIMULATE CHANGE** → check the interpreted plan → **RUN EXPERIMENT** →
**+3 yrs** → open **Effects** → click a second-order effect → read the causal chain → drag the time scrubber back.

### Optional AI extras (Apple Silicon Mac, macOS 26/27)

Two swappable pieces can replace their rule-based defaults if you want to compare how model-driven interpretation
or decisions differ from rules:

| Piece | What it replaces | Requires |
|---|---|---|
| Apple Foundation Models (`fm serve`) | the rule-based intervention parser | macOS 26/27 with Apple Intelligence enabled |
| [Laya](https://github.com/NandhaKishorM/laya) (`pip install laya`, Apache-2.0) | the rule-based decision engine | PyTorch; fastest on Apple Silicon (MPS) |

If `fm` isn't on your machine, the parser detects that immediately and uses rules with no delay or timeout — nothing
to configure. To try a decision model instead of rules: `WINDTUNNEL_ENGINE=laya ./windtunnel.sh`, or pick the engine
per experiment in the app (Saved → New experiment) or per batch (Many worlds). Rules stay the default: in a head-to-head
test Laya chose differently 89% of the time at ~50–200× the run time, and its outcomes differ mainly because of a
wording bias towards cutting corners (see [docs/VALIDATION.md](docs/VALIDATION.md#decision-engines-compared)), so treat
it as a sensitivity check.
`WINDTUNNEL_TEMPLATE=charity500` switches the synthetic organisation from 100 to ~500 people. Details, measured
latency and known pitfalls of each are in [docs/APPLE_FOUNDATION_MODELS.md](docs/APPLE_FOUNDATION_MODELS.md),
and [docs/LAYA.md](docs/LAYA.md). (A second model, Cactus Needle 3, was removed in September 2026: slow, unstable on
long runs, and no added value.)

`backend/requirements.txt` installs Laya by default so the extra works out of the box; if you're on a platform where it
doesn't build cleanly, delete that line and reinstall — the deterministic path doesn't need
them.

## Batch runs from the command line

```bash
.venv/bin/python scripts/batch_cli.py --n 500 --months 36 --text "Reduce administrative capacity by 20%"
.venv/bin/python scripts/batch_cli.py --n 100 --sweep target_utilisation=0.65,0.75,0.85   # sensitivity sweep
.venv/bin/python scripts/batch_cli.py --n 24 --scale 100 --text "..."                     # ~10,000-employee org
```

## Tests

```bash
.venv/bin/python -m pytest -q tests     # 57 tests: physics, invariants, determinism, forking, interventions, parser safety, causality, AI mechanics, store, adapters
(cd frontend && npm run smoke)          # Playwright end-to-end smoke test against the real servers
(cd frontend && npm run build:static && npm run smoke:static)   # the same for the browser-only build
```

## Documentation

| Doc | Contents |
|---|---|
| [docs/HOSTING.md](docs/HOSTING.md) | the browser-only build: build, publish (Cloudflare/GitHub Pages), what differs |
| [docs/GUIDE.md](docs/GUIDE.md) | **user guide**: screenshot walkthrough of the demo, every panel and control, reading results honestly |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | layers, modules, data flow, technology choices and why |
| [docs/SIMULATION_MODEL.md](docs/SIMULATION_MODEL.md) | every simulation assumption: organisation, work, processes, physics, psychology, information, finance |
| [docs/AGENT_DECISIONS.md](docs/AGENT_DECISIONS.md) | decision engine abstraction, triggers, context compression, actions, confidence routing, cache |
| [docs/LAYA.md](docs/LAYA.md) · [docs/APPLE_FOUNDATION_MODELS.md](docs/APPLE_FOUNDATION_MODELS.md) | verified APIs, how each optional model is used, measured latency, pitfalls |
| [docs/AI_SCENARIOS.md](docs/AI_SCENARIOS.md) | *simulated* AI-adoption scenarios (agent pools, supervision, deskilling…) — deterministic, no model involved |
| [docs/PERFORMANCE.md](docs/PERFORMANCE.md) | the O(n²) bottlenecks found and fixed to make 10,000+-employee organisations practical |
| [docs/VALIDATION.md](docs/VALIDATION.md) | what has been checked, how historical validation would work |
| [docs/PRIVACY.md](docs/PRIVACY.md) · [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | privacy design; what this tool is and is not |

## AI-impact scenarios

Four shipped chips — **Automate back end**, **Supervisory roles**, **AI workflow loops**, and a delegated-approvals
variant — let you simulate an organisation *adopting* AI: agent pools that need human supervision, exceptions
returning to staff, hidden defects surfacing downstream, incidents, skill atrophy and attrition-based downsizing.
This is all deterministic organisational physics, distinct from the optional AI extras above that can drive the
simulator itself — you don't need any model installed to run these scenarios. See
[docs/AI_SCENARIOS.md](docs/AI_SCENARIOS.md).

## Status

100-person / 8-team synthetic organisation (a 500-person, 27-team template also ships), real work items flowing
through 14 processes, monthly simulation, heuristic + Laya + recorded decision engines, an intervention
parser with rule fallback, a Three.js world with instanced employees and animated work/information flow,
baseline/intervention split universe, time scrubber, event timeline, employee and team inspectors with decision
replay, effects classifier, emergence detector, WHY chains, Monte Carlo batch runner with clusters and surprises,
SQLite save/export, developer diagnostics. Performance-tested and bug-fixed up to 20,000 simulated employees (see
[docs/PERFORMANCE.md](docs/PERFORMANCE.md)); the 100- and 500-person templates are the calibrated, validated sizes.
Measured numbers are in the docs.

## License

[MIT](LICENSE) for this repository's own code. The optional AI extras are separate projects with their own
licenses: Laya is Apache-2.0; Apple Foundation Models is Apple's own on-device system
service, called over local HTTP and never bundled or redistributed here.
