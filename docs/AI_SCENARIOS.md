# AI-impact scenarios

The wind tunnel models AI in the organisation as **composable primitives with organisational physics**, not as separate
scripted simulations. Three scenarios ship as chips in the prompt bar; any mix can be typed in plain English.

| Chip | Prompt | Primitives |
|---|---|---|
| Automate back end | *Automate the back office: deploy AI agents to take 70% of routine finance, HR and administrative work over 6 months, and do not replace leavers in those teams.* | `deploy_ai_agents(admin, 0.7, replace_leavers=False)` |
| Supervisory roles | *Convert half of the administrative and finance roles into supervisors of AI agent teams, with agents handling 80% of routine work.* | `deploy_ai_agents(admin, 0.8)` + `convert_to_supervisory(admin, 0.5)` |
| AI workflow loops | *Let AI run the procurement, invoicing and expenses workflows end to end for 80% of cases, with humans handling exceptions and approvals.* | `ai_run_process([procurement, invoice, payroll], 0.8)` |
| AI loops + approvals | *… including approvals, with humans handling exceptions only.* | `ai_run_process(…, delegate_approvals=True)` |

## Mechanics (`backend/windtunnel/ai.py`)

**Agent pool.** A team can hold *agent-equivalents*. Each supplies 120 productive hours/month for £900/month and takes
eligible items first: non-approval stages whose routine share ≥ 0.4 (or any stage of an AI-run process); priority-1 items
only if `handles_urgent`. Agents go live after an implementation lag (3–4 months) and implementation is **real work**:
60 h per agent on the target team plus 25 h per agent on the Technology team (a work item on their queue).

**Supervision.** Agents need human supervision: 12 h per agent per month at supervision skill 0, falling to 6 h at
skill 1. Supervisors (converted or retrained officers) cover it first, up to 90% of their time; other officers cover the
remainder with at most 25% of theirs. *Coverage* = hours covered / hours needed. Agents only deliver `capacity × coverage`
and, unsupervised, they **drift**: exception rate × (1 + 0.8·(1 − coverage)).

**Exceptions.** Each AI-handled item fails with the current exception rate and returns to humans at half the stage hours
(a visible magenta hop in the 3D world). Rate = base 0.16 × learning (0.45 + 0.55·e^(−months live/9)) × drift × 2 during an
incident. Exceptions land on staff whose routine practice is shrinking, so they are slower at them (see atrophy).

**Silent errors.** 4% of AI-handled items (× (2 − coverage), halved when a colleague chose *verify AI output*) pass as done
but carry a hidden defect. It **surfaces at the next stage** — the downstream team pays 35% extra hours, logs an error and
an `ai_quality_leak` event whose cause is the originating team's agents — or, on a final stage, comes back a month later as
a priority-1 *correction*. This is how AI in Finance shows up as errors in Executive reporting 15 months later.

**Incidents.** 3%/month per team with live agents: agents offline for the month, exception rate doubled, negative memory
trace for the team. Managers may respond by pausing agents; officers by verifying output.

**Skill atrophy.** When agents cover ≥ 50% of a skill's routine hours, officers lose 0.012 proficiency/month in the team's
primary skill (floor 0.4) and institutional knowledge erodes; supervisors gain supervision skill with practice. The
**deskilling index** is the mean primary-skill drop among officers in teams with agents.

**Attrition-based downsizing.** With `replace_leavers=False`, a leaver's post is not backfilled while agents cover the
work (`post_not_replaced` events); half the saved salary is banked, half assumed to fund agents. Turnover in small admin
teams is low, so this shrinks headcount slowly — an honest, unscripted finding.

**Delegated approvals.** In an AI-run process the AI may approve non-urgent items (twice the silent-error chance). Kept
human, approvals become the constraint when the rest of the loop speeds up (`approval_bottleneck`).

**Role conversion.** Converted staff become `supervisor`s (adaptable people first), gain `ai_supervision` skill and
+0.1 autonomy; their memory trace is positive or negative depending on change tolerance; colleagues not converted get a
small negative trace; a rumour/announcement packet spreads. New hires into a converted team keep the role mix.

## New bounded actions
Employees: `verify_ai_output` (10% of capacity; halves silent errors). Managers: `pause_ai_agents` (one month),
`expand_ai_agents` (+20%, needs low exceptions and coverage), `retrain_staff` (two officers → supervisors, 20 h each).
Triggers: `ai_introduced`, `ai_incident`, `ai_exceptions_high`, `supervision_gap`.

## Measured (prototype org, heuristic engine, 24 seeds × 36 months, frequencies *within the model*)
| Scenario | Stable | Net cost saving | Hidden defects > 3/month | Deskilling | Approval bottleneck | Automation recovery |
|---|---|---|---|---|---|---|
| Automate back end (no backfill) | 88% | 63% | 100% | 0% | 25% | 21% |
| Supervisory roles | 96% | 0% | 100% | 4% | 0% | 0% |
| AI loops + delegated approvals | 92% | 0% | 100% | 0% | 0% | 0% |
| *(reference: Admin −20%, no AI)* | 50% | 79% | – | – | – | – |

(Re-measured after per-person work allocation was introduced; the admin cut now bites harder because overload concentrates
on individuals.) Distant effects that recur: **Executive errors** (AI-processed finance reporting leaking defects into
executive approval) in 92–96% of worlds with a ~31 month lag; Programme Delivery backlog divergence in 67–83% with a
15–18 month lag; Communications error rises around month 24. Use `scripts/batch_cli.py --sweep ai_base_exception_rate=0.08,0.16,0.3`
(or any `SimConfig` field) to see how sensitive these are to the guessed constants. Cost savings appear only where posts are actually removed —
agents plus their supervision and exceptions cost about what the routine work cost.

## Assumptions to challenge
Hours per agent, cost per agent, supervision hours, base exception and silent-error rates, incident probability, learning
time constant and atrophy rate are all in `SimConfig`/`Team` defaults and are guesses. Change them and re-run the batch.
