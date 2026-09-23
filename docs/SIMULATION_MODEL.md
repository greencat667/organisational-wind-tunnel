# Simulation model

All parameters live in `backend/windtunnel/config.py` (`SimConfig`) and `orggen.py`. Everything below is an
*assumption of the model*, chosen to be plausible and internally consistent — not an empirical claim.

## Organisation
* **Templates.** `prototype`: 100 people, 8 teams, 6 departments (Executive, Finance, Business Support, Operations,
  Fundraising, Communications, Programme Delivery, Technology). `charity500`: ~500 people, 27 teams, 11 departments.
* **Employees** carry fixed bounded traits (change tolerance, risk tolerance, collaboration, escalation, autonomy,
  institutional knowledge, adaptability; one of six archetypes shifts their means) and dynamic state (workload,
  stress, morale, engagement, trust in management, commitment, turnover intention, absence probability, memory,
  informal ties). Skills are proficiencies 0–1: a primary skill (0.6–0.95), secondary team skills (0.35–0.75), and for
  ~35% a cross-functional skill (0.2–0.5). Grades map to salaries (£22k–£78k). 15% are part-time (0.6 FTE).
* **Reporting.** Officers → team manager → director (Executive team) → chief executive.
* **Informal network.** Dense within teams (45% of pairs), sparse along process paths. Ties strengthen when someone
  successfully seeks help (+0.25) and decay 1.5%/month.

## Work
* **Processes** are stage graphs (team, required skill, hours mean/sd, approval?, routine share). The prototype has 14
  (procurement, invoices, grants, service delivery, campaigns, support, reporting, supporter enquiries, logistics,
  operations, design, data, people cases, payroll). Approval stages consume *management* hours, not officer hours.
* **Arrivals** are Poisson per process per month, calibrated so each team starts near a target utilisation:
  admin 0.84, support 0.76, frontline/income/technology 0.74 (back offices run hotter, a documented assumption).
  High-volume processes are bundled into batch items (≤60 items/process/month) so the visual world stays legible.
* **Allocation.** At the start of each month the team's queue is *allocated to people*: each item (priority → age) goes to
  the skilled member with the lowest load ratio, sticky for items already in progress; items bigger than ~35% of a
  person's month are shared in chunks. **Personal workload = allocated hours / own capacity**, so overload concentrates on
  individuals, key people emerge, and managers' `redistribute_work` rebalances the allocation before offloading to neighbours.
  Nobody is planned more than `max_allocation_ratio` (2.0) months of work in a month — the rest waits in the team queue —
  so personal workload measures this month's load, not the size of the backlog. Work the team's AI agents are expected to
  take is reserved first and never planned onto people.
* **Queueing.** Processing follows the allocation: the owner works first, colleagues with spare hours help. Any member with
  the stage skill ≥0.2 can work an item; speed = 0.55 + 0.45 × proficiency. If nobody has the skill the item stalls.
  Priority-3 items more than 3 months past deadline are *dropped* (counted as lost work), whether queued or half-done.
  `delay_low_priority` only moves items to the back of the queue; it never moves deadlines. An item whose next stage is
  on the same team stays in that team's queue (an earlier bug silently dropped ~23% of frontline work this way).
* **Helping.** A neighbouring team (shared process) with workload <0.9 can take items if it provides the skill or any
  active member has it at ≥0.3; transferred items without the exact team skill take 25% longer.
* **Errors.** P(error) = 0.02 + 0.08·max(0, stress−0.55) + 0.05·max(0, min(workload, 2)−1.1) + 0.04 if onboarding +
  0.06 if cutting corners + 0.05 if the approval was bypassed, capped at `max_error_probability` (0.25). An error sends
  40% of the stage hours back as rework. (Uncapped, a deep queue drove error rates towards 0.85 and a rework spiral.)
* **Approvals** need a manager (or a grade ≥5 senior, or team autonomy ≥0.75 for self-approval) with spare management
  hours; otherwise the item waits and `approvals_waiting` grows. Workarounds skip the approval stage at higher error risk.

## Capacity (organisational physics)
* 150 contracted hours/month; 92% productive. A manager's management time is sized for the team the role was designed
  for (15 h + 3 h per designed report, plus a calibrated approval allowance; capped at 80%) and doesn't shrink when
  reports leave. Line management itself needs 6 h + 1.5 h per *current* report; the rest is approval/decision time, so
  losing officers frees approval time and growing past the design squeezes it. Directors spend 60%; seniors (grade ≥5)
  8 h approving. **Management load** = (line management + approvals done or waiting + escalations) ÷ all management
  time — no fixed offset. Calibration sizes each team's approval allowance so its approvals run at ~80% of the time left
  after line management (the old calibration sized only work stages, so Finance's approvals alone exceeded its
  management time and it read "overloaded" before any intervention). Effective hours × effectiveness, where effectiveness =
  onboarding ramp (0.4→1 over 4 months) × (1 − 0.2·max(0, stress−0.65)) × (0.85 + 0.15·morale) × effort level.
* **Absence:** monthly probability 0.02–0.05 baseline + 0.10·max(0, stress−0.6); duration 10–100% of the month.
* **Overtime:** only via a decision; ≤20 h/month; paid at 1.25× when the manager has approved it; raises stress.
* **Recruitment:** vacancies open only if the department is not frozen and salary spend ×1.05 < budget; lead time
  3 months (+1–2 if the HR-capable team is overloaded); recruitment creates a real people-case work item; new hires
  onboard for 4 months. Restructured teams have hiring frozen for 6 months. A leaver who can't be replaced because of a
  freeze or budget is remembered as a blocked backfill and the vacancy opens once the block lifts.
* **Budget:** team budget = pay × 1.18. Departments freeze hiring when projected annual spend > budget (hysteresis 0.97).
* **Automation / AI agents:** see [AI_SCENARIOS.md](AI_SCENARIOS.md) — agent pools with supervision coverage, learning, drift,
  exceptions, silent errors surfacing downstream, incidents, skill atrophy, attrition-based downsizing, delegated approvals.

## Psychology (bounded, monthly)
* stress → target 0.15 + 0.5·max(0, workload−0.9) + 0.15·overtime/20 + 0.2·max(0, backlog months−0.6) +
  0.1·(1−manager availability) − 0.05·(morale−0.5) − adaptability relief + 0.3·fatigue; adapts 35%/month.
* morale → target 0.72 − 0.35·stress + 0.15·(trust−0.5) + 0.1·(team morale − own) + 0.2·memory valence + …; adapts 25%/month.
* turnover intention → 0.03 + 0.6·max(0, stress−0.35) + 0.45·max(0, 0.5−morale) + 0.1·(1−commitment) + 0.1·job market −
  0.1·institutional knowledge + 0.25·fatigue …; the `leave` action becomes *available* above 0.2, and its pull rises with
  stress and fatigue.
* **Memory** traces (restructure −0.35, colleague left −0.3, overload −0.15, manager support +0.15, escalation ignored
  −0.2, successful collaboration +0.2 …) decay 10%/month → path dependence.
* **External exits:** a seeded hazard of 0.56%/month × (1 + 8·turnover intention) × (0.5 + job market) ≈ 8–12%/year at
  baseline — the same as before the September 2026 rebalance (0.7% × (1 + 3·intention)), but someone at breaking point
  (intention 0.6) is now ~5× likelier to leave than a calm colleague, not ~2×. Not an AI decision.

## How choices outlast the month (`behaviour.py`)
Every agent action used to be a one-month nudge, so choices washed out: the rules and a model making different choices
86% of the time produced the same outcomes. Four mechanisms now carry a choice forward in time or out to other people,
and each records the decision that started it, so WHY chains lead back to a person:

* **Habits.** Cutting corners and working overtime persist for up to 3 months without a fresh decision while the person
  is still under pressure (workload ≥ 0.95). An overtime habit also ends once fatigue reaches 0.35.
* **Team norms.** Each team tracks how much of it is cutting corners, working overtime, bypassing approvals and asking
  for help: a slow-moving (25%/month) share, weighted by influence — the manager and informal hubs count for more than a
  newcomer. Norms raise the rules' pull towards the same behaviour (social proof) and are in Laya's context too. A norm
  passing 0.3 is a timeline event ("Cutting corners is becoming normal in Finance") caused by the people doing it.
* **Fatigue.** A month at the overtime cap adds 0.12 fatigue; fatigue keeps 80% a month (≈0.6 if sustained). It raises
  stress, absence, the wish to leave and the pull to resign, and lowers the pull to work more overtime.
* **Hidden defects.** A stage finished while cutting corners hides a defect 20% of the time; an approval skipped by a
  workaround lets one through 15% of the time. It surfaces at the next stage as rework (half the stage's hours, on
  whichever team that is), or after delivery as a priority-1 correction next month — attributed to the decision. Cutting
  corners also costs committed people a little morale.

Two fixes went with this: approval **workarounds now actually skip the approval** (moving an item cleared the flag
before it reached the approval, so "bypassed approvals on 3 items" changed nothing), and the rules' **pressure is capped
at 2** (uncapped, coping options dwarfed everything else in a badly backed-up team, so even someone at breaking point
never chose to resign).

## Information
Packets (announcements on restructure, rumours when someone leaves) spread along informal ties with probability
0.35 × (0.5 + collaboration tendency) per holder per month; `share_information` decisions spread them deliberately.
Negative packets leave small memory traces. Reach is measured, not assumed.

## Interventions are phased
Every additive change (capacity, budget, hours, agents, automation, role conversion) is spread evenly over the transition
period in 2–6 steps; demand changes compound geometrically to the stated total. "Demand doubles over two years" therefore
grows ~12% every ~5 months rather than doubling next month.

## Events and causality
Every state change of consequence emits an `Event(kind, actor, entities, before, after, causes)`. Causes are wired at
the point of change and **only state-changing kinds may be cited** (staffing, capacity, transfers, agents, incidents,
demand, protection, cancellations, overload of a person) — never routine decisions. Threshold events record numeric
before/after (backlog months, capacity hours, headcount, management load) so a WHY chain reads as deltas, and a person's
departure cites what happened *to* them (overload, ignored escalations, absence, role change).
The intervention is a root event; `analysis.causal_orders` gives BFS distance; `why()` reconstructs a chain.
`emergent` is set on systemic events that hit entities outside the intervention's targets.

## Time
One tick = one month. Order: interventions → arrivals → people flow (exits, hires, onboarding) → absence & capacity →
decisions → work processing → psychology & network → information → finance → metrics/threshold events → frame.

## Slack presets
`SimConfig.target_utilisation` (UI: slack 0.65 · normal 0.75 · lean 0.85) sets how stretched the organisation starts;
admin teams run ~12% hotter than the target. A utilisation sweep of the admin cut (12 worlds each): at 0.65, 92% of worlds
stay stable; at 0.85, none do and median backlog reaches 2.3 months — the intervention's outcome depends on slack more than
on anything else in the model.

## Measured baseline behaviour (prototype, heuristic engine, 36 months, seeds 5/7/11/23/42)
Re-measured 2026-09-23 after the lost-work and management-time fixes: backlog 0.07–0.17 months, delivery 0.97–1.04 (the
old 0.75–0.78 was the lost-work bug, not the organisation), turnover 7–9/year, mean personal workload 0.77–0.93,
management load 0.41–0.49 (every team <1.0), cooperation (items passed to neighbouring teams) 90–160 over the run, no
orphaned work items — stable. After the behaviour mechanisms (same day): worst-team backlog ≤0.5 months on seeds
6/7/11/23/42, delivery 0.97–1.02, turnover 7–10/year. Seed 5 is a knife-edge world — its Programme Delivery team is
generated at ~100% utilisation, so its backlog wanders (to 1.7 months before these changes, ~2 after).
