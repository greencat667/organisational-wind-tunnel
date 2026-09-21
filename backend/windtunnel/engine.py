"""The simulation core: a World advances one month at a time.

Order of a monthly tick (see docs/SIMULATION_MODEL.md):
  1. scheduled interventions / shocks      (deterministic primitives)
  2. arrivals of new work                   (seeded Poisson per process)
  3. recruitment, onboarding, departures    (deterministic timing)
  4. absence and capacity arithmetic        (deterministic)
  5. agent decisions (event-triggered)      (decision engine, bounded actions)
  6. work processing through process stages (deterministic queueing, skills, approvals)
  7. psychological state, memory, network   (bounded dynamics)
  8. information propagation                (agents share along informal ties)
  9. finance                                (salaries, overtime, recruitment; budgets)
 10. metrics, events, emergence checks

Nothing in here calls a model except step 5 via ``decision_engine.decide``.
"""
from __future__ import annotations

import copy
import hashlib
import heapq
import math
import random
import time
from collections import defaultdict
from typing import Any, Optional

from . import ai
from .actions import EMPLOYEE_ACTIONS, MANAGER_ACTIONS
from .config import SimConfig
from .context import build_request
from .decisions.base import AgentDecision, AgentDecisionEngine, DecisionRequest
from .decisions.heuristic import HeuristicDecisionEngine
from .layout import compute_layout, place_new_employee
from .model import Employee, Event, InfoPacket, MemoryTrace, Team, Vacancy, WorkItem, to_dict
from .orggen import GRADE_SALARY, generate_organisation, productive_hours

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# event kinds that change a team's state and may therefore be cited as causes of later threshold events
STATE_CHANGING_KINDS = {"intervention", "capacity_reduced", "capacity_increased", "role_removed", "employee_left", "employee_hired", "internal_move",
                        "work_transferred", "work_redistributed", "work_cancelled", "work_dropped", "team_protected", "overtime_approved",
                        "vacancy_blocked", "post_not_replaced", "hiring_freeze", "manager_changed", "absence", "team_merged", "layer_removed",
                        "demand_changed", "budget_changed", "hours_changed", "shock", "automation_live", "ai_agents_live", "ai_incident",
                        "ai_paused", "ai_expanded", "ai_process_live", "roles_converted", "staff_retrained", "ai_quality_leak", "workaround",
                        "approval_removed", "approval_added", "reporting_changed", "backlog_threshold", "management_overload", "escalation"}
PERSONAL_CAUSE_KINDS = {"overtime", "escalation", "absence", "rework", "quality_reduced", "workaround", "manager_changed", "roles_converted",
                        "staff_retrained", "internal_move", "role_removed", "capacity_reduced", "team_merged", "ai_incident", "employee_overloaded"}
# event kinds that describe a systemic state change (candidates for the EMERGENT label when they hit non-target entities)
SYSTEMIC_KINDS = {"backlog_threshold", "management_overload", "turnover_spike", "team_protected", "work_dropped", "hiring_freeze",
                  "vacancy_blocked", "manager_changed", "automation_live", "ai_agents_live", "work_cancelled", "internal_move",
                  "ai_incident", "ai_quality_leak", "post_not_replaced", "ai_paused", "ai_expanded", "supervision_gap"}


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


class World:
    def __init__(self, template: str = "prototype", seed: int = 7, label: str = "baseline",
                 decision_engine: Optional[AgentDecisionEngine] = None, config: Optional[SimConfig] = None,
                 scale: float = 1.0, record_frames: bool = True):
        self.template = template
        self.seed = seed
        self.label = label
        self.config = config or SimConfig()
        self.rng = random.Random(seed)
        self.decision_engine = decision_engine or HeuristicDecisionEngine()
        self._heuristic = HeuristicDecisionEngine()
        self.record_frames = record_frames
        deps, teams, emps, procs = generate_organisation(template, seed, scale=scale, target_utilisation=self.config.target_utilisation)
        for t in teams.values():
            t.ai_hours_per_agent = self.config.ai_hours_per_agent
            t.ai_monthly_cost_per_agent = self.config.ai_monthly_cost_per_agent
            t.ai_supervision_hours = self.config.ai_supervision_hours
            t.ai_base_exception_rate = self.config.ai_base_exception_rate
            t.ai_exception_rate = self.config.ai_base_exception_rate
            t.ai_silent_error_rate = self.config.ai_silent_error_rate
        self.departments = deps
        self.teams = teams
        self.employees = emps
        self.processes = procs
        self.work_items: dict[str, WorkItem] = {}
        self.info_packets: dict[str, InfoPacket] = {}
        self.month = 0
        self.events: list[Event] = []
        self._event_seq = 0
        self.metrics_history: list[dict[str, Any]] = []
        self.decision_log: list[dict[str, Any]] = []
        self.frames: list[dict[str, Any]] = []
        self.scheduled: list[dict[str, Any]] = []       # pending change primitives: {"month": m, ...}
        self.demand_multiplier: dict[str, float] = {p: 1.0 for p in procs}
        self.global_demand: float = 1.0
        self.income_multiplier: float = 1.0
        self.intervention_root: Optional[int] = None
        self.intervention_targets: set[str] = set()
        self.intervention_month: Optional[int] = None
        self.layout = compute_layout(deps, teams, emps)
        # Recent causal events per team/employee, bucketed by kind: recent_team_causes/recent_emp_causes
        # only ever look for a handful of specific kinds (state-changing / personal-cause), but by far
        # the most frequent event kind emitted (e.g. employee_overloaded) is neither — so a flat per-team
        # list would force every lookup to wade through that noise. Bucketing means a lookup only ever
        # walks events of the kinds it actually asked for.
        self._team_events: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        self._emp_events: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        self._item_seq = 0
        self._packet_seq = 0
        self._vacancy_seq = 0
        self._emp_seq = len(emps)
        self._flows: list[dict[str, Any]] = []      # work movements this month (for the renderer)
        self._info_flows: list[dict[str, Any]] = []
        self._active_members_cache: dict[str, list[Employee]] = {}
        # team.member_ids scanned once per team per invalidation instead of once per decision
        # (invalidated by _clear_member_cache(), called at every hire/departure/team-move)
        self.timing: dict[str, float] = {}
        self.team_alias: dict[str, str] = {}        # merged/removed team -> receiving team
        self.baseline_metrics: Optional[dict[str, Any]] = None
        self.agreement = {"n": 0, "agree": 0, "by_action": defaultdict(lambda: {"model": 0, "rules": 0})}   # model vs shadow rules
        self.leavers_by_month: dict[int, int] = defaultdict(int)
        self.threshold_state: dict[str, str] = {}   # "team:backlog" -> band
        self._warm_start()

    # ------------------------------------------------------------------ utils
    def _r(self, tag: str, entity: str = "", month: Optional[int] = None) -> float:
        """Common random numbers: a uniform draw that depends only on (seed, month, tag, entity).

        Baseline and intervention worlds therefore see *identical* exogenous luck (arrivals, absences, external exits,
        errors) unless their state genuinely differs — so divergence between them is caused, not noise."""
        m = self.month if month is None else month
        h = hashlib.blake2b(f"{self.seed}|{m}|{tag}|{entity}".encode(), digest_size=8).digest()
        return int.from_bytes(h, "big") / 2**64

    def _rgauss(self, tag: str, entity: str, mu: float, sigma: float) -> float:
        u1 = max(1e-12, self._r(tag + ":a", entity))
        u2 = self._r(tag + ":b", entity)
        return mu + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2)

    def date_label(self, month: Optional[int] = None) -> str:
        m = self.month if month is None else month
        y = self.config.start_year + (self.config.start_month - 1 + m) // 12
        mm = (self.config.start_month - 1 + m) % 12
        return f"{MONTHS[mm]} {y}"

    def emit(self, kind: str, actor: Optional[str], action: str, entities: list[str], before: dict, after: dict,
             causes: list[int], description: str, significant: bool = False, engine: Optional[str] = None) -> Event:
        ev = Event(id=self._event_seq, month=self.month, kind=kind, actor=actor, action=action, entities=entities,
                   before=before, after=after, causes=sorted(set(c for c in causes if c is not None)),
                   description=description, significant=significant, engine=engine)
        self._event_seq += 1
        self.events.append(ev)
        for ent in entities:
            if ent in self.teams:
                self._team_events[ent][kind].append(ev.id)
            elif ent in self.employees:
                self._emp_events[ent][kind].append(ev.id)
        if self.intervention_root is not None and kind in SYSTEMIC_KINDS:
            ev.emergent = not any(e in self.intervention_targets for e in entities)
        return ev

    def _recent_causes(self, buckets: dict[str, list[int]], months: int, limit: int, kinds: set) -> list[int]:
        """Shared by recent_team_causes/recent_emp_causes. `buckets` holds this team/employee's events
        pre-sorted into per-kind lists, each append-only in chronological order (event ids only ever
        increase). Only the kinds actually being asked for are walked, and each is walked backwards
        and cut off the moment an event falls outside the month window — every earlier entry in that
        kind's list is older still. By far the most frequent event kind (employee_overloaded) is
        neither state-changing nor a personal cause, so this never has to wade through it: scanning a
        team or employee's *entire* history of every kind used to dominate simulation time once enough
        months had accumulated events (found by profiling at 10,000 employees)."""
        cutoff = self.month - months
        matches: list[int] = []
        for kind in kinds:
            ids = buckets.get(kind)
            if not ids:
                continue
            for i in reversed(ids):
                if self.events[i].month < cutoff:
                    break
                matches.append(i)
        matches.sort()   # event id increases monotonically with time -> chronological order
        return matches[-limit:]

    def recent_team_causes(self, team_id: str, months: int = 3, limit: int = 6, kinds: Optional[set] = None) -> list[int]:
        """Recent events on a team that could plausibly have moved its state. By default only *state-changing* kinds
        (staffing, capacity, transfers, agents, incidents, demand) count — never routine decisions."""
        kinds = STATE_CHANGING_KINDS if kinds is None else kinds
        return self._recent_causes(self._team_events.get(team_id, {}), months, limit, kinds)

    def recent_emp_causes(self, emp_id: str, months: int = 4, limit: int = 5, kinds: Optional[set] = None) -> list[int]:
        """Recent events that happened *to* this person (overload, escalation ignored, absence, role change…), not their
        routine decisions."""
        kinds = PERSONAL_CAUSE_KINDS if kinds is None else kinds
        return self._recent_causes(self._emp_events.get(emp_id, {}), months, limit, kinds)

    def active_members(self, team: Team) -> list[Employee]:
        cached = self._active_members_cache.get(team.id)
        if cached is not None:
            return cached
        result = [self.employees[m] for m in team.member_ids if self.employees[m].status in ("active", "leaving")]
        self._active_members_cache[team.id] = result
        return result

    def _clear_member_cache(self) -> None:
        """Call whenever a hire, departure, or move changes who's on a team.
        Cheap (dict of a handful of teams) and correctness-critical: active_members()
        trusts this cache completely, so anything that changes membership must clear
        it before the next read, not just before the next month."""
        self._active_members_cache.clear()

    def manager_load(self, mgr: Employee) -> float:
        team = self.teams.get(mgr.team_id)
        if not team:
            return 0.0
        if mgr.id == team.manager_id:
            return team.management_load
        return 0.5

    def neighbour_teams(self, team_id: str) -> list[str]:
        """Teams connected to this one through shared processes (either direction)."""
        out: set[str] = set()
        for p in self.processes.values():
            tids = [self.resolve_team(s.team_id) for s in p.stages]
            if team_id in tids:
                out.update(t for t in tids if t != team_id)
        return sorted(t for t in out if t in self.teams)

    def resolve_team(self, team_id: str) -> str:
        seen = 0
        while team_id in self.team_alias and seen < 10:
            team_id = self.team_alias[team_id]
            seen += 1
        return team_id

    def recent_change_labels(self, team_id: str, months: int = 6) -> list[str]:
        labels = []
        for ev in reversed(self.events):
            if ev.month < self.month - months:
                break
            if ev.significant and (team_id in ev.entities or ev.kind == "intervention"):
                labels.append(ev.description[:80])
            if len(labels) >= 5:
                break
        return labels

    def unshared_info(self, emp: Employee) -> list[InfoPacket]:
        out = []
        for p in self.info_packets.values():
            if emp.id in p.holders and self.month - p.month <= 4:
                if any(r not in p.holders for r in emp.relationships):
                    out.append(p)
        return out

    def can_open_vacancy(self, team: Team) -> bool:
        dept = self.departments[team.dept_id]
        if team.hiring_frozen or dept.hiring_frozen:
            return False
        if not team.replace_leavers and team.ai_agents > 0:
            return False
        active = len(self.active_members(team)) + len(team.vacancies)
        spend_rate = sum(self.employees[m].salary for m in team.member_ids if self.employees[m].status != "left")
        return active < team.baseline_headcount + 1 and spend_rate * 1.05 < team.budget_annual

    def frontline_share_waiting(self, team: Team) -> float:
        q = [self.work_items[i] for i in team.queue if i in self.work_items]
        if not q:
            return 0.0
        return sum(1 for w in q if self.processes[w.process_id].frontline) / len(q)

    def automation_enabled(self, team: Team) -> bool:
        return any(c.get("op") == "enable_automation" and self.resolve_team(c.get("team", "")) == team.id
                   for c in self.applied_changes) if hasattr(self, "applied_changes") else False

    # ----------------------------------------------------------------- warm start
    def _warm_start(self) -> None:
        """Pre-fill queues so month 0 already looks like a working organisation (~0.6 months of work)."""
        self.applied_changes: list[dict[str, Any]] = []
        for e in self.employees.values():
            e.skill_at_start = dict(e.skills)
            e.role_kind = "manager" if e.is_manager else "officer"
        self._recompute_capacity()
        for p in self.processes.values():
            n = int(round(self._arrivals_for(p) * 0.3))
            for _ in range(n):
                item = self._new_item(p, created=-1)
                # place a share of items further along their process
                if len(p.stages) > 1 and self.rng.random() < 0.4:
                    self._move_item(item, self.rng.randint(1, len(p.stages) - 1), record_flow=False)
        self._update_team_aggregates()
        self.metrics_history.append(self._compute_metrics())
        if self.record_frames:
            self.frames.append(self._frame())

    # ------------------------------------------------------------------ tick
    def step(self) -> dict[str, Any]:
        t0 = time.perf_counter()
        self.month += 1
        self._flows = []
        self._info_flows = []
        for t in self.teams.values():
            t.completed_this_month = 0
            t.arrivals_this_month = 0
            t.transfers_in = 0
            t.transfers_out = 0
            t.errors_this_month = 0
            t.approvals_waiting = 0
        for e in self.employees.values():
            e.overtime_hours = 0.0
            e.hours_worked = 0.0
            e.current_behaviour = "working" if e.status == "active" else e.status
        timing = {}
        s = time.perf_counter(); self._apply_scheduled(); timing["interventions"] = time.perf_counter() - s
        s = time.perf_counter(); self._arrivals(); timing["arrivals"] = time.perf_counter() - s
        s = time.perf_counter(); self._people_flow(); timing["people"] = time.perf_counter() - s
        s = time.perf_counter(); self._absence(); self._recompute_capacity(); self._update_team_aggregates(workload=True); timing["capacity"] = time.perf_counter() - s
        s = time.perf_counter(); n_dec = self._decisions(); timing["decisions"] = time.perf_counter() - s
        s = time.perf_counter(); self._process_work(); timing["work"] = time.perf_counter() - s
        s = time.perf_counter(); self._update_team_aggregates(workload=False); self._psychology(); timing["psychology"] = time.perf_counter() - s
        s = time.perf_counter(); ai.monthly_learning_and_atrophy(self); self._information(); timing["information"] = time.perf_counter() - s
        s = time.perf_counter(); self._finance(); timing["finance"] = time.perf_counter() - s
        s = time.perf_counter()
        metrics = self._compute_metrics()
        self._threshold_events(metrics)
        self.metrics_history.append(metrics)
        frame = self._frame() if self.record_frames else None
        if frame is not None:
            self.frames.append(frame)
        timing["metrics"] = time.perf_counter() - s
        timing["total"] = time.perf_counter() - t0
        timing["decisions_count"] = n_dec
        timing["triggers"] = dict(self._trigger_counts)
        self.timing = timing
        return {"month": self.month, "label": self.date_label(), "metrics": metrics, "frame": frame, "timing": timing}

    def run(self, months: int) -> None:
        for _ in range(months):
            self.step()

    # --------------------------------------------------------- 1. interventions
    def _apply_scheduled(self) -> None:
        from .interventions.primitives import apply_change  # local import: primitives depend on World
        due = [c for c in self.scheduled if c["month"] == self.month]
        self.scheduled = [c for c in self.scheduled if c["month"] != self.month]
        for change in due:
            apply_change(self, change)

    # -------------------------------------------------------------- 2. arrivals
    def _arrivals_for(self, p) -> float:
        rate = p.arrival_rate * self.demand_multiplier.get(p.id, 1.0) * self.global_demand
        return min(rate, p.arrival_rate * self.config.max_arrival_total_multiplier)

    def _poisson(self, lam: float, key: str = "") -> int:
        if lam <= 0:
            return 0
        if lam > 30:
            return max(0, int(round(self._rgauss("arrivals", key, lam, math.sqrt(lam)))))
        L = math.exp(-lam)
        k, p = 0, 1.0
        while True:
            p *= self._r("arrivals", f"{key}:{k}")
            if p < L:
                return k
            k += 1

    def _new_item(self, p, created: Optional[int] = None, bundle: float = 1.0) -> WorkItem:
        self._item_seq += 1
        r = self._r("priority", f"{p.id}:{self._item_seq}")
        pw = p.priority_weights
        priority = 1 if r < pw[0] else 2 if r < pw[0] + pw[1] else 3
        stage = p.stages[0]
        team_id = self.resolve_team(stage.team_id)
        hours = self._stage_hours(stage, team_id, str(self._item_seq)) * bundle
        created_m = self.month if created is None else created
        item = WorkItem(id=f"W{self._item_seq:06d}", process_id=p.id, kind=p.kind, priority=priority, stage_index=0,
                        team_id=team_id, remaining_hours=hours, stage_hours=hours, created_month=created_m,
                        deadline_month=created_m + p.deadline_months, origin_team_id=p.origin_team_id)
        item.path.append((self.month, team_id))
        self.work_items[item.id] = item
        self.teams[team_id].queue.append(item.id)
        self.teams[team_id].arrivals_this_month += 1
        return item

    def _stage_hours(self, stage, team_id: str, key: str = "") -> float:
        h = max(0.2, self._rgauss("hours", f"{stage.id}:{key}", stage.hours_mean, stage.hours_sd))
        auto = self.teams[team_id].automation_level if team_id in self.teams else 0.0
        return h * (1.0 - stage.routine * auto)

    def _arrivals(self) -> None:
        for p in self.processes.values():
            lam = self._arrivals_for(p)
            bundle = 1.0
            if lam > self.config.max_items_per_process_month:
                bundle = lam / self.config.max_items_per_process_month
                lam = self.config.max_items_per_process_month
            n = self._poisson(lam, p.id)
            for _ in range(n):
                self._new_item(p, bundle=bundle)

    # ----------------------------------------------------------- 3. people flow
    def _people_flow(self) -> None:
        cfg = self.config
        # departures
        for e in list(self.employees.values()):
            if e.status == "leaving" and e.leaving_month is not None and self.month >= e.leaving_month:
                self._employee_leaves(e)
        # external/life-event exits: a seeded hazard, amplified by turnover intention (organisational physics, not AI)
        for e in list(self.employees.values()):
            if e.status == "active" and self.month > 0:
                hz = cfg.baseline_exit_hazard * (1.0 + 3.0 * e.turnover_intention) * (0.5 + cfg.job_market)
                if self._r("exit", e.id) < hz:
                    e.status = "leaving"
                    e.leaving_month = self.month + cfg.turnover_notice_months
                    e.current_behaviour = "leaving"
                    self.emit("resignation", e.id, "leave", [e.id, e.team_id], {"turnover_intention": round(e.turnover_intention, 2)}, {"reason": "external"},
                              self.recent_emp_causes(e.id, months=6, limit=3), f"{e.name} resigned from {self.teams[e.team_id].name}", significant=True)
        # vacancies -> hires
        for team in self.teams.values():
            for v in list(team.vacancies):
                ready = self.month >= v.opened_month + v.lead_time_months
                if ready and not (team.hiring_frozen or self.departments[team.dept_id].hiring_frozen):
                    self._hire(team, v)
        # onboarding progress
        for e in self.employees.values():
            if e.status == "active" and e.onboarding_months_left > 0:
                e.onboarding_months_left -= 1
            if e.status == "active":
                e.experience_months += 1

    def _employee_leaves(self, e: Employee) -> None:
        team = self.teams[e.team_id]
        e.status = "left"
        self._clear_member_cache()
        e.left_month = self.month
        e.current_behaviour = "left"
        # hand back work to the team queue
        for wid in e.active_tasks:
            w = self.work_items.get(wid)
            if w and w.status == "in_progress":
                w.status = "queued"
                w.assignee_id = None
        e.active_tasks = []
        self.leavers_by_month[self.month] += 1
        causes = self.recent_emp_causes(e.id) + self.recent_team_causes(team.id, months=2, limit=2)
        ev = self.emit("employee_left", e.id, "left", [e.id, team.id],
                       {"headcount": len(self.active_members(team)) + 1}, {"headcount": len(self.active_members(team))},
                       causes, f"{e.name} ({e.role_title}) left {team.name}", significant=True)
        if e.id == team.manager_id:
            self._replace_manager(team, ev.id)
        # vacancy (if budget allows and not frozen) + rumour
        if self.can_open_vacancy(team):
            self._open_vacancy(team, e.role, e.grade, "turnover", [ev.id])
        elif not team.replace_leavers and team.ai_agents > 0:
            team.baseline_headcount = max(1, team.baseline_headcount - 1)
            team.budget_annual -= e.salary * 1.18 * 0.5   # half the saving is banked, half funds the agents
            self.emit("post_not_replaced", team.id, "attrition_downsizing", [team.id], {}, {"headcount": len(self.active_members(team))},
                      [ev.id] + ([ai._latest_ai_event(self, team.id)] if ai._latest_ai_event(self, team.id) is not None else []),
                      f"{team.name} did not replace {e.name}: work covered by AI agents", significant=True)
        else:
            self.emit("vacancy_blocked", team.id, "vacancy_not_opened", [team.id], {}, {"frozen": team.hiring_frozen},
                      [ev.id], f"{team.name} could not replace {e.name} (budget or hiring freeze)", significant=True)
        self._new_packet("rumour", f"{e.name} has left {team.name}", team.member_ids[:1] or ["management"], valence=-0.3,
                         seed_holders=[m for m in team.member_ids if self.employees[m].status == "active"][:3])
        for m in self.active_members(team):
            m.memory.append(MemoryTrace(self.month, "colleague_left", -0.3, 1.0))

    def _replace_manager(self, team: Team, cause: int) -> None:
        members = [m for m in self.active_members(team) if m.status == "active"]
        if not members:
            team.manager_id = None
            return
        new = max(members, key=lambda m: (m.grade, m.experience_months))
        new.is_manager = True
        new.skills["management"] = max(new.skills.get("management", 0.0), 0.45)
        old_mgr_id = team.manager_id
        team.manager_id = new.id
        for m in members:
            if m.id != new.id:
                m.manager_id = new.id
        self.emit("manager_changed", team.id, "acting_manager", [team.id, new.id], {"manager": old_mgr_id},
                  {"manager": new.id}, [cause], f"{new.name} became acting manager of {team.name}", significant=True)
        for m in members:
            m.memory.append(MemoryTrace(self.month, "manager_changed", -0.1, 0.8))

    def _open_vacancy(self, team: Team, role: str, grade: int, reason: str, causes: list[int]) -> Vacancy:
        self._vacancy_seq += 1
        lead = self.config.recruitment_lead_months
        # recruitment relies on admin/HR capacity: if the HR-capable team is overloaded, lead time stretches
        hr_team = self._team_with_skill("hr") or self._team_with_skill("admin")
        if hr_team is not None and hr_team.workload > 1.1:
            lead += 1 + int(hr_team.workload > 1.4)
        v = Vacancy(id=f"V{self._vacancy_seq:04d}", team_id=team.id, role=role, opened_month=self.month,
                    lead_time_months=lead, grade=grade, reason=reason)
        team.vacancies.append(v)
        self.emit("vacancy_opened", team.id, "recruit", [team.id], {}, {"lead_months": lead}, causes,
                  f"{team.name} opened a vacancy ({reason}); expected fill in {lead} months")
        # recruitment generates real admin work
        hr_proc = next((p for p in self.processes.values() if p.id == "hr_case"), None)
        if hr_proc is not None:
            item = self._new_item(hr_proc)
            item.kind = "recruitment"
            item.priority = 2
        return v

    def internal_process(self, team_id: str):
        """A one-stage process for a team's own internal projects (implementation work, automation builds)."""
        from .model import Process, ProcessStage
        pid = f"internal_{team_id}"
        if pid not in self.processes:
            t = self.teams[team_id]
            skill = t.skills_provided[0] if t.skills_provided else "admin"
            self.processes[pid] = Process(id=pid, name=f"{t.name} internal project", kind="internal project", arrival_rate=0.0,
                                          stages=[ProcessStage(id=f"{pid}_s0", team_id=team_id, skill=skill, hours_mean=40.0, hours_sd=0.0, routine=0.2)],
                                          origin_team_id=team_id, deadline_months=6)
            self.demand_multiplier[pid] = 0.0
        return self.processes[pid]

    def _team_with_skill(self, skill: str) -> Optional[Team]:
        best = None
        for t in self.teams.values():
            if skill in t.skills_provided and self.active_members(t):
                if best is None or len(t.member_ids) > len(best.member_ids):
                    best = t
        return best

    def _hire(self, team: Team, v: Vacancy) -> None:
        team.vacancies.remove(v)
        self._emp_seq += 1
        eid = f"E{self._emp_seq:04d}"
        first = ["Riley", "Jesse", "Casey", "Morgan", "Robin", "Quinn", "Avery", "Dana", "Sky", "Remy"]
        last = ["Park", "Quist", "Ali", "Bennett", "Cruz", "Doyle", "Ekwueme", "Frost", "Grant", "Hale"]
        name = f"{first[int(self._r('hire_first', eid) * 10) % 10]} {last[int(self._r('hire_last', eid) * 10) % 10]}"
        skills = {s: round(0.45 + 0.35 * self._r("hire_skill", f"{eid}:{s}"), 2) for s in team.skills_provided[:1]}
        for s in team.skills_provided[1:]:
            skills[s] = round(0.25 + 0.35 * self._r("hire_skill", f"{eid}:{s}"), 2)
        e = Employee(id=eid, name=name, role=v.role, role_title=team.name.split()[0] + " Officer", team_id=team.id,
                     dept_id=team.dept_id, grade=v.grade, salary=GRADE_SALARY[min(7, v.grade)], contracted_hours=self.config.monthly_hours,
                     skills=skills, experience_months=0, manager_id=team.manager_id, onboarding_months_left=self.config.onboarding_months,
                     hired_month=self.month, institutional_knowledge=0.15, archetype=["steady", "helper", "mobile", "cautious"][int(self._r("hire_arch", eid) * 4) % 4],
                     morale=0.72, stress=0.25, trust_management=0.65, commitment=0.5)
        e.skill_at_start = dict(e.skills)
        if team.supervisory_share > 0 and self._r("hire_role", eid) < team.supervisory_share:
            e.role_kind = "supervisor"
            e.role_title = f"AI Supervisor ({e.role_title})"
            e.skills["ai_supervision"] = round(0.3 + 0.4 * e.adaptability, 2)
        self.employees[eid] = e
        team.member_ids.append(eid)
        self._clear_member_cache()
        self.layout["employees"][eid] = place_new_employee(self.layout, team.id, len(team.member_ids) - 1)
        self.departments[team.dept_id].spend_ytd += self.config.recruitment_cost
        team.spend_ytd += self.config.recruitment_cost
        self.emit("employee_hired", team.id, "hire", [team.id, eid], {}, {"onboarding_months": self.config.onboarding_months},
                  self.recent_team_causes(team.id, months=v.lead_time_months + 1, limit=3),
                  f"{name} joined {team.name} (onboarding {self.config.onboarding_months} months)", significant=True)

    # ----------------------------------------------------------- 4. capacity
    def _absence(self) -> None:
        for e in self.employees.values():
            if e.status not in ("active", "leaving"):
                e.absent_fraction = 0.0
                continue
            p = e.absence_probability + 0.10 * max(0.0, e.stress - 0.6)
            e.absent_fraction = 0.0
            if self._r("absence", e.id) < p:
                e.absent_fraction = min(1.0, [0.1, 0.25, 0.5, 1.0][int(self._r("absence_len", e.id) * 4) % 4] * (1.0 + max(0.0, e.stress - 0.7)))
                if e.absent_fraction >= 0.5:
                    self.emit("absence", e.id, "absent", [e.id, e.team_id], {}, {"fraction": e.absent_fraction},
                              self.recent_emp_causes(e.id, months=2, limit=2), f"{e.name} absent ({int(e.absent_fraction*100)}% of month)")

    def effectiveness(self, e: Employee) -> float:
        onboard = 1.0
        if e.onboarding_months_left > 0:
            frac = e.onboarding_months_left / self.config.onboarding_months
            onboard = self.config.onboarding_start_productivity + (1 - self.config.onboarding_start_productivity) * (1 - frac)
        stress_pen = 1.0 - 0.2 * max(0.0, e.stress - 0.65)
        morale_f = 0.85 + 0.15 * e.morale
        return max(0.2, onboard * stress_pen * morale_f * e.effort_level)

    def _recompute_capacity(self) -> None:
        cfg = self.config
        for t in self.teams.values():
            members = self.active_members(t)
            n = len(members)
            mgmt_hours = 0.0
            cap = 0.0
            for e in members:
                base = e.contracted_hours * (1.0 - e.absent_fraction)
                if e.id == t.manager_id:
                    m_h = min(base * 0.8, cfg.manager_base_hours + cfg.manager_hours_per_report * max(0, n - 1))
                    mgmt_hours += m_h
                    base -= m_h
                elif e.is_manager and t.function == "management":
                    m_h = base * 0.6          # directors: most of their time is management capacity
                    mgmt_hours += m_h
                    base -= m_h
                elif e.grade >= 5:
                    m_h = min(base, 8.0)      # senior officers can approve routine items
                    mgmt_hours += m_h
                    base -= m_h
                e.capacity_hours = max(0.0, base * cfg.productive_fraction * self.effectiveness(e))
                cap += e.capacity_hours
            # AI agent pool (see ai.py): supervision off human hours, coverage, exception rate, incidents
            cap = ai.apply_capacity(self, t, members, cap)
            t.capacity_hours = cap
            t.management_capacity_hours = mgmt_hours

    def _update_team_aggregates(self, workload: bool = True) -> None:
        """Before processing (workload=True): demand = carried backlog + this month's arrivals, workload = demand/capacity.
        After processing (workload=False): backlog = what is left; workload is kept from the start of the month."""
        for t in self.teams.values():
            items = [self.work_items[i] for i in t.queue if i in self.work_items and self.work_items[i].status in ("queued", "in_progress")]
            hours = sum(w.remaining_hours for w in items)
            members = [m for m in self.active_members(t) if m.status == "active"]
            if workload:
                t.demand_hours = hours
                t.workload = hours / max(1.0, t.capacity_hours) if t.capacity_hours > 0 else (2.0 if items else 0.0)
                self._allocate(t, items, members)
            t.backlog_hours = hours
            t.morale = sum(m.morale for m in members) / len(members) if members else 0.0
            t.stress = sum(m.stress for m in members) / len(members) if members else 0.0

    def _allocate(self, t: Team, items: list[WorkItem], members: list[Employee], balance: bool = False) -> None:
        """Plan who does what this month. Each item goes to the skilled member with the lowest load ratio (sticky for
        items already in progress unless ``balance``). Personal workload = allocated hours / own capacity, so overload can
        concentrate on individuals and key people can emerge."""
        workers = [m for m in members if m.capacity_hours > 0 and m.absent_fraction < 1.0]
        for m in members:
            m.assigned_hours = 0.0
            m.active_tasks = []
        if not workers:
            for m in members:
                m.workload = 1.5 if items else 0.0
            return
        load = {m.id: 0.0 for m in workers}
        cap = {m.id: max(1.0, m.capacity_hours) for m in workers}
        by_id = {m.id: m for m in workers}
        approvals = 0.0

        # Least-loaded-by-ratio selection used to rescan `workers` with min() on every chunk
        # (O(items x chunks x team_size) per team per month). Instead, keep one lazy-deletion
        # min-heap per distinct skill encountered this call, keyed by the same
        # (load_ratio, -skill_level, id) tuple `min()` used, so picking drops to O(log team_size).
        # `load[m]` only ever increases, so a heap entry's ratio can only match the worker's
        # current true ratio if it is the most recently pushed one for that worker — any older
        # entry is provably stale (its ratio is strictly lower) and safe to discard on sight.
        heaps: dict[str, list[tuple[float, float, str]]] = {}
        skill_ids: dict[str, set[str]] = {}   # skill -> ids of workers skilled (>=0.2) in it, built once per skill

        def pool_for(skill: str) -> set[str]:
            ids = skill_ids.get(skill)
            if ids is None:
                ids = {m.id for m in workers if m.skills.get(skill, 0.0) >= 0.2}
                skill_ids[skill] = ids
                # Seed with each worker's CURRENT ratio, not 0.0: a worker may already carry
                # load from a different skill processed earlier this call (pools are built
                # lazily, on first use of each skill) — seeding at 0.0 would leave that entry
                # permanently stale (ratio can only increase) and eventually empty the heap.
                heaps[skill] = [(load[mid] / cap[mid], -by_id[mid].skills.get(skill, 0.0), mid) for mid in ids]
                heapq.heapify(heaps[skill])
            return ids

        def pop_min(skill: str) -> Employee:
            heap = heaps[skill]
            while True:
                ratio, _neg_skill, mid = heap[0]
                if ratio == load[mid] / cap[mid]:
                    return by_id[mid]
                heapq.heappop(heap)   # stale — this worker's load changed since this entry was pushed

        def bump(m: Employee) -> None:
            """Refresh m's entry in every already-built skill-heap it belongs to, not just the
            one just used: a worker can qualify for more than one skill, and leaving their entry
            in another skill's heap stale would eventually drop them from consideration there
            even if they're the lightest-loaded person left."""
            ratio = load[m.id] / cap[m.id]
            for skill, ids in skill_ids.items():
                if m.id in ids:
                    heapq.heappush(heaps[skill], (ratio, -m.skills.get(skill, 0.0), m.id))

        for w in sorted(items, key=lambda w: (w.priority, w.created_month, w.id)):
            stage = self.processes[w.process_id].stages[w.stage_index]
            if stage.approval:
                approvals += stage.hours_mean
                continue
            if not pool_for(stage.skill):
                continue
            keep = by_id.get(w.assignee_id) if (w.assignee_id and not balance and w.status == "in_progress") else None
            remaining = w.remaining_hours
            first = True
            while remaining > 0.01:
                if first and keep is not None and keep.skills.get(stage.skill, 0.0) >= 0.2:
                    m = keep
                else:
                    m = pop_min(stage.skill)
                rate = 0.55 + 0.45 * m.skills.get(stage.skill, 0.2)
                chunk = min(remaining, max(4.0, 0.35 * cap[m.id] * rate))   # a big item is shared, in chunks
                load[m.id] += chunk / rate
                bump(m)
                remaining -= chunk
                if first:
                    w.assignee_id = m.id
                    first = False
                if w.id not in m.active_tasks:
                    m.active_tasks.append(w.id)
        for m in workers:
            m.assigned_hours = load[m.id]
            m.workload = load[m.id] / cap[m.id]
        for m in members:
            if m.id not in load:
                m.workload = 0.0

    # ---------------------------------------------------------- 5. decisions
    def _decisions(self) -> int:
        cfg = self.config
        candidates: list[tuple[Employee, list[str], list[int], str]] = []
        for t in self.teams.values():
            members = [m for m in self.active_members(t) if m.status == "active" and m.absent_fraction < 0.5]
            team_causes = self.recent_team_causes(t.id)
            lost_staff = any(self.events[i].kind == "employee_left" for i in team_causes)
            backlog_months = t.backlog_hours / max(1.0, t.capacity_hours)
            restructured = any(self.events[i].kind in ("intervention", "capacity_reduced", "team_merged", "reporting_changed")
                               and self.events[i].month >= self.month - 1 for i in team_causes)
            for m in members:
                trig = []
                if m.workload > cfg.overload_threshold:
                    trig.append("overload")
                if backlog_months > cfg.backlog_high_months:
                    trig.append("team_backlog_high")
                if lost_staff:
                    trig.append("colleague_left")
                if restructured:
                    trig.append("restructure")
                if any(self.work_items[i].deadline_month < self.month - 1 and self.work_items[i].priority <= 2 for i in m.active_tasks if i in self.work_items):
                    trig.append("deadline_pressure")
                if m.morale < 0.35:
                    trig.append("low_morale")
                if m.turnover_intention > 0.3:
                    trig.append("turnover_pressure")
                if any(self.events[i].kind == "manager_changed" for i in team_causes):
                    trig.append("manager_changed")
                if t.ai_agents > 0:
                    if any(self.events[i].kind in ("ai_agents_live", "roles_converted") and self.events[i].month >= self.month - 1 for i in team_causes):
                        trig.append("ai_introduced")
                    if t.ai_incident:
                        trig.append("ai_incident")
                    if t.ai_items_this_month + t.ai_exceptions_this_month > 0 and t.ai_exceptions_this_month / max(1, t.ai_items_this_month + t.ai_exceptions_this_month) > 0.25 or t.ai_exception_rate > 0.3:
                        trig.append("ai_exceptions_high")
                    if t.ai_supervision_coverage < 0.8:
                        trig.append("supervision_gap")
                if not trig and self._r("periodic", m.id) < cfg.periodic_decision_fraction:
                    trig.append("periodic")
                if trig:
                    kind = "manager" if m.id == t.manager_id else "employee"
                    if kind == "manager" and not any(x in trig for x in ("team_backlog_high", "colleague_left", "restructure", "periodic", "manager_changed", "ai_incident", "ai_exceptions_high", "supervision_gap", "ai_introduced")) and t.workload < 1.05:
                        continue
                    candidates.append((m, trig, team_causes, kind))
        # prioritise: managers first, then most overloaded; cap evaluations per team and per month
        candidates.sort(key=lambda c: (c[3] != "manager", -c[0].workload))
        per_team: dict[str, int] = defaultdict(int)
        capped = []
        for c in candidates:
            if per_team[c[0].team_id] < 8 or c[3] == "manager":
                capped.append(c)
                per_team[c[0].team_id] += 1
        candidates = capped
        if len(candidates) > cfg.max_decisions_per_month:
            keep = candidates[: cfg.max_decisions_per_month // 2]
            rest = candidates[cfg.max_decisions_per_month // 2:]
            rest.sort(key=lambda c: self._r("decision_pick", c[0].id))
            candidates = keep + rest[: cfg.max_decisions_per_month - len(keep)]
        n = 0
        self._trigger_counts: dict[str, int] = defaultdict(int)
        for emp, trig, causes, kind in candidates:
            if emp.status != "active":
                continue
            for tr in trig:
                self._trigger_counts[tr] += 1
            self._decide_and_apply(emp, trig, causes, kind)
            n += 1
        return n

    def available_actions(self, emp: Employee, kind: str) -> tuple[list[str], dict[str, list[str]]]:
        """Deterministic constraints on what an agent *can* do — no magical employees."""
        team = self.teams[emp.team_id]
        acts = ["continue_as_normal"]
        targets: dict[str, list[str]] = {}
        my_items = [self.work_items[i] for i in emp.active_tasks if i in self.work_items]
        queue_items = [self.work_items[i] for i in team.queue if i in self.work_items]
        if kind == "employee":
            helpers = []
            needed = {self.processes[w.process_id].stages[w.stage_index].skill for w in queue_items
                      if not self.processes[w.process_id].stages[w.stage_index].approval}
            for nt in self.neighbour_teams(team.id):
                t = self.teams[nt]
                if t.function == "management" or not t.accepting_transfers or t.workload >= 0.9 or not self.active_members(t):
                    continue
                if self.team_can_do(t, needed):
                    helpers.append(nt)
            if helpers and queue_items:
                acts.append("seek_help"); targets["seek_help"] = helpers
            if emp.contracted_hours >= 100 and team.overtime_allowed or (emp.workload > 1.05 and emp.overtime_hours < cfg_max(self)):
                acts.append("work_overtime")
            if any(w.priority == 3 for w in queue_items):
                acts.append("delay_low_priority")
            mgr = self.employees.get(emp.manager_id) if emp.manager_id else None
            if mgr and mgr.status == "active" and team.management_load < 1.6:
                acts.append("escalate_workload")
            if any(self._next_stage_is_approval(w) for w in queue_items):
                acts.append("use_workaround")
            if emp.workload > 1.0:
                acts.append("reduce_quality")
            if self.unshared_info(emp):
                acts.append("share_information")
            vac = [t.id for t in self.teams.values() if t.id != team.id and t.vacancies
                   and any(emp.skills.get(s, 0) >= 0.3 for s in t.skills_provided)]
            if vac and emp.turnover_intention > 0.15:
                acts.append("apply_for_internal_job"); targets["apply_for_internal_job"] = vac
            if emp.turnover_intention > 0.2 and emp.status == "active":
                acts.append("leave")
            if team.ai_agents > 0 and team.ai_capacity_hours > 0:
                acts.append("verify_ai_output")
        else:
            members = [m for m in self.active_members(team) if m.status == "active" and m.id != emp.id]
            if len(members) >= 2 and queue_items:
                acts.append("redistribute_work")
            if self.can_open_vacancy(team) and team.function != "management":
                acts.append("request_recruitment")
            if not team.overtime_allowed:
                acts.append("approve_overtime")
            if team.accepting_transfers:
                acts.append("protect_team")
            if any(w.priority == 3 for w in queue_items):
                acts.append("cancel_low_priority")
            if emp.manager_id and self.employees.get(emp.manager_id) and self.employees[emp.manager_id].status == "active":
                acts.append("escalate_up")
            if queue_items:
                acts.append("reprioritise")
            if self.automation_enabled(team) and team.automation_level < 0.6 and not team.automation_pipeline:
                acts.append("automate_task")
            if team.ai_agents > 0 and team.ai_paused_until < self.month:
                acts.append("pause_ai_agents")
            if team.programme_expandable and team.ai_agents > 0 and not team.ai_pipeline and team.ai_exception_rate < 0.12 and team.ai_supervision_coverage >= 0.9:
                acts.append("expand_ai_agents")
            if team.ai_agents > 0 and team.ai_supervision_coverage < 0.9 and any(m.role_kind == "officer" and m.id != team.manager_id for m in self.active_members(team)):
                acts.append("retrain_staff")
            if self.unshared_info(emp) or any(self.events[i].kind == "intervention" and self.events[i].month >= self.month - 1 for i in range(max(0, len(self.events) - 200), len(self.events))):
                acts.append("share_information")
        return acts, targets

    def team_can_do(self, t: Team, skills: set[str]) -> bool:
        """A team can plausibly help with a skill if it provides it, or at least two active members have it at >=0.35."""
        if skills & set(t.skills_provided):
            return True
        for s in skills:
            n = sum(1 for m in t.member_ids if self.employees[m].status == "active" and self.employees[m].skills.get(s, 0) >= 0.35)
            if n >= 2:
                return True
        return False

    def _next_stage_is_approval(self, w: WorkItem) -> bool:
        p = self.processes[w.process_id]
        return w.stage_index + 1 < len(p.stages) and p.stages[w.stage_index + 1].approval

    def _decide_and_apply(self, emp: Employee, triggers: list[str], causes: list[int], kind: str) -> None:
        available, targets = self.available_actions(emp, kind)
        if len(available) == 1 and "periodic" in triggers:
            return
        req = build_request(self, emp, triggers, available, targets, kind)
        t0 = time.perf_counter()
        try:
            decision = self.decision_engine.decide(req)
        except Exception as exc:  # model failure must never stop the simulation
            decision = self._heuristic.decide(req)
            decision.fallback = True
            decision.raw = {"error": repr(exc)[:200]}
        if decision.latency_ms == 0.0 and not decision.cached:
            decision.latency_ms = (time.perf_counter() - t0) * 1000.0
        decision = self._route(decision, req)
        decision = self._guards(decision, emp, req)
        if decision.action not in available:
            decision.action = "continue_as_normal"
        shadow_action = None
        if getattr(self.decision_engine, "name", "heuristic") != "heuristic":
            # shadow rules decision, sampled with the same common random number, so agreement is measured like-for-like
            shadow = self._heuristic.decide(req)
            shadow_action = self._sample(shadow.probabilities, req.agent_id) if shadow.confidence < self.config.confidence_execute else shadow.action
            self.agreement["n"] += 1
            self.agreement["agree"] += int(shadow_action == decision.action)
            self.agreement["by_action"][decision.action]["model"] += 1
            self.agreement["by_action"][shadow_action]["rules"] += 1
        if decision.action in targets and not decision.target:
            decision.target = self._pick_target(emp, decision.action, targets[decision.action])
        emp.effort_level = clamp(decision.scores.get("effort", 1.0), 0.6, 1.15)
        emp.last_decision_month = self.month
        emp.current_behaviour = decision.action
        ev = self.emit("decision", emp.id, decision.action, [emp.id, emp.team_id] + ([decision.target] if decision.target else []),
                       {"workload": round(emp.workload, 2), "stress": round(emp.stress, 2)}, {"action": decision.action},
                       causes + self.recent_emp_causes(emp.id, months=2, limit=2),
                       f"{emp.name} ({self.teams[emp.team_id].name}) decided to {EMPLOYEE_ACTIONS.get(decision.action, MANAGER_ACTIONS.get(decision.action)).label.lower()}",
                       engine=decision.engine)
        self.decision_log.append({
            "month": self.month, "agent_id": emp.id, "agent_name": emp.name, "kind": kind, "team_id": emp.team_id,
            "triggers": triggers, "available": available, "action": decision.action, "target": decision.target,
            "probabilities": {k: round(v, 3) for k, v in decision.probabilities.items()}, "confidence": round(decision.confidence, 3),
            "engine": decision.engine, "latency_ms": round(decision.latency_ms, 1), "route": decision.route, "cached": decision.cached,
            "fallback": decision.fallback, "scores": decision.scores, "state_text": req.state_text(), "raw": decision.raw, "event_id": ev.id,
            "shadow_action": shadow_action,
        })
        from .interventions.primitives import apply_action
        apply_action(self, emp, decision, ev.id)

    def _route(self, d: AgentDecision, req: DecisionRequest) -> AgentDecision:
        """Confidence routing: high -> execute argmax; medium -> sample; low -> conservative heuristic."""
        cfg = self.config
        if d.confidence >= cfg.confidence_execute:
            d.route = "execute"
            d.action = max(d.probabilities, key=d.probabilities.get) if d.probabilities else d.action
        elif d.confidence >= cfg.confidence_probabilistic and d.probabilities:
            d.route = "probabilistic"
            d.action = self._sample(d.probabilities, req.agent_id)
        else:
            d.route = "conservative"
            h = self._heuristic.decide(req)
            # blend: conservative means we lean on rules but keep the model's preference as a vote
            mix = {a: 0.6 * h.probabilities.get(a, 0.0) + 0.4 * d.probabilities.get(a, 0.0) for a in req.available_actions}
            d.action = self._sample(mix, req.agent_id)
            d.raw = {**d.raw, "conservative_mix": {k: round(v, 3) for k, v in mix.items()}}
        return d

    def _guards(self, d: AgentDecision, emp: Employee, req: DecisionRequest) -> AgentDecision:
        """Downgrade-only guards grounded in state (never invent an action the engine did not choose)."""
        team = self.teams[emp.team_id]
        ctx = req.local_context
        reason = None
        if d.action == "use_workaround" and not (ctx.get("urgent_tasks", 0) > 0 and (ctx.get("manager_availability", 1.0) < 0.5 or emp.workload > 1.1)):
            reason = "workaround_without_urgency"
        elif d.action == "reduce_quality" and emp.workload <= 1.05:
            reason = "quality_cut_without_overload"
        elif d.action == "leave" and emp.turnover_intention < 0.2:
            reason = "leave_without_intention"
        elif d.action == "work_overtime" and emp.workload <= 1.0 and team.workload <= 1.0:
            reason = "overtime_without_demand"
        if reason:
            d.raw = {**d.raw, "guard": reason, "guarded_from": d.action}
            d.action = "continue_as_normal"
        return d

    def _sample(self, probs: dict[str, float], key: str = "") -> str:
        total = sum(max(0.0, v) for v in probs.values())
        if total <= 0:
            return "continue_as_normal"
        r = (self._r("decision", key) if key else self.rng.random()) * total
        acc = 0.0
        for k, v in probs.items():
            acc += max(0.0, v)
            if r <= acc:
                return k
        return next(iter(probs))

    def _pick_target(self, emp: Employee, action: str, options: list[str]) -> str:
        if action == "seek_help":
            # prefer teams where the employee has an informal tie, then the least loaded
            def score(tid):
                t = self.teams[tid]
                ties = sum(emp.relationships.get(m, 0.0) for m in t.member_ids)
                return (ties * 2.0) - t.workload
            return max(options, key=score)
        return sorted(options)[int(self._r("target", f"{emp.id}:{action}") * len(options)) % len(options)]

    # --------------------------------------------------------- 6. work processing
    def _process_work(self) -> None:
        cfg = self.config
        for t in self.teams.values():
            members = [m for m in self.active_members(t) if m.capacity_hours > 0]
            avail = {m.id: m.capacity_hours for m in members}   # capacity already includes any overtime decided this month
            mgmt_avail = t.management_capacity_hours
            by_id = {m.id: m for m in members}
            idx = {m.id: i for i, m in enumerate(members)}   # tie-break matching members' fixed order (was: stable sort of a filtered copy of this same list)
            for m in members:
                m.active_tasks = []

            # Picking "most spare hours, then most skilled" used to rebuild and sort a fresh
            # `skilled` list from scratch for every item (O(team_size log team_size) each,
            # cProfile showed this dominating a month's time at scale). One lazy-deletion
            # min-heap per distinct skill replaces that: `avail[m]` only ever decreases here,
            # so a heap entry's cached avail can only match the worker's current avail if it's
            # the most recently pushed one for that worker — any other is provably stale.
            skill_ids: dict[str, set[str]] = {}
            heaps: dict[str, list[tuple[float, float, int, str]]] = {}

            def pool_for(skill: str) -> set[str]:
                ids = skill_ids.get(skill)
                if ids is None:
                    ids = {m.id for m in members if m.skills.get(skill, 0.0) >= 0.2}
                    skill_ids[skill] = ids
                    heaps[skill] = [(-avail[mid], -by_id[mid].skills.get(skill, 0.0), idx[mid], mid) for mid in ids]
                    heapq.heapify(heaps[skill])
                return ids

            def pop_best(skill: str) -> Optional[Employee]:
                heap = heaps[skill]
                while heap:
                    neg_avail, _neg_skill, _i, mid = heap[0]
                    cur = avail[mid]
                    if cur <= 0.05:
                        heapq.heappop(heap)   # avail only decreases: permanently ineligible from here on
                        continue
                    if -neg_avail == cur:
                        return by_id[mid]
                    heapq.heappop(heap)       # stale — this worker's avail changed since this entry was pushed
                return None

            def bump(m: "Employee") -> None:
                """Refresh m's entry in every already-built skill-heap it belongs to, not just the
                one just used, so a stale entry elsewhere doesn't drop them from consideration there."""
                for skill, ids in skill_ids.items():
                    if m.id in ids:
                        heapq.heappush(heaps[skill], (-avail[m.id], -m.skills.get(skill, 0.0), idx[m.id], m.id))
            queue = [self.work_items[i] for i in t.queue if i in self.work_items and self.work_items[i].status in ("queued", "in_progress")]
            queue.sort(key=lambda w: (w.priority, w.created_month, w.id))
            still: list[str] = []
            expired = 0
            ai_avail = t.ai_capacity_hours
            t.ai_exceptions_this_month = 0
            for w in queue:
                p = self.processes[w.process_id]
                stage = p.stages[w.stage_index]
                if w.priority == 3 and w.status == "queued" and self.month > w.deadline_month + cfg.low_priority_expiry_months:
                    w.status = "expired"
                    expired += 1
                    continue
                # AI agents take eligible items first (bounded by their capacity); exceptions bounce back to humans
                if ai_avail > 0.5 and w.remaining_hours <= ai_avail and ai.eligible(t, w, stage, p):
                    ai_avail -= w.remaining_hours
                    if ai.handle_item(self, t, w, stage) == "done":
                        w.assignee_id = None
                        self._advance(w, t)
                        continue
                    self._flows.append({"item": w.id, "from": t.id, "to": t.id, "kind": w.kind, "priority": w.priority, "exception": True})
                if stage.approval and not w.workaround:
                    need = stage.hours_mean
                    mgr = self.employees.get(t.manager_id) if t.manager_id else None
                    can_self_approve = t.autonomy >= 0.75
                    has_approver = (mgr and mgr.status == "active" and mgr.absent_fraction < 1.0) or any(m.grade >= 5 or m.is_manager for m in members)
                    if ai.approval_by_ai(self, t, w, p):
                        w.remaining_hours = 0.0
                        self._advance(w, t)
                        continue
                    if (has_approver and mgmt_avail >= need) or can_self_approve:
                        if not can_self_approve:
                            mgmt_avail -= need
                            t._approval_hours_used = getattr(t, "_approval_hours_used", 0.0) + need
                        w.remaining_hours = 0.0
                        self._advance(w, t)
                    else:
                        t.approvals_waiting += 1
                        t._approval_hours_waiting = getattr(t, "_approval_hours_waiting", 0.0) + need
                        still.append(w.id)
                    continue
                # skill match
                skill = stage.skill
                pool_ids = pool_for(skill)

                def take(m: "Employee") -> None:
                    prof = m.skills.get(skill, 0.2)
                    rate = 0.55 + 0.45 * prof             # low proficiency = slower
                    can_do_hours = avail[m.id] * rate
                    done = min(w.remaining_hours, can_do_hours)
                    spent = done / rate
                    avail[m.id] -= spent
                    m.hours_worked += spent
                    w.remaining_hours -= done
                    w.status = "in_progress"
                    w.assignee_id = m.id
                    if w.id not in m.active_tasks:
                        m.active_tasks.append(w.id)
                    # learning by doing
                    if prof < 0.95 and self._r("learn", f"{m.id}:{w.id}") < 0.05:
                        m.skills[skill] = round(min(0.95, prof + 0.02), 2)
                    bump(m)

                picked_any = False
                if pool_ids:
                    # planned assignee first (personal ownership), then colleagues with the most spare hours
                    assignee = by_id.get(w.assignee_id) if w.assignee_id else None
                    if assignee is not None and assignee.id in pool_ids and avail[assignee.id] > 0.05:
                        take(assignee)
                        picked_any = True
                    while w.remaining_hours > 0.01:
                        m = pop_best(skill)
                        if m is None:
                            break
                        take(m)
                        picked_any = True
                if not picked_any:
                    still.append(w.id)
                    continue
                if w.remaining_hours <= 0.01:
                    assignee = self.employees.get(w.assignee_id) if w.assignee_id else None
                    if assignee and self._error_occurs(assignee, w):
                        w.errors += 1
                        t.errors_this_month += 1
                        w.remaining_hours = w.stage_hours * 0.4     # rework
                        w.status = "queued"
                        still.append(w.id)
                        self.emit("rework", assignee.id, "error", [assignee.id, t.id], {}, {"item": w.id, "kind": w.kind},
                                  self.recent_emp_causes(assignee.id, months=1, limit=1), f"Error on {w.kind} in {t.name}; rework required")
                        continue
                    self._advance(w, t)
                else:
                    still.append(w.id)
            t.queue = still
            t.expired_this_month = expired
            if expired >= 5:
                self.emit("work_dropped", t.id, "expired", [t.id], {}, {"items": expired}, self.recent_team_causes(t.id, months=3, limit=3),
                          f"{t.name} dropped {expired} stale low-priority requests", significant=expired >= 15)
            # overtime actually used
            for m in members:
                used_ot = max(0.0, m.hours_worked - m.capacity_hours)
                m.overtime_hours = min(m.overtime_hours, used_ot) if m.overtime_hours else 0.0

    def _error_occurs(self, e: Employee, w: WorkItem) -> bool:
        p = 0.02 + 0.08 * max(0.0, e.stress - 0.55) + 0.05 * max(0.0, e.workload - 1.1)
        if e.onboarding_months_left > 0:
            p += 0.04
        if e.effort_level < 0.9 or e.current_behaviour == "reduce_quality":
            p += 0.06
        if w.workaround:
            p += 0.05
        return self._r("error", w.id) < p

    def _advance(self, w: WorkItem, from_team: Team) -> None:
        p = self.processes[w.process_id]
        if w.stage_index + 1 >= len(p.stages):
            if w.ai_silent_error:
                ai.final_stage_silent_error(self, w, from_team)
            w.status = "done"
            w.completed_month = self.month
            w.assignee_id = None
            from_team.completed_this_month += 1
            from_team.completed_total += 1
            return
        self._move_item(w, w.stage_index + 1)

    def _move_item(self, w: WorkItem, new_stage: int, record_flow: bool = True, cause: Optional[int] = None) -> None:
        p = self.processes[w.process_id]
        old_team = self.resolve_team(w.team_id)
        stage = p.stages[new_stage]
        new_team = self.resolve_team(stage.team_id)
        if w.id in self.teams[old_team].queue and old_team != new_team:
            self.teams[old_team].queue.remove(w.id)
        w.stage_index = new_stage
        w.team_id = new_team
        w.stage_hours = self._stage_hours(stage, new_team, w.id)
        w.remaining_hours = w.stage_hours
        w.status = "queued"
        w.assignee_id = None
        w.workaround = False
        if w.ai_silent_error:
            ai.surface_silent_error(self, w, self.teams[new_team], old_team)
        if old_team != new_team:
            self.teams[new_team].queue.append(w.id)
            w.path.append((self.month, new_team))
            if record_flow:
                self._flows.append({"item": w.id, "from": old_team, "to": new_team, "kind": w.kind, "priority": w.priority, "ai": w.ai_handled})
        elif w.id not in self.teams[new_team].queue:
            self.teams[new_team].queue.append(w.id)

    def transfer_item(self, w: WorkItem, to_team: str, cause: int, reason: str) -> None:
        """Move a work item off its normal path to another team (help/redistribution)."""
        old = w.team_id
        if w.id in self.teams[old].queue:
            self.teams[old].queue.remove(w.id)
        w.team_id = to_team
        w.transferred = True
        w.status = "queued"
        w.assignee_id = None
        # a team without the exact skill works slower: stage hours inflate 25%
        stage = self.processes[w.process_id].stages[w.stage_index]
        if stage.skill not in self.teams[to_team].skills_provided:
            w.remaining_hours *= 1.25
        self.teams[to_team].queue.append(w.id)
        self.teams[to_team].transfers_in += 1
        self.teams[old].transfers_out += 1
        w.path.append((self.month, to_team))
        self._flows.append({"item": w.id, "from": old, "to": to_team, "kind": w.kind, "priority": w.priority, "transfer": True})

    # ----------------------------------------------------------- 7. psychology
    def _psychology(self) -> None:
        cfg = self.config
        for t in self.teams.values():
            members = [m for m in self.active_members(t) if m.status == "active"]
            backlog_m = t.backlog_hours / max(1.0, t.capacity_hours)
            mgr = self.employees.get(t.manager_id) if t.manager_id else None
            mgr_avail = max(0.0, 1.0 - t.management_load) if mgr and mgr.status == "active" else 0.0
            for m in members:
                mem_val = sum(tr.valence * tr.weight for tr in m.memory)
                for tr in m.memory:
                    tr.weight *= cfg.memory_decay
                m.memory = [tr for tr in m.memory if tr.weight > 0.05]
                target_stress = clamp(0.15 + 0.5 * max(0.0, m.workload - 0.9) + 0.15 * (m.overtime_hours / cfg.max_overtime_hours)
                                      + 0.2 * max(0.0, backlog_m - 0.6) + 0.1 * (1.0 - mgr_avail) - 0.05 * (m.morale - 0.5)
                                      - 0.1 * m.adaptability * max(0.0, m.workload - 1.0))
                m.stress = clamp(m.stress + cfg.stress_adapt * (target_stress - m.stress))
                target_morale = clamp(0.72 - 0.35 * m.stress + 0.15 * (m.trust_management - 0.5) + 0.1 * (t.morale - m.morale)
                                      + 0.2 * clamp(mem_val, -1, 1) + 0.05 * (m.engagement - 0.5))
                m.morale = clamp(m.morale + cfg.morale_adapt * (target_morale - m.morale))
                m.engagement = clamp(m.engagement + 0.1 * ((0.5 + 0.4 * m.morale + 0.1 * m.autonomy) - m.engagement))
                if m.workload > cfg.overload_threshold:
                    m.memory.append(MemoryTrace(self.month, "overload", -0.15, 0.6))
                    m.trust_management = clamp(m.trust_management - 0.01 * (1.0 - mgr_avail))
                    if not getattr(m, "_overloaded_last", False):
                        self.emit("employee_overloaded", m.id, "overloaded", [m.id, t.id], {"workload": round(getattr(m, "_prev_workload", 1.0), 2)},
                                  {"workload": round(m.workload, 2), "assigned_hours": round(m.assigned_hours), "capacity_hours": round(m.capacity_hours)},
                                  self.recent_team_causes(t.id, months=3, limit=3), f"{m.name} overloaded ({int(m.workload*100)}% of capacity)")
                    m._overloaded_last = True
                else:
                    m._overloaded_last = False
                    m.trust_management = clamp(m.trust_management + 0.005)
                m._prev_workload = m.workload
                ti_target = clamp(0.03 + 0.5 * max(0.0, m.stress - 0.5) + 0.45 * max(0.0, 0.5 - m.morale)
                                  + 0.1 * (1.0 - m.commitment) + 0.1 * cfg.job_market - 0.1 * m.institutional_knowledge
                                  - 0.05 * (m.trust_management - 0.5))
                m.turnover_intention = clamp(m.turnover_intention + 0.3 * (ti_target - m.turnover_intention))
                m.absence_probability = clamp(0.04 + 0.08 * max(0.0, m.stress - 0.6), 0.01, 0.3)
                # influence grows with help given
                m.influence = clamp(m.influence + 0.01 * m.help_given - 0.002)
                m.help_given = 0
            # informal ties decay slowly
            for m in members:
                for k in list(m.relationships):
                    m.relationships[k] *= 0.985
                    if m.relationships[k] < 0.05 or self.employees.get(k, None) is None or self.employees[k].status == "left":
                        del m.relationships[k]
        # management load bookkeeping (approvals + escalations relative to management hours)
        for t in self.teams.values():
            demand = getattr(t, "_approval_hours_used", 0.0) + getattr(t, "_approval_hours_waiting", 0.0) + getattr(t, "_escalation_hours", 0.0)
            t.management_load = clamp(0.5 + demand / max(1.0, t.management_capacity_hours) if t.management_capacity_hours > 0 else 1.5, 0.0, 3.0)
            t._approval_hours_used = 0.0
            t._approval_hours_waiting = 0.0
            t._escalation_hours = 0.0
            # rolling 12-month turnover
            t.turnover_12m = sum(1 for e in self.employees.values() if e.team_id == t.id and e.left_month is not None and e.left_month > self.month - 12)
            # automation pipeline delivers
            for ready, level in list(t.automation_pipeline):
                if ready <= self.month:
                    t.automation_pipeline.remove((ready, level))
                    before = t.automation_level
                    t.automation_level = clamp(t.automation_level + level, 0.0, 0.8)
                    self.emit("automation_live", t.id, "automation_live", [t.id], {"automation": before}, {"automation": t.automation_level},
                              self.recent_team_causes(t.id, months=12, limit=2), f"Automation live in {t.name}: routine work reduced to {int((1-t.automation_level)*100)}%", significant=True)

    # ---------------------------------------------------------- 8. information
    def _new_packet(self, kind: str, topic: str, origin: list[str], valence: float, seed_holders: list[str]) -> InfoPacket:
        self._packet_seq += 1
        p = InfoPacket(id=f"I{self._packet_seq:05d}", kind=kind, topic=topic, origin_id=origin[0] if origin else "management",
                       month=self.month, holders=set(seed_holders), valence=valence)
        self.info_packets[p.id] = p
        return p

    def _information(self) -> None:
        cfg = self.config
        for p in list(self.info_packets.values()):
            if self.month - p.month > 8:
                del self.info_packets[p.id]
                continue
            new_holders = set()
            for h in list(p.holders):
                e = self.employees.get(h)
                if not e or e.status != "active":
                    continue
                share_p = cfg.info_share_base * (0.5 + e.collaboration_tendency)
                if e.current_behaviour == "share_information":
                    share_p = 0.95
                if self._r("share", f"{p.id}:{h}") < share_p and e.relationships:
                    rel = list(e.relationships)
                    tgt = rel[int(self._r("share_to", f"{p.id}:{h}") * len(rel)) % len(rel)]
                    if tgt not in p.holders and tgt in self.employees and self.employees[tgt].status == "active":
                        new_holders.add(tgt)
                        p.hops.append((self.month, h, tgt))
                        self._info_flows.append({"packet": p.id, "from": h, "to": tgt, "kind": p.kind})
                        if p.valence < 0:
                            self.employees[tgt].memory.append(MemoryTrace(self.month, f"heard_{p.kind}", p.valence * 0.5, 0.5))
            p.holders |= new_holders

    # --------------------------------------------------------------- 9. finance
    def _finance(self) -> None:
        cfg = self.config
        fiscal_month = ((self.month - 1) % 12) + 1 if self.month > 0 else 1
        for d in self.departments.values():
            if fiscal_month == 1 and self.month > 1:
                d.spend_ytd = 0.0
                for tid in d.team_ids:
                    self.teams[tid].spend_ytd = 0.0
        for t in self.teams.values():
            monthly = 0.0
            for m in self.active_members(t):
                monthly += m.salary / 12.0 * (m.contracted_hours / cfg.monthly_hours)
                if m.overtime_hours > 0 and t.overtime_allowed:
                    monthly += (m.salary / 12.0 / cfg.monthly_hours) * m.overtime_hours * cfg.overtime_cost_multiplier
            monthly += t.ai_agents * t.ai_monthly_cost_per_agent
            t.spend_ytd += monthly
            self.departments[t.dept_id].spend_ytd += monthly
        for d in self.departments.values():
            projected = d.spend_ytd / fiscal_month * 12
            was = d.hiring_frozen
            d.hiring_frozen = projected > d.budget_annual * 1.02 if not was else projected > d.budget_annual * 0.97
            if d.hiring_frozen and not was:
                self.emit("hiring_freeze", d.id, "freeze", [d.id] + d.team_ids, {"projected": round(projected)}, {"budget": round(d.budget_annual)},
                          self.recent_team_causes(d.team_ids[0], months=6, limit=2) if d.team_ids else [],
                          f"{d.name} projected to overspend; hiring frozen", significant=True)
            elif was and not d.hiring_frozen:
                self.emit("hiring_unfreeze", d.id, "unfreeze", [d.id] + d.team_ids, {}, {}, [], f"{d.name} hiring freeze lifted")

    # ---------------------------------------------------------------- 10. metrics
    def _compute_metrics(self) -> dict[str, Any]:
        active = [e for e in self.employees.values() if e.status in ("active", "leaving")]
        n = len(active)
        cap = sum(t.capacity_hours for t in self.teams.values())
        backlog = sum(t.backlog_hours for t in self.teams.values())
        frontline_done = sum(t.completed_this_month for t in self.teams.values() if t.function == "frontline")
        frontline_items = [w for w in self.work_items.values() if self.processes[w.process_id].frontline]
        done_this_month = [w for w in self.work_items.values() if w.completed_month == self.month]
        arrivals = sum(t.arrivals_this_month for t in self.teams.values())
        frontline_done_m = sum(1 for w in done_this_month if self.processes[w.process_id].frontline)
        frontline_arr = sum(1 for w in frontline_items if w.created_month == self.month)
        cycle = [w.completed_month - w.created_month for w in done_this_month]
        overdue = sum(1 for w in self.work_items.values() if w.status in ("queued", "in_progress") and w.deadline_month < self.month)
        spend = sum(t.spend_ytd for t in self.teams.values())
        leavers_12 = sum(v for m, v in self.leavers_by_month.items() if m > self.month - 12)
        transfers = sum(t.transfers_in for t in self.teams.values())
        reach = [len(p.holders) / max(1, n) for p in self.info_packets.values() if self.month - p.month <= 6]
        mgmt = [t.management_load for t in self.teams.values() if t.management_capacity_hours > 0]
        approvals_waiting = sum(t.approvals_waiting for t in self.teams.values())
        teams = {}
        for t in self.teams.values():
            teams[t.id] = {
                "headcount": len([m for m in self.active_members(t) if m.status == "active"]),
                "vacancies": len(t.vacancies),
                "capacity_hours": round(t.capacity_hours, 1),
                "backlog_hours": round(t.backlog_hours, 1),
                "backlog_months": round(t.backlog_hours / max(1.0, t.capacity_hours), 2),
                "queue": len(t.queue),
                "workload": round(t.workload, 3),
                "completed": t.completed_this_month,
                "arrivals": t.arrivals_this_month,
                "transfers_in": t.transfers_in,
                "transfers_out": t.transfers_out,
                "errors": t.errors_this_month,
                "dropped": getattr(t, "expired_this_month", 0),
                "morale": round(t.morale, 3),
                "stress": round(t.stress, 3),
                "management_load": round(t.management_load, 3),
                "approvals_waiting": t.approvals_waiting,
                "turnover_12m": t.turnover_12m,
                "spend_ytd": round(t.spend_ytd),
                "automation": round(t.automation_level, 2),
                "ai_agents": round(t.ai_agents, 1),
                "ai_capacity_hours": round(t.ai_capacity_hours, 1),
                "ai_exceptions": t.ai_exceptions_this_month,
                "ai_items": t.ai_items_this_month,
                "ai_exception_rate": round(t.ai_exception_rate, 3) if t.ai_agents > 0 else 0.0,
                "ai_supervision_coverage": round(t.ai_supervision_coverage, 3) if t.ai_agents > 0 else 1.0,
                "ai_incident": 1 if t.ai_incident else 0,
                "downstream_ai_errors": t.downstream_ai_errors_this_month,
                "supervisors": sum(1 for m in self.active_members(t) if m.role_kind == "supervisor"),
                "ai_cost_month": round(t.ai_agents * t.ai_monthly_cost_per_agent),
            }
        return {
            "month": self.month,
            "label": self.date_label(),
            "headcount": n,
            "vacancies": sum(len(t.vacancies) for t in self.teams.values()),
            "capacity_hours": round(cap, 1),
            "backlog_hours": round(backlog, 1),
            "backlog_months": round(backlog / max(1.0, cap), 3),
            "queue_items": sum(len(t.queue) for t in self.teams.values()),
            "arrivals": arrivals,
            "completed": len(done_this_month),
            "delivery": round(self._trailing_delivery(frontline_done_m, frontline_arr), 3),   # frontline throughput vs demand, 3-month trailing
            "frontline_completed": frontline_done_m,
            "cycle_time": round(sum(cycle) / len(cycle), 2) if cycle else 0.0,
            "overdue": overdue,
            "workload": round(sum(e.workload for e in active) / max(1, n), 3),
            "stress": round(sum(e.stress for e in active) / max(1, n), 3),
            "morale": round(sum(e.morale for e in active) / max(1, n), 3),
            "turnover_12m": leavers_12,
            "turnover_intention": round(sum(e.turnover_intention for e in active) / max(1, n), 3),
            "cost_ytd": round(spend),
            "monthly_cost": round(sum(e.salary / 12 for e in active)),
            "management_load": round(sum(mgmt) / max(1, len(mgmt)), 3),
            "approvals_waiting": approvals_waiting,
            "cooperation": transfers,
            "information_reach": round(sum(reach) / len(reach), 3) if reach else 0.0,
            "informal_ties": sum(len(e.relationships) for e in active),
            "errors": sum(t.errors_this_month for t in self.teams.values()),
            "dropped": sum(getattr(t, "expired_this_month", 0) for t in self.teams.values()),
            "ai_agents": round(sum(t.ai_agents for t in self.teams.values()), 1),
            "ai_exceptions": sum(t.ai_exceptions_this_month for t in self.teams.values()),
            "ai_items": sum(t.ai_items_this_month for t in self.teams.values()),
            "ai_capacity_share": round(sum(t.ai_capacity_hours for t in self.teams.values()) / max(1.0, cap + sum(t.ai_capacity_hours for t in self.teams.values())), 3),
            "ai_incidents": sum(1 for t in self.teams.values() if t.ai_incident),
            "downstream_ai_errors": sum(t.downstream_ai_errors_this_month for t in self.teams.values()),
            "supervisors": sum(1 for e in active if e.role_kind == "supervisor"),
            "ai_cost_month": round(sum(t.ai_agents * t.ai_monthly_cost_per_agent for t in self.teams.values())),
            "deskilling_index": ai.deskilling_index(self),
            "teams": teams,
        }

    def _trailing_delivery(self, done: int, arrived: int) -> float:
        hist = getattr(self, "_delivery_hist", [])
        hist.append((done, arrived))
        self._delivery_hist = hist[-3:]
        d = sum(x for x, _ in self._delivery_hist)
        a = sum(y for _, y in self._delivery_hist)
        return d / max(1, a)

    def _threshold_events(self, m: dict[str, Any]) -> None:
        cfg = self.config
        for tid, tm in m["teams"].items():
            key = f"{tid}:backlog"
            band = "critical" if tm["backlog_months"] > cfg.backlog_critical_months else "high" if tm["backlog_months"] > cfg.backlog_high_months else "normal"
            prev = self.threshold_state.get(key, "normal")
            if band != prev:
                self.threshold_state[key] = band
                team = self.teams[tid]
                if band in ("high", "critical") and (prev == "normal" or band == "critical"):
                    prev_m = self.metrics_history[-4]["teams"].get(tid, {}) if len(self.metrics_history) >= 4 else {}
                    self.emit("backlog_threshold", tid, f"backlog_{band}", [tid],
                              {"band": prev, "backlog_months": prev_m.get("backlog_months"), "capacity_hours": prev_m.get("capacity_hours"), "headcount": prev_m.get("headcount")},
                              {"band": band, "backlog_months": tm["backlog_months"], "capacity_hours": tm["capacity_hours"], "headcount": tm["headcount"]},
                              self.recent_team_causes(tid, months=4, limit=5),
                              f"{team.name} backlog {band}: {tm['backlog_months']:.1f} months of work waiting", significant=True)
                elif band == "normal":
                    self.emit("backlog_recovered", tid, "backlog_normal", [tid], {"band": prev}, {"band": band},
                              self.recent_team_causes(tid, months=4, limit=3), f"{team.name} backlog back to normal", significant=True)
            key = f"{tid}:mgmt"
            mband = "overloaded" if tm["management_load"] > 1.2 else "normal"
            if mband != self.threshold_state.get(key, "normal"):
                self.threshold_state[key] = mband
                if mband == "overloaded":
                    prev_m = self.metrics_history[-3]["teams"].get(tid, {}) if len(self.metrics_history) >= 3 else {}
                    self.emit("management_overload", tid, "management_overload", [tid], {"management_load": prev_m.get("management_load"), "approvals_waiting": prev_m.get("approvals_waiting")},
                              {"management_load": tm["management_load"], "approvals_waiting": tm["approvals_waiting"]},
                              self.recent_team_causes(tid, months=3, limit=4, kinds=STATE_CHANGING_KINDS | {"escalation"}), f"Management capacity in {self.teams[tid].name} overloaded", significant=True)
        key = "org:turnover"
        band = "high" if m["turnover_12m"] > max(4, 0.12 * m["headcount"]) else "normal"
        if band != self.threshold_state.get(key, "normal"):
            self.threshold_state[key] = band
            if band == "high":
                self.emit("turnover_spike", "organisation", "turnover_high", ["organisation"], {}, {"turnover_12m": m["turnover_12m"]},
                          [e.id for e in self.events[-40:] if e.kind == "employee_left"][-5:], f"Staff turnover high: {m['turnover_12m']} leavers in 12 months", significant=True)

    # --------------------------------------------------------------- rendering
    def _frame(self) -> dict[str, Any]:
        emps = []
        for e in self.employees.values():
            if e.status == "left" and (e.left_month is None or self.month - e.left_month > 1):
                continue
            x, z = self.layout["employees"].get(e.id, (0.0, 0.0))
            emps.append([e.id, e.team_id, round(x, 2), round(z, 2), round(e.workload, 2), round(e.stress, 2), round(e.morale, 2),
                         e.status, 1 if e.is_manager else 0, e.current_behaviour, len(e.active_tasks), e.onboarding_months_left, e.role_kind])
        teams = []
        for t in self.teams.values():
            tx, tz, r = self.layout["teams"][t.id]
            teams.append({"id": t.id, "name": t.name, "dept": t.dept_id, "x": round(tx, 2), "z": round(tz, 2), "r": round(r, 2),
                          "queue": len(t.queue), "backlog_months": round(t.backlog_hours / max(1.0, t.capacity_hours), 2),
                          "workload": round(t.workload, 2), "headcount": len([m for m in self.active_members(t) if m.status == "active"]),
                          "vacancies": len(t.vacancies), "management_load": round(t.management_load, 2), "morale": round(t.morale, 2),
                          "accepting": t.accepting_transfers, "automation": round(t.automation_level, 2), "function": t.function,
                          "ai_agents": round(t.ai_agents, 1), "ai_incident": t.ai_incident, "ai_paused": t.ai_paused_until >= self.month,
                          "ai_coverage": round(t.ai_supervision_coverage, 2), "ai_exception_rate": round(t.ai_exception_rate, 2) if t.ai_agents else 0,
                          "supervisors": sum(1 for m in self.active_members(t) if m.role_kind == "supervisor")})
        # process paths (team -> team edges with monthly volume) for rendering flows
        return {"month": self.month, "label": self.date_label(), "employees": emps, "teams": teams,
                "flows": self._flows[:400], "info_flows": self._info_flows[:200],
                "departments": [{"id": d.id, "name": d.name, "x": round(self.layout["departments"][d.id][0], 2),
                                 "z": round(self.layout["departments"][d.id][1], 2), "r": round(self.layout["departments"][d.id][2], 2),
                                 "hiring_frozen": d.hiring_frozen} for d in self.departments.values()],
                "new_events": [to_dict(ev) for ev in self.events if ev.month == self.month and ev.significant]}

    # ------------------------------------------------------------- fork / save
    def fork(self, label: str, decision_engine: Optional[AgentDecisionEngine] = None, record_frames: Optional[bool] = None) -> "World":
        """Deep-copy the world (identical RNG state) so baseline and intervention diverge only by the intervention."""
        engine = self.decision_engine
        self.decision_engine = None  # type: ignore
        heur = self._heuristic
        self._heuristic = None  # type: ignore
        by_action = self.agreement["by_action"]
        self.agreement["by_action"] = {k: dict(v) for k, v in by_action.items()}
        try:
            w = copy.deepcopy(self)
        finally:
            self.decision_engine = engine
            self._heuristic = heur
            self.agreement["by_action"] = defaultdict(lambda: {"model": 0, "rules": 0}, {k: dict(v) for k, v in by_action.items()})
        w.agreement["by_action"] = defaultdict(lambda: {"model": 0, "rules": 0}, {k: dict(v) for k, v in w.agreement["by_action"].items()})
        w.decision_engine = decision_engine or engine
        w._heuristic = heur
        w.label = label
        if record_frames is not None:
            w.record_frames = record_frames
        return w

    def agreement_report(self) -> dict[str, Any]:
        a = self.agreement
        return {"n": a["n"], "agreement_rate": round(a["agree"] / a["n"], 3) if a["n"] else None,
                "by_action": {k: dict(v) for k, v in sorted(a["by_action"].items(), key=lambda kv: -(kv[1]["model"] + kv[1]["rules"]))}}

    def structure(self) -> dict[str, Any]:
        """Static-ish description for the client: teams, departments, employees, process graph, layout."""
        return {
            "template": self.template, "seed": self.seed, "label": self.label,
            "departments": [to_dict(d) for d in self.departments.values()],
            "teams": [{**{k: v for k, v in to_dict(t).items() if k not in ("queue", "vacancies", "automation_pipeline")},
                       "position": self.layout["teams"][t.id]} for t in self.teams.values()],
            "employees": [{"id": e.id, "name": e.name, "role_title": e.role_title, "team_id": e.team_id, "dept_id": e.dept_id,
                           "grade": e.grade, "is_manager": e.is_manager, "manager_id": e.manager_id, "status": e.status,
                           "archetype": e.archetype, "skills": e.skills} for e in self.employees.values()],
            "processes": [{"id": p.id, "name": p.name, "kind": p.kind, "arrival_rate": p.arrival_rate, "frontline": p.frontline,
                           "origin": p.origin_team_id, "stages": [{"team_id": self.resolve_team(s.team_id), "skill": s.skill, "hours": s.hours_mean, "approval": s.approval} for s in p.stages]}
                          for p in self.processes.values()],
            "layout": {"teams": self.layout["teams"], "departments": self.layout["departments"]},
        }

    def employee_detail(self, eid: str) -> dict[str, Any]:
        e = self.employees[eid]
        t = self.teams[e.team_id]
        items = [self.work_items[i] for i in e.active_tasks if i in self.work_items]
        decisions = [d for d in self.decision_log if d["agent_id"] == eid][-12:]
        return {"employee": to_dict(e), "team": {"id": t.id, "name": t.name, "backlog_months": round(t.backlog_hours / max(1.0, t.capacity_hours), 2), "workload": round(t.workload, 2)},
                "manager": (self.employees[e.manager_id].name if e.manager_id in self.employees else None),
                "work": [{"id": w.id, "kind": w.kind, "priority": w.priority, "remaining_hours": round(w.remaining_hours, 1), "deadline_month": w.deadline_month} for w in items[:20]],
                "decisions": decisions,
                "position": self.layout["employees"].get(eid),
                "informal_ties": sorted(((k, round(v, 2), self.employees[k].name, self.employees[k].team_id) for k, v in e.relationships.items() if k in self.employees), key=lambda x: -x[1])[:8]}

    def team_detail(self, tid: str) -> dict[str, Any]:
        t = self.teams[tid]
        items = [self.work_items[i] for i in t.queue if i in self.work_items]
        by_kind: dict[str, int] = defaultdict(int)
        for w in items:
            by_kind[w.kind] += 1
        return {"team": {k: v for k, v in to_dict(t).items() if k not in ("queue",)},
                "queue_by_kind": dict(sorted(by_kind.items(), key=lambda kv: -kv[1])),
                "members": [{"id": m.id, "name": m.name, "role_title": m.role_title, "workload": round(m.workload, 2), "stress": round(m.stress, 2),
                             "morale": round(m.morale, 2), "status": m.status, "behaviour": m.current_behaviour, "is_manager": m.id == t.manager_id, "role_kind": m.role_kind}
                            for m in self.active_members(t)],
                "history": [{"month": h["month"], **h["teams"].get(tid, {})} for h in self.metrics_history[-36:]],
                "events": [to_dict(ev) for ev in self.events if tid in ev.entities and ev.significant][-15:]}

    def export_state(self) -> dict[str, Any]:
        return {"meta": {"template": self.template, "seed": self.seed, "label": self.label, "month": self.month,
                         "engine": getattr(self.decision_engine, "name", "?"), "config": self.config.to_dict(), "applied_changes": self.applied_changes},
                "metrics": self.metrics_history, "events": [to_dict(e) for e in self.events], "decisions": self.decision_log,
                "employees": [to_dict(e) for e in self.employees.values()],
                "teams": [{k: v for k, v in to_dict(t).items()} for t in self.teams.values()],
                "work_items": [to_dict(w) for w in self.work_items.values() if w.status != "done" or (w.completed_month or 0) >= self.month - 1]}


def cfg_max(world: World) -> float:
    return world.config.max_overtime_hours
