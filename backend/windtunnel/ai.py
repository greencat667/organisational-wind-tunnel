"""AI agent mechanics (organisational physics for non-human capacity).

Everything here is deterministic given state and the World's common random numbers. Nothing predicts an outcome;
these are the rules from which outcomes emerge:

* Agents supply routine capacity but need human **supervision hours**; short supervision → agents idle *and* drift.
* **Exceptions** (items agents cannot finish) return to humans at half the stage hours; the rate falls with
  maturity and supervision quality and rises with drift and after incidents.
* **Silent errors** pass as done but surface at the next stage (downstream team pays rework) or, on the final stage,
  as a correction item a month later — quality leakage across team boundaries.
* **Incidents** (outage / model regression) take agents offline for a month and double exceptions briefly.
* **Skill atrophy**: when agents do ≥70% of a skill's routine work, officers who no longer practise it lose proficiency,
  which slows exception handling later (deskilling).
* **Attrition-based downsizing**: with ``replace_leavers=False`` posts are not backfilled while agents cover the work.
* **Delegated approvals** let an AI loop approve non-urgent items (faster, but silent-error prone); kept human, the
  approval step becomes the constraint.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from .model import MemoryTrace, Team, WorkItem

if TYPE_CHECKING:
    from .engine import World


def supervisors(world: "World", team: Team):
    return [m for m in world.active_members(team) if m.status == "active" and m.role_kind == "supervisor"]


def supervision_hours_needed(world: "World", team: Team) -> float:
    if team.ai_agents <= 0:
        return 0.0
    sups = supervisors(world, team)
    skill = (sum(m.skills.get("ai_supervision", 0.0) for m in sups) / len(sups)) if sups else 0.0
    per_agent = team.ai_supervision_hours * (1.0 - 0.5 * skill)
    return team.ai_agents * per_agent


def apply_capacity(world: "World", team: Team, members, cap: float) -> float:
    """Called from World._recompute_capacity. Deducts supervision from humans, sets AI capacity, coverage, exception rate.
    Returns the (reduced) human capacity."""
    cfg = world.config
    # pipeline deliveries
    for live, n_ag in list(team.ai_pipeline):
        if live <= world.month:
            team.ai_pipeline.remove((live, n_ag))
            before = team.ai_agents
            team.ai_agents += n_ag
            if team.ai_live_month is None:
                team.ai_live_month = world.month
            world.emit("ai_agents_live", team.id, "ai_agents_live", [team.id], {"agents": round(before, 1)}, {"agents": round(team.ai_agents, 1)},
                       world.recent_team_causes(team.id, months=12, limit=2), f"{team.ai_agents:.0f} AI agent-equivalents live in {team.name}", significant=True)
    team.ai_incident = False
    team.downstream_ai_errors_this_month = 0
    team.ai_items_this_month = 0
    team.ai_exceptions_this_month = 0
    team.verify_hours_this_month = 0.0
    if team.ai_agents <= 0 or not members:
        team.ai_supervision_used_hours = 0.0
        team.ai_capacity_hours = 0.0
        team.ai_supervision_coverage = 1.0
        return cap
    # incident?
    if world._r("ai_incident", team.id) < cfg.ai_incident_probability:
        team.ai_incident = True
        team.ai_incidents_total += 1
        world.emit("ai_incident", team.id, "ai_incident", [team.id], {}, {"agents": round(team.ai_agents, 1)},
                   world.recent_team_causes(team.id, months=6, limit=2), f"AI incident in {team.name}: agents offline this month", significant=True)
        for m in members:
            m.memory.append(MemoryTrace(world.month, "ai_incident", -0.15, 0.7))
    paused = team.ai_paused_until >= world.month
    # supervision: supervisors first, then other members
    need = supervision_hours_needed(world, team)
    sups = [m for m in members if m.role_kind == "supervisor"]
    others = [m for m in members if m.role_kind != "supervisor" and m.id != team.manager_id]
    covered = 0.0
    for m in sups:
        take = min(m.capacity_hours * 0.9, need - covered)
        if take <= 0:
            break
        m.capacity_hours -= take
        covered += take
    if covered < need and others:
        # Officers cover the gap from at most 25% of their time — and less when the team is stretched: checking agents'
        # output is the first thing to slip under a queue (last month's workload). Without this, supervision always won
        # over work, coverage never fell short and the drift/supervision-gap paths were never exercised.
        slack = world.config.ai_officer_supervision_share * max(0.0, min(1.0, (1.4 - team.workload) / 0.6))
        gap = need - covered
        pool = sum(m.capacity_hours * slack for m in others)
        take = min(gap, pool)
        for m in others:
            share = (m.capacity_hours * slack) / max(1e-6, pool)
            m.capacity_hours -= take * share
        covered += take
    cap -= covered
    team.ai_supervision_used_hours = covered
    team.ai_supervision_coverage = min(1.0, covered / need) if need > 0 else 1.0
    # effective exception rate: learning down, drift up, incident up
    months_live = (world.month - team.ai_live_month) if team.ai_live_month is not None else 0
    learn = 0.45 + 0.55 * math.exp(-months_live / cfg.ai_learning_months)
    drift = 1.0 + cfg.ai_drift_factor * (1.0 - team.ai_supervision_coverage)
    incident = 2.0 if team.ai_incident else 1.0
    team.ai_exception_rate = min(0.9, team.ai_base_exception_rate * learn * drift * incident)
    if team.ai_incident or paused:
        team.ai_capacity_hours = 0.0
    else:
        team.ai_capacity_hours = team.ai_agents * team.ai_hours_per_agent * team.ai_supervision_coverage
    return max(0.0, cap)


def ai_run_case(world: "World", w: WorkItem, process) -> bool:
    """Is this case one of the share an AI-run process handles end to end? One fixed draw per case (month pinned), so the
    same cases stay AI-run at every stage — 10% and 80% used to behave identically because every case qualified."""
    return process.ai_run_share > 0 and world._r("ai_run", world._wkey(w), month=0) < process.ai_run_share


def eligible(team: Team, w: WorkItem, stage, process, world: Optional["World"] = None) -> bool:
    if stage.approval:
        return False
    if process.ai_run_share > 0 and world is not None and ai_run_case(world, w, process):
        return True
    if stage.routine < team.ai_routine_threshold:
        return False
    if w.priority == 1 and not team.ai_handles_urgent:
        return False
    return True


def handle_item(world: "World", team: Team, w: WorkItem, stage) -> str:
    """Agents take the item. Returns 'done' | 'exception'. Caller advances or requeues."""
    team.ai_items_this_month += 1
    w.ai_handled = True
    silent_p = team.ai_silent_error_rate * (1.0 + (1.0 - team.ai_supervision_coverage)) * (0.5 if team.verify_hours_this_month > 0 else 1.0)
    if world._r("ai_exception", world._wkey(w)) < team.ai_exception_rate:
        team.ai_exceptions_this_month += 1
        w.ai_exception = True
        w.remaining_hours = w.stage_hours * 0.5
        w.ai_handled = False
        return "exception"
    if world._r("ai_silent", world._wkey(w)) < silent_p:
        w.ai_silent_error = True
    w.remaining_hours = 0.0
    return "done"


def approval_by_ai(world: "World", team: Team, w: WorkItem, process) -> bool:
    """Delegated approval: AI approves non-urgent items of an AI-run process."""
    if not process.ai_delegated_approvals or w.priority == 1 or team.ai_incident:
        return False
    if not ai_run_case(world, w, process):
        return False
    # the approving agents must actually be live (not still deploying, paused or down after an incident)
    if not any(world.teams[world.resolve_team(s.team_id)].ai_capacity_hours > 0 for s in process.stages
               if world.resolve_team(s.team_id) in world.teams):
        return False
    w.ai_approved = True
    if world._r("ai_approve_err", world._wkey(w)) < 2.0 * team.ai_silent_error_rate:
        w.ai_silent_error = True
    return True


def surface_silent_error(world: "World", w: WorkItem, at_team: Team, origin_team: str) -> None:
    """A hidden AI defect surfaces when the item reaches the next team: extra rework hours land there."""
    w.ai_silent_error = False
    w.errors += 1
    w.remaining_hours += w.stage_hours * 0.35
    at_team.downstream_ai_errors_this_month += 1
    at_team.errors_this_month += 1
    cause = _latest_ai_event(world, origin_team)
    world.emit("ai_quality_leak", origin_team, "silent_error_surfaced", [at_team.id, origin_team], {}, {"item": w.id, "kind": w.kind},
               [cause] if cause is not None else [], f"Hidden AI defect from {world.teams[origin_team].name if origin_team in world.teams else origin_team} surfaced in {at_team.name} ({w.kind})")


def final_stage_silent_error(world: "World", w: WorkItem, team: Team) -> None:
    """Defect in a completed item comes back as a priority-1 correction a month later."""
    w.ai_silent_error = False
    p = world.processes[w.process_id]
    world._item_seq += 1
    hours = max(0.5, w.stage_hours * 0.6)
    c = WorkItem(id=f"W{world._item_seq:06d}", process_id=p.id, kind=f"correction ({w.kind})", priority=1, stage_index=len(p.stages) - 1,
                 team_id=team.id, remaining_hours=hours, stage_hours=hours, created_month=world.month + 1, deadline_month=world.month + 2, origin_team_id=team.id)
    c.path.append((world.month + 1, team.id))
    world.work_items[c.id] = c
    world.scheduled.append({"month": world.month + 1, "op": "_enqueue", "team": team.id, "item": c.id})
    team.downstream_ai_errors_this_month += 1
    cause = _latest_ai_event(world, team.id)
    world.emit("ai_correction", team.id, "correction_raised", [team.id], {}, {"item": c.id}, [cause] if cause is not None else [],
               f"Correction needed on AI-completed {w.kind} in {team.name}")


def _latest_ai_event(world: "World", team_id: str):
    for ev in reversed(world.events):
        if ev.kind in ("ai_agents_live", "ai_process_live", "ai_agents_deployed", "ai_incident") and team_id in ev.entities:
            return ev.id
    return None


def monthly_learning_and_atrophy(world: "World") -> None:
    """Skill atrophy where agents do most routine work; supervisors' skill grows with practice."""
    cfg = world.config
    for t in world.teams.values():
        if t.ai_agents <= 0 or t.ai_live_month is None:
            continue
        routine_hours = sum(p.arrival_rate * s.hours_mean * s.routine for p in world.processes.values() for s in p.stages
                            if world.resolve_team(s.team_id) == t.id and not s.approval)
        share = min(1.0, t.ai_capacity_hours / max(1.0, routine_hours))
        for m in world.active_members(t):
            if m.status != "active":
                continue
            if m.role_kind == "supervisor":
                m.skills["ai_supervision"] = round(min(0.95, m.skills.get("ai_supervision", 0.4) + 0.01), 3)
                continue
            if share >= 0.5 and m.id != t.manager_id:
                prim = t.skills_provided[0] if t.skills_provided else None
                if prim and m.skills.get(prim, 0) > cfg.skill_atrophy_floor:
                    m.skills[prim] = round(max(cfg.skill_atrophy_floor, m.skills[prim] - cfg.skill_atrophy_per_month * share), 3)
                m.institutional_knowledge = max(0.2, m.institutional_knowledge - 0.004 * share)


def deskilling_index(world: "World") -> float:
    """Mean drop in primary-skill proficiency since the start, over staff in teams that have AI agents (0 = none)."""
    drops = []
    ai_teams = {t.id: t for t in world.teams.values() if t.ai_agents > 0}
    for e in world.employees.values():
        t = ai_teams.get(e.team_id)
        if e.status != "active" or not e.skill_at_start or t is None or e.role_kind != "officer":
            continue
        prim = t.skills_provided[0] if t.skills_provided else None
        if prim and prim in e.skill_at_start:
            drops.append(max(0.0, e.skill_at_start[prim] - e.skills.get(prim, e.skill_at_start[prim])))
    return round(sum(drops) / len(drops), 4) if drops else 0.0
