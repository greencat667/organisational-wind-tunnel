# 065 — Organisational Wind Tunnel — log

## 2026-09-20 — project created
- Brief received (see `brief/brief.md`). Learnings taken from 058 (Needle Plays Doom), 059 (Laya Plays Doom), 060/063 (Laya/Needle in jev-doom-agent).
- Verified locally: Apple `fm serve` (macOS 27 built-in CLI) returns JSON-schema-constrained output in ~2.7s. Laya 0.1.6 and cactus_needle 3.0.2 already installed in sibling venvs (Python 3.11); weights cached in `~/.cache/huggingface`.
- Architecture decisions kept in main thread; Sonnet subagents used for API research/verification only.
- Christian: future scope = AI-impact scenarios (automate back end; supervisory roles over AI agent teams; AI running workflow loops). Model hooks for AI agent pools added to the core design now.
- Finding: Apple FM guided generation via `fm serve` hangs on nested array-of-object JSON schemas (never returns; blocks the system model queue for all callers). Flat schemas return in ~1.2 s. Plan schema flattened to two change slots.

## 2026-09-20 — vertical slice built
- Backend: `backend/windtunnel/` (model, orggen, config, layout, engine, context, actions, decisions/{heuristic,laya,needle,recorded,cache}, interventions/{schema,parser,primitives}, analysis, batch, store, server). 24 pytest tests pass.
- Frontend: React + R3F app (`frontend/`), instanced employees, team clusters with queue stacks, animated work/info flows, split universe, scrubber, timeline, inspectors with decision replay, effects/why, batch panel, dev panel, watch mode.
- Launch: `./windtunnel.sh` (or `npm run dev` in frontend → `scripts/dev.mjs`) starts backend :8765 + frontend :5180. Registered as `windtunnel` in the workspace `.claude/launch.json`.
- Measured: heuristic month ≈ 5 ms (100 people) / 53 ms (500 people); Laya ≈ 270 ms/decision; Needle ≈ 500 ms/decision; Apple FM flat-schema interpretation ≈ 1.2 s when the daemon is free; batch 32 seeds × 2 worlds × 36 months ≈ 9 s on 6 workers.
- Physics decisions: common random numbers for exogenous luck; approvals consume management hours; utilisation calibrated per function (admin 0.84); baseline exit hazard; low-priority expiry; hiring freeze with hysteresis; restructure freezes hiring 6 months. Details in docs/SIMULATION_MODEL.md.
- Open: Apple on-device model service was wedged for long periods by earlier nested-schema requests; parser falls back to rules (UI shows source). Retest interpretation after a fresh boot / once queue clears.
