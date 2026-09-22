# Validation

## What is verified now
* **Unit/integration tests** (`tests/`, 46 passing): generation sizes; determinism (same seed → identical history);
  fork without intervention stays identical; capacity arithmetic (nobody works beyond contracted + overtime cap);
  work cannot be completed twice; terminated employees hold no work; queues grow when arrivals exceed capacity;
  budget freeze blocks hiring; the admin-cut plan removes admin posts, protects frontline and wires causes to the
  intervention root; team merge and layer removal; causal chains reach the root; target aliases; AI agent capacity;
  export; heuristic probabilities; recorded replay; cache keys; confidence routing; adapter fallback; rule parser on all
  shipped scenarios; flat Apple FM output validation; SQLite round trip. `tests/test_review_fixes.py` adds the invariants
  from the September 2026 review: no work item ever sits outside every queue; the baseline stays stable with no
  intervention; personal workload and errors stay bounded; neighbouring teams can help; low-priority work expires;
  common random numbers survive an extra item in one world; the rule parser never guesses (unrecognised text gives
  warnings and no changes), handles negation, protection clauses and multiple clauses; merges resolve team names;
  WHY chains reach the intervention; organisation-wide rows are never labelled emergent or third order.
* **Baseline stability** across seeds (see SIMULATION_MODEL.md).
* **Common random numbers**: with no intervention, baseline and fork are identical for 12+ months.
* **Batch sanity** (32 seeds × 36 months, admin −20%, re-run 2026-09-22): stable 66%, a bottleneck somewhere 34%
  (Finance 28%, Business Support 6%), no world with delivery down >10%, net cost saving 78%, stress up 44%. The protected
  frontline team is the distant effect: Programme Delivery stress rose in 50% of worlds and its backlog in 47% (median
  lag ~21 months), because admin work flows into it through new help channels — protection of posts is not protection
  of workload. Unscripted.

* **Replay fidelity**: a saved experiment reloaded by replay reproduces baseline and intervention metrics exactly.
* **End-to-end smoke test** (`frontend/tests/smoke.spec.ts`, `npm run smoke`): loads the page, interprets and runs an
  intervention, advances 24 months, checks effects, WHY, inspectors and diagnostics through the real server.
* **Sensitivity sweeps**: `scripts/batch_cli.py --sweep <SimConfig field>=a,b,c` tabulates outcome frequencies per level.

## What is *not* validated
Nothing here has been compared with a real organisation. Parameter values are plausible, not estimated.

## How historical validation would work
1. Import an anonymised organisation at T0 (CSV: employee_id, role, team, department, grade, FTE, manager_id, skill_tags)
   plus process definitions and observed monthly demand.
2. Feed the known changes between T0 and T1 as a change plan.
3. Run many seeds; compare distributions of queue growth, capacity pressure, team turnover, project delays and
   cross-team dependencies with what was observed at T1.
4. Keep **calibration** data (used to tune SimConfig) strictly separate from **validation** data (never tuned on).
5. Report where the model is wrong. Do not tune until everything matches.
