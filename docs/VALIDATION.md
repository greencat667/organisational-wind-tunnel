# Validation

## What is verified now
* **Unit/integration tests** (`tests/`, 57 passing): generation sizes; determinism (same seed → identical history);
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
* **Batch sanity** (before the behaviour mechanisms; see *Coupling* below for the current numbers) (32 seeds × 36 months, admin −20%, re-run 2026-09-23): stable 78%, a bottleneck somewhere 22%
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

### After strengthening the coupling (same day)

The "different choices, same outcomes" result turned out to be a model weakness, not a feature: every action was a
one-month nudge. After adding habits, team norms, fatigue and hidden defects (`behaviour.py`, see SIMULATION_MODEL.md)
and fixing approval workarounds that never skipped anything, the same comparison diverges:

| Same world and change, 18 months | Rules | Laya |
|---|---|---|
| Top actions | continue 251 · seek help 86 · delay 28 · overtime 20 | **reduce quality 284** · delay 88 · escalate up 45 |
| Agreement with the rules | — | 11% |
| Errors, baseline → intervention | 16 → 40 | **86 → 128** |
| Backlog (months) | 0.08 → 0.20 | 0.18 → 0.37 |
| Morale | 0.64 → 0.61 | 0.55 → 0.53 |
| Work dropped | 0 → 43 | 0 → 77 |
| Delivery | 1.01 → 1.01 | 0.96 → 0.98 |

Laya's label bias towards *reduce quality* now shows up where it should — errors, hidden defects, morale and a
slower queue — even in the baseline. So engine choice matters now, which makes the advice sharper, not weaker: Laya's
different outcomes come from question-wording bias, not better behaviour. Keep the rules as the default and treat
any engine's results as one assumption about behaviour among several.

## Coupling between choices and outcomes

Measured with `scripts/coupling.py` (five seeds, admin cut, 24 months, last 6 months averaged): the same worlds
run under deliberately extreme decision policies. "Spread" is the spread across policies divided by the spread across
seeds — above 1, how agents cope matters more than luck.

| Intervention world | Rules | Nobody acts | Always cut corners | Always seek help | Always overtime | Spread |
|---|---|---|---|---|---|---|
| Backlog (months) | 0.35 | 0.74 | 0.59 | 0.66 | 0.33 | 0.7 |
| Stress | 0.30 | 0.43 | 0.38 | 0.40 | 0.33 | 0.6 |
| Errors (last 6 months) | 39 | 53 | **135** | 49 | 42 | 2.9 |
| Hidden defects surfacing | 3 | 0 | **119** | 0 | 0 | 9.8 |
| Fatigue | 0.03 | 0 | 0 | 0 | **0.12** | 4.3 |
| Delivery | 0.99 | 0.97 | 0.94 | 0.98 | 1.00 | 1.2 |

Before the behaviour mechanisms, "always cut corners" was indistinguishable from the rules on backlog and stress and
had only ~1.6× their errors; there were no defects or fatigue to measure. One person: switching off the Finance
manager's decisions adds ~0.7 months to Finance's backlog and 0.2 to its stress; one ordinary Finance officer's
choices move their team's numbers only slightly (see LIMITATIONS.md). Turnover responds to strain through the exit
hazard — under the "nobody acts" policy expected exits rise ~20%, concentrated in the strained teams, where someone at
breaking point is ~5× likelier to leave than a calm colleague — but organisation-wide turnover moves less than the other
measures.

Admin-cut batch after these changes (32 worlds × 36 months): stable 41% (was 78%), a bottleneck somewhere 47% (Finance
28%, Business Support 25%), turnover up 41% (was 12%), delivery down >10% in none. The distant effect is now behavioural:
the protected Programme Delivery team develops an **overtime norm in 44% of worlds** (median lag ~19 months), followed by
fatigue (28%), stress (41%) and turnover (47%).

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
