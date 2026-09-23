# Validation

## What is verified now
* **Unit/integration tests** (`tests/`, 51 passing): generation sizes; determinism (same seed → identical history);
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
  WHY chains reach the intervention; organisation-wide rows are never labelled emergent or third order; baseline
  management load stays below 1.0 in every team; cutting officers doesn't cut approval time; blocked backfills reopen
  after a freeze; phased supervisory conversion reaches its target; AI supervision slips under pressure.
* **Baseline stability** across seeds (see SIMULATION_MODEL.md).
* **Common random numbers**: with no intervention, baseline and fork are identical for 12+ months.
* **Batch sanity** (32 seeds × 36 months, admin −20%, re-run 2026-09-23): stable 78%, a bottleneck somewhere 22%
  (Finance), no world with delivery down >10%, net cost saving 78%, stress up 28%. The protected frontline team is the
  distant effect: Programme Delivery turnover rose in 47% of worlds (median lag ~26 months), its morale fell in 34% and
  its backlog rose in 25%, because admin work flows into it through new help channels — protection of posts is not
  protection of workload. Unscripted.

* **Replay fidelity**: a saved experiment reloaded by replay reproduces baseline and intervention metrics exactly.
* **End-to-end smoke test** (`frontend/tests/smoke.spec.ts`, `npm run smoke`): loads the page, interprets and runs an
  intervention, advances 24 months, checks effects, WHY, inspectors and diagnostics through the real server.
* **Sensitivity sweeps**: `scripts/batch_cli.py --sweep <SimConfig field>=a,b,c` tabulates outcome frequencies per level.

## Decision engines compared

Run 2026-09-23: prototype organisation, seed 6, admin cut (−20%, protecting frontline), 18 months after the fork, the
same cap of 24 agent decisions per month for every engine, same machine (M5 Max, heavily loaded at the time).

| | Rules (heuristic) | Laya | Cactus Needle 3 |
|---|---|---|---|
| Run time, 18 months × 2 worlds | **2 s** | 445 s (+33 s load) | did not finish: 25 min limit hit at month 17 |
| Agreement with the rules (same situation) | — | 14% | — |
| Top actions (intervention world) | continue 266 · seek help 59 · overtime 38 · delay 27 | **reduce quality 198** · delay 71 · escalate 56 · continue 49 | — |
| Asked another team for help | 59 | **0** | — |
| Stress, baseline → intervention | 0.216 → 0.273 | 0.205 → 0.262 | — |
| Backlog (months) | 0.09 → 0.21 | 0.07 → 0.19 | — |
| Delivery | 1.01 → 1.01 | 1.01 → 1.01 | — |
| Turnover (12 months) | 11 → 11 | 11 → 11 | — |
| Low-priority work dropped | 0 → 42 | 0 → 39 | — |

What this shows:

* **Different choices, same outcomes.** Laya picked a different action from the rules 86% of the time, yet the effect of
  the intervention — the difference between the two worlds — came out almost identical on every headline measure. In
  this model, organisational physics (capacity, queues, approvals, calibration) drives the outcomes far more than which
  bounded action an individual agent takes.
* **Where Laya differs, it's wording bias.** It chose *reduce quality* 30× more often than the rules and never chose
  *seek help* — the same label bias `LAYA.md` documents, surviving the neutral-state calibration. Never seeking help
  also switches off the cross-team help channel that carries this model's most interesting distant effect.
* **Needle was unusable at this length.** Time per month rose from about 20 s to about 300 s over the run (the
  long-run decode slowdown it was known for). It was removed from the project on the strength of this.
* **The rules are the right default.** They are ~200× faster (which is what makes many-worlds batches and sweeps
  possible), reproducible, and every choice traces to a rule that can be read and changed. Laya stays as an optional
  **sensitivity check**: the admin-cut conclusion surviving a very different decision-maker is itself reassuring.

Caveats: one seed and one intervention, 18 months; a loaded machine inflates the model timings but not their ratio.
And a question this raises rather than answers — if agents' choices barely move the outcomes, individual actions may
be too weakly coupled to results in this model. Real organisations sometimes turn on individual choices; strengthening
that coupling (and re-testing with this comparison) is open work.

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
