"""Core data model for the organisational simulation.

Everything here is plain dataclasses so that a World can be deep-copied (forking),
serialised to JSON (snapshots / export) and diffed (baseline vs intervention).

These variables are *simulation parameters*, not claims about real people.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# ----------------------------------------------------------------------------
# Organisation graph nodes
# ----------------------------------------------------------------------------


@dataclass
class MemoryTrace:
    month: int
    kind: str          # restructure | overload | colleague_left | manager_support | broken_promise | success | budget_cut ...
    valence: float     # -1 .. +1
    weight: float      # decays each month


@dataclass
class Employee:
    id: str
    name: str
    role: str                     # role id, e.g. "ops_officer"
    role_title: str
    team_id: str
    dept_id: str
    grade: int
    salary: float                 # annual
    contracted_hours: float       # per month
    skills: dict[str, float]      # skill -> proficiency 0..1
    experience_months: int
    is_manager: bool = False
    manager_id: Optional[str] = None

    # bounded individual differences (fixed traits, 0..1)
    change_tolerance: float = 0.5
    risk_tolerance: float = 0.5
    collaboration_tendency: float = 0.5
    escalation_tendency: float = 0.5
    autonomy: float = 0.5
    institutional_knowledge: float = 0.5
    adaptability: float = 0.5
    archetype: str = "steady"

    # dynamic state (0..1 unless noted)
    workload: float = 0.0         # assigned hours / capacity hours (ratio)
    capacity_hours: float = 0.0   # effective productive hours this month
    hours_worked: float = 0.0     # hours actually spent on work items this month
    overtime_hours: float = 0.0
    stress: float = 0.2
    morale: float = 0.7
    engagement: float = 0.7
    influence: float = 0.3
    trust_management: float = 0.6
    commitment: float = 0.6
    absence_probability: float = 0.03
    absent_fraction: float = 0.0  # fraction of this month absent
    turnover_intention: float = 0.05
    onboarding_months_left: int = 0
    effort_level: float = 1.0     # multiplier from decisions (0.7..1.15)

    relationships: dict[str, float] = field(default_factory=dict)  # informal ties
    memory: list[MemoryTrace] = field(default_factory=list)
    active_tasks: list[str] = field(default_factory=list)  # work item ids currently assigned

    status: str = "active"        # active | leaving | left
    hired_month: int = 0
    leaving_month: Optional[int] = None
    left_month: Optional[int] = None
    current_behaviour: str = "working"
    role_kind: str = "officer"        # officer | supervisor (of AI agents) | manager
    skill_at_start: dict[str, float] = field(default_factory=dict)   # for the deskilling index
    last_decision_month: int = -1
    help_requests_received: int = 0
    help_given: int = 0


@dataclass
class Vacancy:
    id: str
    team_id: str
    role: str
    opened_month: int
    lead_time_months: int
    grade: int
    reason: str            # turnover | growth | restructure


@dataclass
class Team:
    id: str
    name: str
    dept_id: str
    function: str                 # frontline | admin | support | management | technology ...
    manager_id: Optional[str]
    member_ids: list[str]
    skills_provided: list[str]
    budget_annual: float
    protected: bool = False       # cannot be reduced by interventions (protected group)
    autonomy: float = 0.4         # team-level decision autonomy (0..1)
    accepting_transfers: bool = True   # manager can close the door ("protect team")
    overtime_allowed: bool = False
    hiring_frozen: bool = False

    # dynamic aggregates (recomputed each month)
    queue: list[str] = field(default_factory=list)     # work item ids waiting/in progress here
    capacity_hours: float = 0.0
    demand_hours: float = 0.0
    backlog_hours: float = 0.0
    workload: float = 0.0
    completed_this_month: int = 0
    completed_total: int = 0
    arrivals_this_month: int = 0
    transfers_in: int = 0
    transfers_out: int = 0
    errors_this_month: int = 0
    morale: float = 0.7
    stress: float = 0.2
    management_capacity_hours: float = 0.0
    management_load: float = 0.0
    approvals_waiting: int = 0
    turnover_12m: int = 0
    vacancies: list[Vacancy] = field(default_factory=list)
    spend_ytd: float = 0.0
    baseline_headcount: int = 0
    automation_level: float = 0.0     # fraction of routine hours removed by automation (0..1)
    automation_pipeline: list[tuple[int, float]] = field(default_factory=list)  # (ready_month, level)
    # AI agent pool (non-human capacity). Agents do routine work at ai_capacity_hours/month, need supervision hours
    # from humans, and a share of their output fails and returns to humans as exceptions (rework).
    ai_agents: float = 0.0                 # agent-equivalents live
    ai_pipeline: list[tuple[int, float]] = field(default_factory=list)   # (live_month, agents)
    ai_hours_per_agent: float = 120.0       # productive hours per agent-equivalent per month
    ai_supervision_hours: float = 12.0      # human hours per agent per month at supervision skill 0 (falls with skill)
    ai_base_exception_rate: float = 0.16    # exceptions on day one; learning and supervision bring it down
    ai_exception_rate: float = 0.16         # current effective rate (recomputed monthly)
    ai_silent_error_rate: float = 0.04      # AI output that passes but carries a hidden defect (surfaces downstream)
    ai_monthly_cost_per_agent: float = 900.0
    ai_routine_threshold: float = 0.4       # stages with at least this routine share are eligible for agents
    ai_handles_urgent: bool = False         # agents take priority-1 items?
    ai_live_month: Optional[int] = None     # first month agents were live (maturity)
    ai_paused_until: int = -1               # manager can pause agents after an incident
    ai_incident: bool = False               # incident this month (agents unavailable)
    ai_incidents_total: int = 0
    ai_supervision_coverage: float = 1.0    # supervision hours available / needed (computed)
    ai_items_this_month: int = 0
    replace_leavers: bool = True            # False = attrition-based downsizing (posts not backfilled while AI covers the work)
    programme_expandable: bool = False      # managers may expand the agent pool
    supervisory_share: float = 0.0          # share of members whose role is now supervising agents
    ai_capacity_hours: float = 0.0          # computed each month
    ai_exceptions_this_month: int = 0
    downstream_ai_errors_this_month: int = 0   # hidden AI defects that surfaced in THIS team's work
    verify_hours_this_month: float = 0.0


@dataclass
class Department:
    id: str
    name: str
    team_ids: list[str]
    budget_annual: float
    spend_ytd: float = 0.0
    hiring_frozen: bool = False
    head_id: Optional[str] = None


# ----------------------------------------------------------------------------
# Work and processes
# ----------------------------------------------------------------------------


@dataclass
class ProcessStage:
    id: str
    team_id: str                  # team performing the stage
    skill: str                    # required skill tag
    hours_mean: float
    hours_sd: float
    approval: bool = False        # consumes management capacity of the team instead of member hours
    routine: float = 0.5          # fraction of the stage that is routine (automatable)


@dataclass
class Process:
    id: str
    name: str
    kind: str                     # work item kind label, e.g. "procurement request"
    stages: list[ProcessStage]
    arrival_rate: float           # mean new items per month
    origin_team_id: Optional[str] # None = external origin
    deadline_months: int = 2
    priority_weights: tuple[float, float, float] = (0.2, 0.5, 0.3)  # P(high, medium, low)
    frontline: bool = False       # counts towards "delivery" metric
    ai_run_share: float = 0.0     # share of cases an AI loop runs end to end
    ai_delegated_approvals: bool = False   # AI may approve non-urgent items in this process


@dataclass
class WorkItem:
    id: str
    process_id: str
    kind: str
    priority: int                 # 1 high, 2 medium, 3 low
    stage_index: int
    team_id: str
    remaining_hours: float
    stage_hours: float
    created_month: int
    deadline_month: int
    origin_team_id: Optional[str]
    status: str = "queued"        # queued | in_progress | done | cancelled
    assignee_id: Optional[str] = None
    path: list[tuple[int, str]] = field(default_factory=list)   # (month, team_id) hops
    errors: int = 0
    delayed: int = 0
    completed_month: Optional[int] = None
    transferred: bool = False     # moved off its normal process path by a decision
    workaround: bool = False      # skipped an approval stage
    ai_handled: bool = False      # last stage was done by AI agents
    ai_exception: bool = False    # bounced back to humans by AI
    ai_silent_error: bool = False # carries a hidden AI defect that will surface at the next stage
    ai_approved: bool = False     # approval delegated to AI


@dataclass
class InfoPacket:
    id: str
    kind: str                     # announcement | rumour | warning | update | decision | financial
    topic: str
    origin_id: str                # employee id or "management"
    month: int
    holders: set[str] = field(default_factory=set)
    hops: list[tuple[int, str, str]] = field(default_factory=list)  # (month, from, to)
    valence: float = 0.0


# ----------------------------------------------------------------------------
# Events (causal graph)
# ----------------------------------------------------------------------------


@dataclass
class Event:
    id: int
    month: int
    kind: str                     # capacity_reduced | backlog_threshold | decision | work_transferred | employee_left ...
    actor: Optional[str]          # employee id / team id / "intervention" / "system"
    action: str
    entities: list[str]           # affected entity ids (teams, employees, processes)
    before: dict[str, Any]
    after: dict[str, Any]
    causes: list[int]             # event ids
    description: str
    significant: bool = False     # shown on timeline
    emergent: bool = False        # not explicitly specified by the intervention
    order: Optional[int] = None   # causal order from intervention root (1,2,3...) — computed lazily
    engine: Optional[str] = None  # decision engine that produced a decision event


def to_dict(obj: Any) -> Any:
    """asdict that copes with sets/tuples."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    if isinstance(obj, set):
        return sorted(obj)
    return obj
