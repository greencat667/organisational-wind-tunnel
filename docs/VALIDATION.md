# Validation

## What is verified now
* **Unit/integration tests** (`tests/`, 24 passing): generation sizes; determinism (same seed → identical history);
  fork without intervention stays identical; capacity arithmetic (nobody works beyond contracted + overtime cap);
  work cannot be completed twice; terminated employees hold no work; queues grow when arrivals exceed capacity;
  budget freeze blocks hiring; the admin-cut plan removes admin posts, protects frontline and wires causes to the
  intervention root; team merge and layer removal; causal chains reach the root; target aliases; AI agent capacity;
  export; heuristic probabilities; recorded replay; cache keys; confidence routing; adapter fallback; rule parser on all
  shipped scenarios; flat Apple FM output validation; SQLite round trip.
* **Baseline stability** across seeds (see SIMULATION_MODEL.md).
* **Common random numbers**: with no intervention, baseline and fork are identical for 12+ months.
* **Batch sanity** (32 seeds, admin −20%): stable 75%, workload-transfer cluster 22%, bottleneck 12.5%;
  Programme Delivery backlog diverged in 53% of worlds with a median lag of 19 months — a distant, unscripted effect.

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
