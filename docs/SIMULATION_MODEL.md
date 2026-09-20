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
* **Queueing.** Each team works its queue in priority → age order. Any member with the stage skill ≥0.2 can work an item;
  speed = 0.55 + 0.45 × proficiency. Items can be worked by several people in a month. If nobody has the skill the
  item stalls. Priority-3 items more than 3 months past deadline are *dropped* (counted as lost work).
* **Errors.** P(error) = 0.02 + 0.08·max(0, stress−0.55) + 0.05·max(0, workload−1.1) + 0.04 if onboarding + 0.06 if
  cutting corners + 0.05 if the approval was bypassed. An error sends 40% of the stage hours back as rework.
* **Approvals** need a manager (or a grade ≥5 senior, or team autonomy ≥0.75 for self-approval) with spare management
  hours; otherwise the item waits and `approvals_waiting` grows. Workarounds skip the approval stage at higher error risk.

## Capacity (organisational physics)
* 150 contracted hours/month; 92% productive. Managers spend 15 h + 3 h per direct report on management (capped at 80%);
  directors 60%; seniors (grade ≥5) 8 h approving. Effective hours × effectiveness, where effectiveness =
  onboarding ramp (0.4→1 over 4 months) × (1 − 0.2·max(0, stress−0.65)) × (0.85 + 0.15·morale) × effort level.
* **Absence:** monthly probability 0.02–0.05 baseline + 0.10·max(0, stress−0.6); duration 10–100% of the month.
* **Overtime:** only via a decision; ≤20 h/month; paid at 1.25× when the manager has approved it; raises stress.
* **Recruitment:** vacancies open only if the department is not frozen and salary spend ×1.05 < budget; lead time
  3 months (+1–2 if the HR-capable team is overloaded); recruitment creates a real people-case work item; new hires
  onboard for 4 months. Restructured teams have hiring frozen for 6 months.
* **Budget:** team budget = pay × 1.18. Departments freeze hiring when projected annual spend > budget (hysteresis 0.97).
* **Automation / AI agents:** see [AI_SCENARIOS.md](AI_SCENARIOS.md) — agent pools with supervision coverage, learning, drift,
  exceptions, silent errors surfacing downstream, incidents, skill atrophy, attrition-based downsizing, delegated approvals.

## Psychology (bounded, monthly)
* stress → target 0.15 + 0.5·max(0, workload−0.9) + 0.15·overtime/20 + 0.2·max(0, backlog months−0.6) +
  0.1·(1−manager availability) − 0.05·(morale−0.5) − adaptability relief; adapts 35%/month.
* morale → target 0.72 − 0.35·stress + 0.15·(trust−0.5) + 0.1·(team morale − own) + 0.2·memory valence + …; adapts 25%/month.
* turnover intention → 0.03 + 0.5·max(0, stress−0.5) + 0.45·max(0, 0.5−morale) + 0.1·(1−commitment) + 0.1·job market −
  0.1·institutional knowledge …; the `leave` action becomes *available* above 0.2.
* **Memory** traces (restructure −0.35, colleague left −0.3, overload −0.15, manager support +0.15, escalation ignored
  −0.2, successful collaboration +0.2 …) decay 10%/month → path dependence.
* **External exits:** a seeded hazard of 0.7%/month × (1 + 3·turnover intention) × (0.5 + job market) ≈ 8–12%/year at
  baseline. Not an AI decision.

## Information
Packets (announcements on restructure, rumours when someone leaves) spread along informal ties with probability
0.35 × (0.5 + collaboration tendency) per holder per month; `share_information` decisions spread them deliberately.
Negative packets leave small memory traces. Reach is measured, not assumed.

## Events and causality
Every state change of consequence emits an `Event(kind, actor, entities, before, after, causes)`. Causes are wired at
the point of change: decisions cite their triggers; transfers cite the decision; threshold crossings cite recent
capacity/staffing/transfer events for that team; departures cite the person's recent negative experiences.
The intervention is a root event; `analysis.causal_orders` gives BFS distance; `why()` reconstructs a chain.
`emergent` is set on systemic events that hit entities outside the intervention's targets.

## Time
One tick = one month. Order: interventions → arrivals → people flow (exits, hires, onboarding) → absence & capacity →
decisions → work processing → psychology & network → information → finance → metrics/threshold events → frame.

## Measured baseline behaviour (prototype, heuristic engine, 36 months, seeds 7/11/23/42)
backlog 0.04–0.06 months, worst team 0.19–0.37, delivery 0.75–0.78, turnover 6–8/year, headcount 99–102 — stable.
