"""Context compression: build the compact local view an agent gets before deciding.

Agents never see the whole organisation. They see: their own state, their team, their
manager's availability, a few relationships, relevant work, recent organisational changes.
Everything is numbers or short labels so prompts stay tiny for Laya.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .behaviour import norm_context
from .decisions.base import DecisionRequest

if TYPE_CHECKING:
    from .engine import World


def _label(x: float, bands: list[tuple[float, str]]) -> str:
    for th, lab in bands:
        if x < th:
            return lab
    return bands[-1][1]


BACKLOG_BANDS = [(0.5, "low"), (1.0, "moderate"), (2.0, "high"), (99, "critical")]
AVAIL_BANDS = [(0.3, "very low"), (0.55, "low"), (0.8, "moderate"), (99, "good")]


def build_request(world: "World", emp, triggers: list[str], available: list[str],
                  targets: dict[str, list[str]], kind: str) -> DecisionRequest:
    team = world.teams[emp.team_id]
    mgr = world.employees.get(emp.manager_id) if emp.manager_id else None
    cfg = world.config
    cap = max(1.0, team.capacity_hours)
    backlog_months = team.backlog_hours / cap
    mgr_avail = 0.0
    if mgr and mgr.status == "active":
        mgr_avail = max(0.0, 1.0 - world.manager_load(mgr))
    neighbours = world.neighbour_teams(team.id)
    spare = 0.0
    spare_names = []
    for nt in neighbours:
        t = world.teams[nt]
        if t.accepting_transfers and t.workload < 0.9:
            spare = max(spare, 0.9 - t.workload)
            spare_names.append(t.name)
    recent = world.recent_change_labels(team.id, months=6)
    my_items = [world.work_items[i] for i in emp.active_tasks if i in world.work_items]
    urgent = sum(1 for w in my_items if w.priority == 1)
    overdue = sum(1 for w in my_items if w.deadline_month < world.month)
    agent_state = {
        "role": emp.role_title.lower(),
        "team": team.name,
        "workload": round(emp.workload, 2),
        "stress": round(emp.stress, 2),
        "morale": round(emp.morale, 2),
        "trust_management": round(emp.trust_management, 2),
        "turnover_intention": round(emp.turnover_intention, 2),
        "commitment": round(emp.commitment, 2),
        "collaboration_tendency": round(emp.collaboration_tendency, 2),
        "escalation_tendency": round(emp.escalation_tendency, 2),
        "risk_tolerance": round(emp.risk_tolerance, 2),
        "autonomy": round(emp.autonomy, 2),
        "adaptability": round(emp.adaptability, 2),
        "tenure_months": emp.experience_months,
        "archetype": emp.archetype,
    }
    ctx = {
        "team_workload": round(team.workload, 2),
        "team_backlog_months": round(backlog_months, 2),
        "team_backlog": _label(backlog_months, BACKLOG_BANDS),
        "team_headcount": f"{len([m for m in team.member_ids if world.employees[m].status != 'left'])} (was {team.baseline_headcount})",
        "team_vacancies": len(team.vacancies),
        "manager_availability": round(mgr_avail, 2),
        "manager_availability_label": _label(mgr_avail, AVAIL_BANDS),
        "my_tasks": len(my_items),
        "urgent_tasks": urgent,
        "overdue_tasks": overdue,
        "neighbour_spare_capacity": round(spare, 2),
        "neighbours_with_spare_capacity": spare_names[:3] or ["none"],
        "recent_changes": recent[:3] or ["none"],
        "job_market": cfg.job_market,
        "holds_unshared_information": 1.0 if world.unshared_info(emp) else 0.0,
    }
    ctx["my_role"] = emp.role_kind
    ctx.update(norm_context(team))                    # how colleagues are coping (social proof)
    if emp.fatigue > 0.05:
        ctx["my_fatigue"] = round(emp.fatigue, 2)
    if team.ai_agents > 0:
        ctx.update({
            "ai_agents_in_team": round(team.ai_agents, 1),
            "ai_share_of_capacity": round(team.ai_capacity_hours / max(1.0, team.capacity_hours + team.ai_capacity_hours), 2),
            "ai_exception_rate": round(team.ai_exception_rate, 2),
            "ai_supervision_coverage": round(team.ai_supervision_coverage, 2),
            "ai_incident_this_month": 1.0 if team.ai_incident else 0.0,
            "posts_replaced_when_people_leave": "no" if not team.replace_leavers else "yes",
        })
    if kind == "manager":
        members = [world.employees[m] for m in team.member_ids if world.employees[m].status == "active"]
        wl = [m.workload for m in members]
        ctx.update({
            "team_stress": round(team.stress, 2),
            "team_morale": round(team.morale, 2),
            "member_workload_spread": round((max(wl) - min(wl)) if wl else 0.0, 2),
            "vacancy_budget_available": 1.0 if world.can_open_vacancy(team) else 0.0,
            "hiring_frozen": 1.0 if (team.hiring_frozen or world.departments[team.dept_id].hiring_frozen) else 0.0,
            "transfers_in_recent": round(min(1.0, team.transfers_in / 10.0), 2),
            "frontline_share_waiting": round(world.frontline_share_waiting(team), 2),
            "automation_programme": 1.0 if world.automation_enabled(team) else 0.0,
            "approvals_waiting": team.approvals_waiting,
        })
    return DecisionRequest(agent_id=emp.id, agent_kind=kind, agent_state=agent_state, local_context=ctx,
                           available_actions=available, action_targets=targets, triggers=triggers, month=world.month)
