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

## 2026-09-20 — AI-impact scenarios built out
- New `backend/windtunnel/ai.py`: agent pools with supervision coverage (supervisors first, officers ≤25%), learning (exception rate decays, τ=9 months), drift when under-supervised, incidents (3%/month), exceptions returning to humans at half hours, silent errors surfacing at the next stage (`ai_quality_leak`) or as corrections, skill atrophy + deskilling index, attrition-based downsizing (`replace_leavers=False` → `post_not_replaced`), delegated approvals, implementation work landing on target and Technology teams, internal one-stage processes for internal projects.
- New actions: `verify_ai_output`, `pause_ai_agents`, `expand_ai_agents`, `retrain_staff`; triggers `ai_introduced`, `ai_incident`, `ai_exceptions_high`, `supervision_gap`. Context exposes AI fields. Schema/parser understand "do not replace leavers", "including approvals", named workflows.
- Analysis: AI emergence kinds (ai_exception_load, quality_leakage, approval_bottleneck, supervision_gap, deskilling); batch outcomes (hidden defects, deskilling, approval bottleneck, automation recovery); cluster names disambiguated.
- Frontend: agent pool rings (cyan / dim paused / red incident), supervisor tint, magenta exception hops, AI metric tiles, inspector AI section. Four new chips.
- Measured (24 seeds × 36 months): back-office automation without backfill → stable 92%, net cost saving 50%, deskilling 25%, approval bottleneck 29%; Executive errors rise in 79–96% of AI worlds with ~15–31 month lag (defects leaking through finance reporting). Docs: `docs/AI_SCENARIOS.md`. 34 tests pass.

## 2026-09-20 — twelve improvements from the critique
1 per-person work allocation (personal workload, chunked sharing, manager rebalancing) · 2 causal wiring restricted to state-changing events with numeric deltas · 3 every change phased over the transition (demand compounds) · 4 trailing 6-month averages for emergence, ranking by floored relative change · 5 model-vs-rules shadow agreement diagnostic · 6 same decision cap for all engines · 7 remaining RNG draws keyed (hire names/archetypes, target choice, decision picks) · 8 progressive interpretation (rules instantly, Apple model upgrades) · 9 load/fork-from-date by deterministic replay (byte-identical, tested) · 10 slack preset (lean/normal/slack) · 11 `--sweep` sensitivity analysis in the batch CLI · 12 all monthly events sent + Playwright smoke test (`npm run smoke`).
Effect: admin −20% now bites (stable 50%, bottleneck 38%, workload-transfer clusters) because overload concentrates on people; utilisation sweep shows slack dominates outcomes (0.65 → 92% stable, 0.85 → 0%).
- WHY chains: linked events now chosen by kind priority (threshold crossings first); decision→action pairs folded; consecutive routine events collapsed. Admin-cut chain reads intervention → capacity reduced → redistributions/escalations → backlog critical.
