# Agent decisions

## Abstraction
```python
class AgentDecisionEngine:
    def decide(self, request: DecisionRequest) -> AgentDecision   # sync; adecide() async wrapper
```
`DecisionRequest` = compact agent state + local context + `available_actions` (already constrained by the World) +
targets + triggers. `AgentDecision` = probabilities over the available actions, confidence, engine name, latency,
target, auxiliary scores (effort, turnover pressure), raw model output (for replay).

Engines: `HeuristicDecisionEngine` (rules → softmax), `LayaDecisionEngine`, `NeedleDecisionEngine`,
`RecordedDecisionEngine` (replays a decision log; falls back to rules), all wrappable in `CachedDecisionEngine`.
If an engine raises, the World uses the heuristic engine and flags `fallback`. **The simulator always runs.**

## Event-driven triggers (not every employee every month)
overload (workload > 1.15) · team_backlog_high (> 1 month) · colleague_left · restructure · deadline_pressure ·
low_morale (< 0.35) · turnover_pressure (> 0.3) · manager_changed · periodic (8% sample). Managers are evaluated
when their team is under pressure or after staffing/structural events. Cap: 60 evaluations/month (24 for AI engines),
≤8 per team, managers first.

## Context compression
`context.build_request` produces ~30 short lines: role, team, workload, stress, morale, trust, turnover intention,
traits, tenure, archetype; team workload/backlog/headcount/vacancies; manager availability; own tasks (urgent,
overdue); neighbours with spare capacity; up to three recent changes; whether the person holds unshared information.
Managers also get team spread, vacancy budget, freeze, transfers in, frontline share waiting, automation programme.
No names of other people, no full org.

## Bounded actions
Employees: continue_as_normal, seek_help(team), work_overtime, delay_low_priority, escalate_workload, use_workaround,
reduce_quality, share_information, apply_for_internal_job(team), leave.
Managers: redistribute_work, request_recruitment, approve_overtime, protect_team, cancel_low_priority, escalate_up,
reprioritise, automate_task, share_information, pause_ai_agents, expand_ai_agents, retrain_staff.
Employees with AI agents in their team also get verify_ai_output.
Availability is decided deterministically by the World (no helpers with spare capacity → no seek_help; no vacancy
budget → no recruitment; turnover intention < 0.2 → no leave). Effects live in `primitives.apply_action`.

## Confidence routing (configurable)
≥ 0.75 execute argmax · 0.5–0.75 sample from the distribution · < 0.5 sample from 0.6·rules + 0.4·model.
Then downgrade-only **guards** grounded in state (workaround without urgency, quality cut without overload, leaving
without intention, overtime without demand) can turn an action into continue_as_normal; the guard is logged.

## Decision cache
Key = agent kind + archetype-bucketed state/context + sorted available actions + triggers (identity and free text
excluded). Hits, misses and hit rate are shown in the dev panel. Recorded decisions can be replayed month-for-month.

## Inspector and replay
Every decision is logged with its triggers, available actions, probabilities, confidence, route, cache/fallback flags,
latency, the exact state text the model saw, and the raw model output. The employee inspector shows the latest one;
REPLAY DECISIONS lists the history.
