# Brief — Organisational Wind Tunnel (project 065)

Received 2026-09-20. Condensed from the full prompt; the prompt's section numbers are kept for reference.

## Core idea
An AI-powered 3D organisational wind tunnel: an agent-based simulation of an organisation as a living system. The user types a natural-language intervention ("Reduce administrative capacity by 20% while protecting frontline delivery"), a local model interprets it into a structured, validated change plan, the plan is applied to a copy of the organisation, and simulated employees/managers/teams respond over months and years. **Do not script consequences** — the intervention changes the environment, agents respond, their responses alter the environment, system effects emerge.

## Layers (1) — must stay separated
User intervention → Apple Foundation Model (interpret; explain; summarise — never decides outcomes) → structured change plan → simulation (time, workload, money, capacity, queues, reporting, vacancies, skills, projects, dependencies, processes, absence, turnover, recruitment, information flow, constraints) → Laya/Needle agents (bounded decisions: cooperate/resist/escalate/delay/delegate/seek_help/find_workaround/share_information/protect_budget/reduce_quality/work_overtime/apply_for_internal_job/leave/automate_task/hire/cancel_activity) → deterministic system rules → updated organisation → next month.

## Fully local (2)
No cloud AI APIs. Apple Silicon Mac, 16 GB baseline. Browser UI on localhost; local Python backend (FastAPI + WebSocket), simulation engine, Apple FM, Laya/Needle, SQLite. Other local tech allowed if superior — document why.

## Verify APIs first (3)
Apple Foundation Models, Laya (github.com/NandhaKishorM/laya), Cactus Needle (cactuscompute.com/needle). Use current documented interfaces; hide each behind adapters.

## Decision engine abstraction (4)
`AgentDecisionEngine.decide(agent_state, local_context, available_actions) -> AgentDecision` with LayaDecisionEngine, NeedleDecisionEngine, HeuristicDecisionEngine, RecordedDecisionEngine. Simulator must run with no AI model.

## Apple FM role (5)
Natural language → constrained structured intervention (type, effective date, objectives, changes[target/operation/amount], protected groups, transition months). Strongly validated schema. Must not invent outcomes.

## Organisation model (6–11)
Graph: employees, teams, departments, roles, projects, processes, suppliers, resources; edges reports_to, works_with, depends_on, provides_service_to, shares_information_with, approves, manages, supplies. Persistent employee agents with structured state (grade, salary, hours, skills, workload, capacity, stress, morale, engagement, autonomy, influence, trust, commitment, change/risk tolerance, manager, relationships, tasks, absence prob, turnover intention, memory). Bounded individual differences. Teams track capacity, incoming/completed work, backlog, skill coverage, management capacity, vacancies, morale, turnover. **Work items physically flow** (origin, destination, priority, complexity, required skills, dependencies, deadline, status) through **process graphs** (request → team → manager approval → finance → procurement → supplier). Removing capacity creates queues elsewhere.

## Time (12)
Monthly strategic steps; enough intra-month activity to update workload, queues, projects, costs, morale, absence, turnover, information, relationships. Speeds: 1 month/s, 6 months/s, 1 year/s, max, pause, step.

## Decisions (13–16)
Compact local context only (personal, team, manager, relationships, relevant work, recent changes/events). Laya: noul/choice/score questions. Needle: constrained tool set modifying only simulation state. Event-driven triggers (overload, manager change, staff loss, new task, deadline, budget, restructure, colleague leaves, promotion, conflicting instructions, new tech, process failure) plus monthly periodic decisions.

## Memory, information, managers (17–19)
Decaying employee memory of significant events (path dependence). Information packets (announcement, rumour, update, warning, feedback, decision, financial) that agents read/ignore/share/escalate/act on. Managers are agents with finite capacity (reprioritise, redistribute, approve overtime, request recruitment, protect team, escalate, cancel, reorganise, share).

## Change & shocks (20–21)
Composable primitives: headcount ±, merge/split teams, remove/add management layer, centralise/decentralise, budget ±, introduce AI, automate process, change reporting lines, working hours, demand ±, outsourcing/insourcing, new strategy, add/remove approval process. Shocks modify environment variables only.

## Effects & causality (22–23)
Effect tracing by causal propagation: first/second/third order. Causal event graph (timestamp, actor, action, state before/after, causes, affected entities). "WHY DID THIS HAPPEN?" reconstructs the chain.

## 3D world (24–28)
Three.js / React Three Fiber. Not floating cards, not a 3D org chart. Tron × digital twin × systems map × Mini Metro × strategy game × living organism, restrained for senior leadership. Teams as spatial clusters, departments as districts, employees as instanced luminous points/figures whose state subtly changes appearance (pulse, jitter, dim, detach). Work items visibly move along process paths; queues visibly accumulate. Information as smaller pulses.

## Health & UI (29–35)
Dimensions, not a single score. 3D dominates; dashboard supports. Intervention input → INTERPRETED CHANGE (RUN / EDIT / CANCEL) → fork into BASELINE vs INTERVENTION with identical seeds → split universe (side-by-side / overlay / difference). Time scrubber; event timeline generated from state.

## Analysis (36–43)
Emergence detector (EMERGENT EFFECT labels), formal vs informal network, key-person dependency measured not pre-labelled, organisational physics (capacity, queueing, skills, budget, management attention, communication paths, recruitment lag, onboarding, automation implementation effort), no magical employees, multiple runs (1,000 organisations, no rendering, distributions as in-model frequencies, never real-world probabilities), outcome clusters with descriptive names, "find unexpected consequences" with causal trace.

## Inspection (44–46)
Decision inspector (probabilities, actual action, engine used), agent replay, confidence routing (high → execute, medium → probabilistic, low → conservative heuristic; configurable).

## Engineering (47–64)
Deterministic rule engine for money/hours/queues/permissions. Import CSV/JSON later (no names required). Privacy first; synthetic default; local only. Ship ~500-employee synthetic org (Executive, Finance, Operations, Fundraising, Communications, Technology, People, Policy, Campaigns, Programme Delivery, Customer/Support) and scenarios (Admin cut, AI automation, Flatten structure, Funding shock, Rapid growth). Watch mode (cinematic), camera modes incl. FOLLOW THE CONSEQUENCES, X-ray modes (structure/work/information/capacity/cost/change/dependencies), graph metrics, simulation core separate from renderer and batch runner, reproducibility (seed, versions, engine, intervention, decisions, events), decision cache visible in diagnostics, archetypes, SQLite, save/load/fork/export, debug panel (tick time, evaluations, cache hits, Laya/Needle/AFM latency, memory, FPS).

## Compare engines (65), limitation notice (66), validation (67)
Same org/intervention/seed across Laya, Needle, heuristics: latency, throughput, memory, diversity, divergence, confidence, stability. Show clearly: exploratory simulation, not prediction. Later: historical validation with calibration/validation split.

## First vertical slice (68) and critical demo (69)
100 synthetic employees, 8 teams, reporting relationships, cross-team dependencies, real work items, queues, capacity, workload, morale/stress, monthly simulation, Laya + Needle + heuristic engines, Apple FM parser, Three.js world with animated employees and work flow, time controls, employee + team inspector, event timeline. One intervention: reduce admin capacity by 20%; baseline vs intervention for 36 months. Then FIND SECOND-ORDER EFFECTS → click → WHY DID THIS HAPPEN?

## Quality bar (70–76)
Dark cinematic, excellent typography, subtle lighting, minimal chrome, high-quality motion; GPU instancing. Optional sound off by default. Automated tests for capacity arithmetic, queues, budgets, determinism, intervention application, employee movement, process dependency, event causality, save/load, adapter fallback, plus invariants. Work autonomously: implement → run → inspect → simulate → fix → profile. Docs: README, ARCHITECTURE, SIMULATION_MODEL, AGENT_DECISIONS, LAYA, NEEDLE, APPLE_FOUNDATION_MODELS, VALIDATION, PRIVACY, LIMITATIONS. Guiding principle: prefer better simulation mechanics over AI cleverness.

## Success criteria (75)
One command → browser → living 3D org → type "Reduce administrative capacity by 20%" → interpreted locally → fork → advance → watch agents respond → workload moves → unexpected effects emerge → click → causal trace → rewind → change → rerun → batch hundreds/thousands without rendering → compare distributions. "I changed one thing over here — and eighteen months later something happened over there."

## Addendum (2026-09-20, from Christian) — AI-impact scenarios
Eventually simulate the impact of AI on the organisation across a range of scenarios, e.g.:
- the organisation decides to mostly automate the back end;
- more roles become supervisory over teams of AI agents;
- AI starts running some workflow loops itself.
Design implication: model AI agents as a non-human capacity pool attached to teams (capacity, supervision hours per agent, exception rate routing failures back to humans, implementation lag, running cost), role conversion (doing → supervising), and process stages executable by an AI loop with human escalation. These are composable primitives, not separate simulations.
