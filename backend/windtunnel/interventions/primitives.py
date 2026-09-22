"""Deterministic effects.

* ``apply_action``  — what an agent's bounded decision does to the simulation state.
* ``apply_change``  — composable intervention primitives (reduce capacity, merge teams, ...).
* ``schedule_plan`` — expands a validated ChangePlan into month-scheduled primitives.

All effects are bounded by organisational physics: work must exist to be moved, hours cannot be
invented, money cannot be spent twice, terminated employees do nothing.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..model import MemoryTrace, WorkItem

if TYPE_CHECKING:
    from ..engine import World
    from ..decisions.base import AgentDecision
    from ..model import Employee
    from .schema import ChangePlan

# ----------------------------------------------------------------------------- agent actions


def apply_action(world: "World", emp: "Employee", d: "AgentDecision", cause: int) -> None:
    team = world.teams[emp.team_id]
    a = d.action
    cfg = world.config
    queue_items = [world.work_items[i] for i in team.queue if i in world.work_items and world.work_items[i].status in ("queued", "in_progress")]

    if a == "continue_as_normal":
        return

    if a == "seek_help":
        tgt = d.target or None
        if not tgt or tgt not in world.teams or not world.teams[tgt].accepting_transfers:
            return
        to_team = world.teams[tgt]
        # move up to 3 items the target could plausibly do (skill overlap), lowest priority number first
        moved = 0
        for w in sorted(queue_items, key=lambda w: (w.priority, w.created_month)):
            if w.transfer_count >= cfg.max_item_transfers:
                continue
            stage = world.processes[w.process_id].stages[w.stage_index]
            if stage.approval:
                continue
            if world.team_can_do(to_team, {stage.skill}):
                world.transfer_item(w, tgt, cause, "seek_help")
                moved += 1
                if moved >= 3:
                    break
        if moved:
            emp.help_requests_received += 0
            # informal tie strengthens with a helper in the target team
            helper = max((world.employees[m] for m in to_team.member_ids if world.employees[m].status == "active"),
                         key=lambda m: emp.relationships.get(m.id, 0.0), default=None)
            if helper:
                cap = cfg.max_relationships_per_person
                if helper.id in emp.relationships or len(emp.relationships) < cap:
                    emp.relationships[helper.id] = min(1.0, emp.relationships.get(helper.id, 0.0) + 0.25)
                if emp.id in helper.relationships or len(helper.relationships) < cap:
                    helper.relationships[emp.id] = min(1.0, helper.relationships.get(emp.id, 0.0) + 0.25)
                helper.help_given += 1
            emp.memory.append(MemoryTrace(world.month, "successful_collaboration", 0.2, 0.7))
            world.emit("work_transferred", emp.id, "seek_help", [team.id, tgt], {"items": len(queue_items)}, {"moved": moved},
                       [cause], f"{emp.name} passed {moved} {'item' if moved == 1 else 'items'} from {team.name} to {to_team.name}", significant=moved >= 3)
        return

    if a == "work_overtime":
        hours = min(cfg.max_overtime_hours, max(4.0, (emp.workload - 1.0) * emp.capacity_hours))
        emp.overtime_hours = hours
        emp.capacity_hours += hours          # hours exist this month only; cost & stress applied later
        emp.memory.append(MemoryTrace(world.month, "overtime", -0.05, 0.5))
        world.emit("overtime", emp.id, "work_overtime", [emp.id, team.id], {}, {"hours": round(hours, 1)}, [cause],
                   f"{emp.name} worked {hours:.0f} hours of overtime")
        return

    if a == "delay_low_priority":
        n = 0
        for w in queue_items:
            if w.priority == 3:
                w.deadline_month += 1
                w.delayed += 1
                w.priority = 3
                n += 1
        # low-priority items move to the back by bumping created_month ordering key
        for w in queue_items:
            if w.priority == 3:
                w.created_month = max(w.created_month, world.month)
        if n:
            world.emit("work_delayed", emp.id, "delay_low_priority", [team.id], {}, {"items": n}, [cause],
                       f"{emp.name} delayed {n} low-priority items in {team.name}")
        return

    if a == "escalate_workload":
        mgr = world.employees.get(emp.manager_id) if emp.manager_id else None
        if not mgr:
            return
        mteam = world.teams[mgr.team_id]
        mteam._escalation_hours = getattr(mteam, "_escalation_hours", 0.0) + 2.0
        ev = world.emit("escalation", emp.id, "escalate_workload", [emp.id, team.id, mgr.id], {}, {}, [cause],
                        f"{emp.name} escalated workload to {mgr.name}")
        # the manager gets a forced decision next month via trigger; here, if manager has capacity, respond now
        if mteam.management_load < 1.0 and mgr.status == "active":
            emp.trust_management = min(1.0, emp.trust_management + 0.03)
            emp.memory.append(MemoryTrace(world.month, "manager_support", 0.15, 0.7))
            _manager_redistribute(world, mgr, team, ev.id, max_items=2)
        else:
            emp.trust_management = max(0.0, emp.trust_management - 0.04)
            emp.memory.append(MemoryTrace(world.month, "escalation_ignored", -0.2, 0.8))
        return

    if a == "use_workaround":
        n = 0
        for w in queue_items:
            if world._next_stage_is_approval(w):
                w.workaround = True
                n += 1
                if n >= 3:
                    break
        # mark the approval stage skipped when the item reaches it
        for w in queue_items:
            if w.workaround:
                p = world.processes[w.process_id]
                if w.stage_index + 1 < len(p.stages) and p.stages[w.stage_index + 1].approval:
                    pass  # handled in _process_work: approval stage auto-passes when w.workaround
        if n:
            world.emit("workaround", emp.id, "use_workaround", [emp.id, team.id], {}, {"items": n}, [cause],
                       f"{emp.name} bypassed approvals on {n} items", significant=n >= 3)
        return

    if a == "reduce_quality":
        emp.effort_level = 1.1   # more throughput...
        emp.current_behaviour = "reduce_quality"   # ...more errors (see _error_occurs)
        world.emit("quality_reduced", emp.id, "reduce_quality", [emp.id, team.id], {}, {}, [cause], f"{emp.name} cut corners to get through work")
        return

    if a == "share_information":
        n = 0
        for p in world.unshared_info(emp):
            for r in list(emp.relationships)[:4]:
                if r not in p.holders and r in world.employees and world.employees[r].status == "active":
                    p.holders.add(r)
                    p.hops.append((world.month, emp.id, r))
                    world._info_flows.append({"packet": p.id, "from": emp.id, "to": r, "kind": p.kind})
                    n += 1
        if emp.is_manager and emp.id == team.manager_id:
            for m in world.active_members(team):
                m.trust_management = min(1.0, m.trust_management + 0.02)
                m.memory.append(MemoryTrace(world.month, "manager_briefing", 0.1, 0.5))
        if n or emp.is_manager:
            world.emit("information_shared", emp.id, "share_information", [emp.id, team.id], {}, {"recipients": n}, [cause],
                       f"{emp.name} briefed colleagues on recent changes")
        return

    if a == "apply_for_internal_job":
        tgt = d.target
        if not tgt or tgt not in world.teams or not world.teams[tgt].vacancies:
            return
        to_team = world.teams[tgt]
        v = to_team.vacancies.pop(0)
        old_team = team
        for wid in emp.active_tasks:
            w = world.work_items.get(wid)
            if w:
                w.status = "queued"; w.assignee_id = None
        emp.active_tasks = []
        old_team.member_ids.remove(emp.id)
        to_team.member_ids.append(emp.id)
        emp.team_id = tgt
        world._clear_member_cache()
        emp.dept_id = to_team.dept_id
        emp.manager_id = to_team.manager_id
        emp.onboarding_months_left = 2
        emp.turnover_intention *= 0.4
        emp.morale = min(1.0, emp.morale + 0.1)
        for s in to_team.skills_provided[:1]:
            emp.skills[s] = max(emp.skills.get(s, 0.0), 0.45)
        from ..layout import place_new_employee
        world.layout["employees"][emp.id] = place_new_employee(world.layout, tgt, len(to_team.member_ids) - 1)
        ev = world.emit("internal_move", emp.id, "apply_for_internal_job", [emp.id, old_team.id, tgt], {"team": old_team.id}, {"team": tgt}, [cause],
                        f"{emp.name} moved internally from {old_team.name} to {to_team.name}", significant=True)
        if world.can_open_vacancy(old_team):
            world._open_vacancy(old_team, emp.role, emp.grade, "internal_move", [ev.id])
        return

    if a == "leave":
        if emp.status != "active":
            return
        emp.status = "leaving"
        emp.leaving_month = world.month + cfg.turnover_notice_months
        emp.current_behaviour = "leaving"
        world.emit("resignation", emp.id, "leave", [emp.id, team.id], {"turnover_intention": round(emp.turnover_intention, 2)}, {},
                   [cause] + world.recent_emp_causes(emp.id, months=6, limit=4), f"{emp.name} resigned from {team.name}", significant=True)
        return

    # ------------------------------------------------------------- manager actions
    if a == "redistribute_work":
        _manager_redistribute(world, emp, team, cause, max_items=6)
        return

    if a == "request_recruitment":
        if world.can_open_vacancy(team):
            grade = max(2, min(5, round(sum(world.employees[m].grade for m in team.member_ids) / max(1, len(team.member_ids)))))
            world._open_vacancy(team, f"{team.id}_officer", grade, "growth", [cause])
            for m in world.active_members(team):
                m.memory.append(MemoryTrace(world.month, "manager_support", 0.1, 0.6))
        return

    if a == "approve_overtime":
        team.overtime_allowed = True
        world.scheduled.append({"month": world.month + 3, "op": "_expire_overtime", "team": team.id})
        world.emit("overtime_approved", emp.id, "approve_overtime", [team.id], {}, {}, [cause], f"{emp.name} approved overtime for {team.name}")
        return

    if a == "protect_team":
        team.accepting_transfers = False
        world.scheduled.append({"month": world.month + 3, "op": "_reopen_transfers", "team": team.id})
        world.emit("team_protected", emp.id, "protect_team", [team.id], {}, {}, [cause], f"{team.name} stopped accepting transferred work", significant=True)
        return

    if a == "cancel_low_priority":
        n = 0
        for w in queue_items:
            if w.priority == 3 and w.status == "queued":
                w.status = "cancelled"
                team.queue.remove(w.id)
                n += 1
                if n >= 8:
                    break
        if n:
            world.emit("work_cancelled", emp.id, "cancel_low_priority", [team.id], {}, {"items": n}, [cause], f"{emp.name} cancelled {n} low-priority items in {team.name}", significant=True)
        return

    if a == "escalate_up":
        director = world.employees.get(emp.manager_id) if emp.manager_id else None
        if not director:
            return
        dteam = world.teams[director.team_id]
        dteam._escalation_hours = getattr(dteam, "_escalation_hours", 0.0) + 3.0
        ev = world.emit("escalation", emp.id, "escalate_up", [team.id, director.id, dteam.id], {}, {}, [cause], f"{emp.name} escalated {team.name}'s capacity problem to {director.name}")
        # director may unlock recruitment if budget permits
        if dteam.management_load < 1.2 and world.can_open_vacancy(team) and team.workload > 1.2:
            world._open_vacancy(team, f"{team.id}_officer", 3, "escalation", [ev.id])
        return

    if a == "reprioritise":
        for w in queue_items:
            if world.processes[w.process_id].frontline and w.priority > 1:
                w.priority -= 1
        world.emit("reprioritised", emp.id, "reprioritise", [team.id], {}, {}, [cause], f"{emp.name} reprioritised {team.name}'s queue towards frontline work")
        return

    if a == "verify_ai_output":
        hours = emp.capacity_hours * cfg.verify_share
        emp.capacity_hours -= hours
        team.verify_hours_this_month += hours
        world.emit("ai_verified", emp.id, "verify_ai_output", [emp.id, team.id], {}, {"hours": round(hours, 1)}, [cause],
                   f"{emp.name} spent {hours:.0f}h checking AI output in {team.name}")
        return

    if a == "pause_ai_agents":
        team.ai_paused_until = world.month + 1
        team.ai_capacity_hours = 0.0
        world.emit("ai_paused", emp.id, "pause_ai_agents", [team.id], {}, {"until": team.ai_paused_until}, [cause],
                   f"{emp.name} paused {team.name}'s AI agents for a month", significant=True)
        return

    if a == "expand_ai_agents":
        add = round(max(0.5, team.ai_agents * 0.2), 1)
        team.ai_pipeline.append((world.month + 2, add))
        tech = world._team_with_skill("tech")
        _deployment_work(world, team, add, 2, tech)
        world.emit("ai_expanded", emp.id, "expand_ai_agents", [team.id], {"agents": team.ai_agents}, {"planned": add}, [cause],
                   f"{emp.name} expanded {team.name}'s AI agents by {add:.1f}", significant=True)
        return

    if a == "retrain_staff":
        members = [m for m in world.active_members(team) if m.status == "active" and m.role_kind == "officer" and m.id != team.manager_id]
        chosen = sorted(members, key=lambda m: -m.adaptability)[:2]
        for m in chosen:
            m.role_kind = "supervisor"
            m.role_title = f"AI Supervisor ({m.role_title})"
            m.skills["ai_supervision"] = round(min(0.9, 0.3 + 0.5 * m.adaptability), 2)
            m.capacity_hours = max(0.0, m.capacity_hours - 20.0)   # training time this month
            m.memory.append(MemoryTrace(world.month, "role_changed", 0.2 * (m.change_tolerance - 0.5), 0.9))
        if chosen:
            world.emit("staff_retrained", emp.id, "retrain_staff", [team.id] + [m.id for m in chosen], {}, {"n": len(chosen)}, [cause],
                       f"{emp.name} retrained {len(chosen)} officers as AI supervisors in {team.name}", significant=True)
        return

    if a == "automate_task":
        level = 0.2
        hours = cfg.automation_implementation_hours_per_level * level
        # implementation effort is real work: create an internal project item on the team's own queue
        p = world.internal_process(team.id)
        world._item_seq += 1
        w = WorkItem(id=f"W{world._item_seq:06d}", process_id=p.id, kind="automation project", priority=2, stage_index=0, team_id=team.id,
                     remaining_hours=hours, stage_hours=hours, created_month=world.month, deadline_month=world.month + 6, origin_team_id=team.id)
        w.path.append((world.month, team.id))
        # this item completes through normal processing; automation goes live after a fixed lag
        world.work_items[w.id] = w
        team.queue.append(w.id)
        team.automation_pipeline.append((world.month + 4, level))
        world.emit("automation_started", emp.id, "automate_task", [team.id], {"automation": team.automation_level}, {"target": team.automation_level + level},
                   [cause], f"{team.name} started automating routine work ({hours:.0f}h implementation)", significant=True)
        return


def _manager_redistribute(world: "World", mgr: "Employee", team, cause: int, max_items: int) -> None:
    members = [m for m in world.active_members(team) if m.status == "active"]
    if len(members) < 2:
        return
    moved = 0
    # within-team: rebalance this month's allocation evenly across members (ignoring stickiness), then offload to
    # neighbouring teams with spare capacity if the team as a whole is still over capacity
    queue_items = [world.work_items[i] for i in team.queue if i in world.work_items]
    world._allocate(team, [w for w in queue_items if w.status in ("queued", "in_progress")], members, balance=True)
    if team.workload <= 1.0:
        for m in members:
            m.trust_management = min(1.0, m.trust_management + 0.01)
        world.emit("work_redistributed", mgr.id, "redistribute_work", [team.id], {}, {"moved": 0, "rebalanced": True}, [cause],
                   f"{mgr.name} rebalanced work across {team.name}")
        return
    for nt in world.neighbour_teams(team.id):
        t = world.teams[nt]
        if t.function == "management" or not t.accepting_transfers or t.workload > 0.85:
            continue
        for w in sorted(queue_items, key=lambda w: (w.priority, w.created_month)):
            if w.transfer_count >= world.config.max_item_transfers:
                continue
            stage = world.processes[w.process_id].stages[w.stage_index]
            if stage.approval or w.team_id != team.id:
                continue
            if world.team_can_do(t, {stage.skill}):
                world.transfer_item(w, nt, cause, "redistribute")
                moved += 1
                if moved >= max_items:
                    break
        if moved >= max_items:
            break
    for m in members:
        m.trust_management = min(1.0, m.trust_management + 0.01)
    world.emit("work_redistributed", mgr.id, "redistribute_work", [team.id], {}, {"moved": moved}, [cause],
               f"{mgr.name} redistributed {moved} items from {team.name}" if moved else f"{mgr.name} reordered {team.name}'s work", significant=moved >= 4)


# ----------------------------------------------------------------------------- change primitives


def apply_change(world: "World", change: dict[str, Any]) -> None:
    op = change.get("op")
    root = world.intervention_root
    causes = [root] if root is not None else []
    if op == "_expire_overtime":
        world.teams[change["team"]].overtime_allowed = False
        return
    if op == "_reopen_transfers":
        world.teams[change["team"]].accepting_transfers = True
        return
    if op == "_ai_process_live":
        p = world.processes.get(change["process"])
        if p:
            p.ai_run_share = min(1.0, p.ai_run_share + float(change["share"]))
            p.ai_delegated_approvals = p.ai_delegated_approvals or bool(change.get("delegate", False))
            teams_touched = [world.resolve_team(s.team_id) for s in p.stages if not s.approval]
            world.emit("ai_process_live", "system", "ai_process_live", [p.id] + teams_touched, {}, {"share": p.ai_run_share, "delegate": p.ai_delegated_approvals},
                       [world.intervention_root] if world.intervention_root is not None else [],
                       f"AI now runs {p.name} for {int(p.ai_run_share*100)}% of cases" + (" and approves non-urgent items" if p.ai_delegated_approvals else ""), significant=True)
        return
    if op == "_enqueue":
        t = world.teams.get(change["team"]); w = world.work_items.get(change["item"])
        if t and w and w.id not in t.queue:
            w.status = "queued"
            t.queue.append(w.id)
        return
    if op == "_unfreeze_team":
        if change["team"] in world.teams and not any(c.get("op") == "reduce_capacity" and change["team"] in resolve_targets(world, c.get("target", "all")) for c in world.scheduled):
            world.teams[change["team"]].hiring_frozen = False
        return

    world.applied_changes.append(change)
    targets = resolve_targets(world, change.get("target", "all"))

    if op == "reduce_capacity":
        frac = float(change.get("amount", 0.1))
        for tid in targets:
            team = world.teams[tid]
            if team.protected:
                continue
            members = [m for m in world.active_members(team) if m.status == "active" and m.id != team.manager_id]
            # cumulative rounding across phased steps: remove exactly round(original * cumulative fraction) in total
            prog = world.__dict__.setdefault("_restructure_progress", {}).setdefault(tid, {"orig": len(members), "cum": 0.0, "removed": 0})
            prog["cum"] += frac
            n_remove = max(0, int(round(prog["orig"] * prog["cum"])) - prog["removed"])
            prog["removed"] += n_remove
            team.hiring_frozen = True
            world.scheduled.append({"month": world.month + 6, "op": "_unfreeze_team", "team": tid})
            # remove lowest tenure first (a realistic, not optimal, rule); managers stay
            members.sort(key=lambda m: (m.experience_months, m.id))
            removed = []
            for m in members[:n_remove]:
                m.status = "leaving"
                m.leaving_month = world.month  # takes effect this month via _people_flow next tick; make immediate:
                world._employee_leaves_restructure(m) if hasattr(world, "_employee_leaves_restructure") else _restructure_exit(world, m, causes)
                removed.append(m.name)
            team.baseline_headcount = max(1, team.baseline_headcount - n_remove)
            team.budget_annual *= (1 - frac * 0.9)
            world.departments[team.dept_id].budget_annual -= team.budget_annual * frac * 0.9 / max(0.01, 1 - frac * 0.9)
            world.intervention_targets.update([tid] + [m for m in team.member_ids])
            cap_before = team.capacity_hours
            ev = world.emit("capacity_reduced", "intervention", "reduce_capacity", [tid],
                            {"headcount": len(members) + 1, "capacity_hours": round(cap_before)},
                            {"headcount": len(members) + 1 - n_remove, "removed": n_remove, "capacity_hours": round(cap_before * (len(members) + 1 - n_remove) / max(1, len(members) + 1))},
                            causes, f"{team.name} reduced by {n_remove} roles ({int(frac*100)}%)", significant=True)
            for m in world.active_members(team):
                m.memory.append(MemoryTrace(world.month, "restructure", -0.35, 1.0))
                m.trust_management = max(0.0, m.trust_management - 0.08 * (1 - m.change_tolerance))
            world._new_packet("announcement", f"{team.name} restructured: {n_remove} roles removed", ["management"], -0.3,
                              seed_holders=[team.manager_id] if team.manager_id else [])
        return

    if op == "increase_capacity":
        frac = float(change.get("amount", 0.1))
        for tid in targets:
            team = world.teams[tid]
            n_add = max(1, int(round(len(team.member_ids) * frac)))
            team.baseline_headcount += n_add
            team.budget_annual *= (1 + frac)
            world.departments[team.dept_id].budget_annual += team.budget_annual * frac / (1 + frac)
            for _ in range(n_add):
                world._open_vacancy(team, f"{team.id}_officer", 3, "growth", causes)
            world.intervention_targets.add(tid)
            world.emit("capacity_increased", "intervention", "increase_capacity", [tid], {}, {"vacancies": n_add}, causes, f"{team.name} to grow by {n_add} roles", significant=True)
        return

    if op == "merge_teams":
        a, b = change["teams"][0], change["teams"][1]
        ta, tb = world.teams.get(a), world.teams.get(b)
        if not ta or not tb:
            return
        new_name = change.get("name") or f"{ta.name} & {tb.name}"
        for eid in tb.member_ids:
            e = world.employees[eid]
            e.team_id = a
            e.manager_id = ta.manager_id if eid != tb.manager_id else (world.employees[ta.manager_id].manager_id if ta.manager_id else None)
            if eid == tb.manager_id:
                e.is_manager = False   # one manager post removed (stays employed as senior officer)
            ta.member_ids.append(eid)
        world._clear_member_cache()
        ta.queue.extend(tb.queue)
        for wid in tb.queue:
            if wid in world.work_items:
                world.work_items[wid].team_id = a
        ta.skills_provided = sorted(set(ta.skills_provided) | set(tb.skills_provided))
        ta.budget_annual += tb.budget_annual
        ta.baseline_headcount += tb.baseline_headcount
        ta.vacancies.extend(tb.vacancies)
        ta.name = new_name
        world.departments[tb.dept_id].team_ids.remove(b)
        del world.teams[b]
        world.team_alias[b] = a
        # re-layout the merged team's members
        from ..layout import place_new_employee
        for i, eid in enumerate(ta.member_ids):
            world.layout["employees"][eid] = place_new_employee(world.layout, a, i)
        world.intervention_targets.update([a, b] + ta.member_ids)
        world.emit("team_merged", "intervention", "merge_teams", [a, b], {"teams": [a, b]}, {"team": a, "name": new_name}, causes,
                   f"{new_name}: teams merged ({len(ta.member_ids)} people, one manager)", significant=True)
        for eid in ta.member_ids:
            world.employees[eid].memory.append(MemoryTrace(world.month, "restructure", -0.2, 1.0))
        world._new_packet("announcement", f"Teams merged into {new_name}", ["management"], -0.1, seed_holders=[ta.manager_id] if ta.manager_id else [])
        return

    if op == "remove_management_layer":
        # team managers report directly to the CEO; director posts are removed from exec (they become senior advisers with no reports)
        exec_team = next((t for t in world.teams.values() if t.function == "management"), None)
        if not exec_team:
            return
        ceo = world.employees[exec_team.manager_id]
        removed = 0
        for eid in list(exec_team.member_ids):
            e = world.employees[eid]
            if e.id != ceo.id and e.is_manager:
                e.is_manager = False
                removed += 1
        for t in world.teams.values():
            if t.id != exec_team.id and t.manager_id:
                world.employees[t.manager_id].manager_id = ceo.id
            t.autonomy = min(1.0, t.autonomy + float(change.get("autonomy_gain", 0.3)))
        for d in world.departments.values():
            d.head_id = ceo.id
        world.intervention_targets.update([exec_team.id] + [t.manager_id for t in world.teams.values() if t.manager_id])
        world.emit("layer_removed", "intervention", "remove_management_layer", [exec_team.id], {"directors": removed}, {"directors": 0, "autonomy_gain": change.get("autonomy_gain", 0.3)},
                   causes, f"Management layer removed: {removed} director posts; {len(world.teams)-1} team leads report to the chief executive", significant=True)
        return

    if op == "change_budget":
        frac = float(change.get("amount", -0.1))
        for tid in targets:
            team = world.teams[tid]
            team.budget_annual *= (1 + frac)
            world.departments[team.dept_id].budget_annual += team.budget_annual * frac / (1 + frac)
            world.intervention_targets.add(tid)
            for m in world.active_members(team):
                m.memory.append(MemoryTrace(world.month, "budget_cut" if frac < 0 else "budget_increase", 0.3 * (1 if frac > 0 else -1), 0.8))
        world.emit("budget_changed", "intervention", "change_budget", list(targets), {}, {"amount": frac}, causes,
                   f"Budgets changed by {int(frac*100)}% for {len(targets)} teams", significant=True)
        return

    if op == "change_demand":
        frac = float(change.get("amount", 0.2))
        procs = change.get("processes") or [p.id for p in world.processes.values() if p.frontline]
        for pid in procs:
            if pid in world.demand_multiplier:
                world.demand_multiplier[pid] *= (1 + frac)
        world.intervention_targets.update(set(world.resolve_team(world.processes[p].stages[0].team_id) for p in procs if p in world.processes))
        world.emit("demand_changed", "intervention", "change_demand", list(world.intervention_targets)[:6], {}, {"amount": frac, "processes": procs},
                   causes, f"Demand changed by {int(frac*100)}% for {len(procs)} processes", significant=True)
        return

    if op == "enable_automation":
        for tid in targets:
            world.teams[tid].autonomy = world.teams[tid].autonomy  # no-op; flag read via applied_changes
            world.intervention_targets.add(tid)
        world.emit("automation_programme", "intervention", "enable_automation", list(targets), {}, {"target_level": change.get("amount", 0.4)},
                   causes, f"Automation programme enabled for {len(targets)} teams", significant=True)
        # initial project seeded: managers decide when to invest (automate_task action becomes available)
        return

    if op == "deploy_ai_agents":
        share = float(change.get("amount") or 0.3)
        lag = int(change.get("lag_months") or 3)
        replace = change.get("replace_leavers") is not False
        tech = world._team_with_skill("tech")
        for tid in targets:
            team = world.teams[tid]
            routine_hours = sum(p.arrival_rate * s.hours_mean * s.routine for p in world.processes.values() for s in p.stages
                                if world.resolve_team(s.team_id) == tid and not s.approval)
            agents = round(share * routine_hours / team.ai_hours_per_agent, 1)
            if agents <= 0:
                continue
            team.ai_pipeline.append((world.month + lag, agents))
            team.replace_leavers = replace
            team.programme_expandable = bool(change.get("expandable", True))
            if change.get("handles_urgent"):
                team.ai_handles_urgent = True
            world.intervention_targets.add(tid)
            _deployment_work(world, team, agents, lag, tech)
            world.emit("ai_agents_deployed", "intervention", "deploy_ai_agents", [tid] + ([tech.id] if tech else []), {"agents": team.ai_agents},
                       {"agents_planned": agents, "live_month": world.month + lag, "replace_leavers": replace}, causes,
                       f"{team.name}: {agents:.0f} AI agent-equivalents to take {int(share*100)}% of routine work (live in {lag} months"
                       f"{'; leavers not replaced' if not replace else ''})", significant=True)
            for m in world.active_members(team):
                m.memory.append(MemoryTrace(world.month, "ai_introduced", -0.1 + 0.3 * (m.change_tolerance - 0.5), 0.9))
            if not replace:
                world._new_packet("rumour", f"Posts in {team.name} will not be refilled once AI agents arrive", ["management"], -0.3,
                                  seed_holders=[m.id for m in world.active_members(team)][:3])
        return

    if op == "convert_to_supervisory":
        share = float(change.get("amount") or 0.3)
        for tid in targets:
            team = world.teams[tid]
            team.supervisory_share = min(1.0, team.supervisory_share + share)
            members = [m for m in world.active_members(team) if m.status == "active" and m.id != team.manager_id and m.role_kind == "officer"]
            n = int(round(len(members) * share))
            chosen = sorted(members, key=lambda m: -m.adaptability)[:n]
            for m in chosen:
                m.role_kind = "supervisor"
                m.role_title = f"AI Supervisor ({m.role_title})" if not m.role_title.startswith("AI Supervisor") else m.role_title
                m.skills["ai_supervision"] = round(min(0.9, 0.35 + 0.5 * m.adaptability), 2)
                m.autonomy = min(1.0, m.autonomy + 0.1)
                m.memory.append(MemoryTrace(world.month, "role_changed", 0.25 * (m.change_tolerance - 0.5), 0.9))
            for m in members:
                if m not in chosen:
                    m.memory.append(MemoryTrace(world.month, "colleagues_reassigned", -0.1, 0.7))
            # a team of supervisors with no agents yet gets a small pool so the role means something
            if team.ai_agents <= 0 and not team.ai_pipeline and n > 0:
                team.ai_pipeline.append((world.month + 2, float(n * 4)))
                team.programme_expandable = True
                world.intervention_targets.add(tid)
            world.intervention_targets.add(tid)
            world.emit("roles_converted", "intervention", "convert_to_supervisory", [tid] + [m.id for m in chosen], {}, {"converted": n}, causes,
                       f"{team.name}: {n} roles converted to supervising AI agents", significant=True)
            world._new_packet("announcement", f"{n} roles in {team.name} become AI supervisors", ["management"], 0.0,
                              seed_holders=[m.id for m in chosen][:3])
        return

    if op == "ai_run_process":
        share = float(change.get("amount") or 0.5)
        lag = int(change.get("lag_months") or 4)
        delegate = bool(change.get("delegate_approvals") or False)
        procs = _resolve_processes(world, change.get("processes")) or _eligible_processes(world, targets)
        tech = world._team_with_skill("tech")
        touched: set[str] = set()
        for pid in procs:
            p = world.processes.get(pid)
            if not p:
                continue
            world.scheduled.append({"month": world.month + lag, "op": "_ai_process_live", "process": pid, "share": share, "delegate": delegate})
            for s in p.stages:
                if not s.approval:
                    touched.add(world.resolve_team(s.team_id))
        for tid in touched:
            team = world.teams[tid]
            hours = sum(p.arrival_rate * s.hours_mean for pid in procs if pid in world.processes for p in [world.processes[pid]] for s in p.stages
                        if not s.approval and world.resolve_team(s.team_id) == tid) * share
            agents = round(hours / team.ai_hours_per_agent, 1)
            if agents > 0:
                team.ai_pipeline.append((world.month + lag, agents))
                team.programme_expandable = False
                world.intervention_targets.add(tid)
                _deployment_work(world, team, agents, lag, tech)
        world.emit("ai_process_planned", "intervention", "ai_run_process", list(procs) + sorted(touched), {}, {"share": share, "live_month": world.month + lag, "delegate_approvals": delegate},
                   causes, f"AI to run {len(procs)} workflow{'s' if len(procs) != 1 else ''} end to end for {int(share*100)}% of cases (live in {lag} months"
                   f"{'; approvals delegated to AI' if delegate else '; approvals stay human'})", significant=True)
        return

    if op == "change_working_hours":
        frac = float(change.get("amount", -0.1))
        for tid in targets:
            for m in world.active_members(world.teams[tid]):
                m.contracted_hours *= (1 + frac)
                m.morale = min(1.0, m.morale + (0.05 if frac < 0 else -0.03))
            world.intervention_targets.add(tid)
        world.emit("hours_changed", "intervention", "change_working_hours", list(targets), {}, {"amount": frac}, causes,
                   f"Contracted hours changed by {int(frac*100)}% for {len(targets)} teams", significant=True)
        return

    if op == "change_reporting":
        team_id = change.get("team")
        new_mgr_team = change.get("reports_to_team")
        if team_id in world.teams and new_mgr_team in world.teams and world.teams[new_mgr_team].manager_id:
            t = world.teams[team_id]
            if t.manager_id:
                world.employees[t.manager_id].manager_id = world.teams[new_mgr_team].manager_id
            world.intervention_targets.add(team_id)
            world.emit("reporting_changed", "intervention", "change_reporting", [team_id, new_mgr_team], {}, {}, causes,
                       f"{t.name} now reports into {world.teams[new_mgr_team].name}", significant=True)
        return

    if op == "remove_approval":
        pid = change.get("process")
        if pid in world.processes:
            p = world.processes[pid]
            p.stages = [s for s in p.stages if not s.approval] or p.stages
            world.emit("approval_removed", "intervention", "remove_approval", [pid], {}, {}, causes, f"Approval step removed from {p.name}", significant=True)
        return

    if op == "add_approval":
        pid = change.get("process")
        tid = change.get("team")
        if pid in world.processes and tid in world.teams:
            from ..model import ProcessStage
            p = world.processes[pid]
            p.stages.insert(min(1, len(p.stages)), ProcessStage(id=f"{pid}_approval", team_id=tid, skill="management", hours_mean=1.0, hours_sd=0.2, approval=True, routine=0.1))
            world.emit("approval_added", "intervention", "add_approval", [pid, tid], {}, {}, causes, f"New approval step added to {p.name} at {world.teams[tid].name}", significant=True)
        return

    if op == "shock":
        kind = change.get("kind")
        amt = float(change.get("amount", 0.1))
        if kind == "funding_cut":
            for t in world.teams.values():
                t.budget_annual *= (1 - amt)
            for d in world.departments.values():
                d.budget_annual *= (1 - amt)
        elif kind == "demand_spike":
            world.global_demand *= (1 + amt)
        elif kind == "staff_shortage":
            world.config.job_market = min(1.0, world.config.job_market + amt)
        elif kind == "supplier_failure":
            for p in world.processes.values():
                if "procurement" in p.id:
                    for s in p.stages:
                        s.hours_mean *= (1 + amt)
        world.emit("shock", "environment", kind or "shock", ["organisation"], {}, {"amount": amt}, causes, f"External shock: {kind} ({int(amt*100)}%)", significant=True)
        return


def _restructure_exit(world: "World", m: "Employee", causes: list[int]) -> None:
    team = world.teams[m.team_id]
    m.status = "left"
    world._clear_member_cache()
    m.left_month = world.month
    m.current_behaviour = "left"
    for wid in m.active_tasks:
        w = world.work_items.get(wid)
        if w:
            w.status = "queued"; w.assignee_id = None
    m.active_tasks = []
    world.leavers_by_month[world.month] += 0  # restructure exits are not voluntary turnover
    world.emit("role_removed", "intervention", "role_removed", [m.id, team.id], {"status": "active"}, {"status": "left"}, causes,
               f"{m.name}'s {m.role_title} post in {team.name} removed")


def resolve_targets(world: "World", target: Any) -> list[str]:
    """Map a plan target (team id, function tag, department, or 'all') to concrete team ids."""
    if isinstance(target, list):
        out: list[str] = []
        for t in target:
            out.extend(resolve_targets(world, t))
        return list(dict.fromkeys(out))
    if target in (None, "all"):
        return [t.id for t in world.teams.values() if t.function != "management"]
    if target in world.teams:
        return [target]
    tl = str(target).lower()
    alias = {"admin_roles": "admin", "administration": "admin", "administrative": "admin", "back_office": "admin",
             "frontline_delivery": "frontline", "frontline": "frontline", "delivery": "frontline", "support": "support",
             "income": "income", "technology": "technology", "management": "management"}
    fn = alias.get(tl, tl)
    by_fn = [t.id for t in world.teams.values() if t.function == fn]
    if by_fn:
        return by_fn
    by_dept = [t.id for d in world.departments.values() if d.name.lower() == tl or d.id == tl for t in world.teams.values() if t.dept_id == d.id]
    if by_dept:
        return by_dept
    by_name = [t.id for t in world.teams.values() if tl in t.name.lower()]
    return by_name


def schedule_plan(world: "World", plan: "ChangePlan") -> int:
    """Register the plan: creates the intervention root event and schedules primitives over the transition."""
    from ..model import to_dict
    root = world.emit("intervention", "intervention", plan.intervention_type, [], {}, {"plan": plan.model_dump()}, [],
                      f"Intervention: {plan.summary or plan.intervention_type}", significant=True)
    world.intervention_root = root.id
    world.intervention_month = world.month
    start = world.month + 1
    T = max(1, plan.transition_period_months)
    for pg in plan.protected_groups:
        for tid in resolve_targets(world, pg):
            world.teams[tid].protected = True
    for ch in plan.changes:
        d = ch.model_dump()
        additive = ch.operation in ("reduce_capacity", "change_budget", "change_working_hours", "increase_capacity", "deploy_ai_agents",
                                    "ai_run_process", "enable_automation", "convert_to_supervisory")
        multiplicative = ch.operation == "change_demand"
        if (additive or multiplicative) and T > 1 and abs(ch.amount or 0) > 0.05:
            # phase the change over the transition period (deterministic, evenly): up to 6 steps, or one per quarter
            steps = max(2, min(6, T // 3 if T >= 6 else T))
            amt = ch.amount or 0.0
            per = amt / steps if additive else (1.0 + amt) ** (1.0 / steps) - 1.0
            for k in range(steps):
                world.scheduled.append({**d, "op": ch.operation, "amount": per, "month": start + round(k * (T - 1) / (steps - 1)) if steps > 1 else start,
                                        "phase": f"{k+1}/{steps}"})
        else:
            world.scheduled.append({**d, "op": ch.operation, "month": start})
    return root.id


def describe_plan(world: "World", plan: "ChangePlan") -> list[str]:
    """Human-readable 'INTERPRETED CHANGE' lines computed against the actual organisation."""
    lines = []
    for ch in plan.changes:
        tids = resolve_targets(world, ch.target)
        names = ", ".join(world.teams[t].name for t in tids[:6]) + (" …" if len(tids) > 6 else "")
        if ch.operation == "reduce_capacity":
            n = sum(int(round((len(world.active_members(world.teams[t])) - 1) * (ch.amount or 0))) for t in tids)
            lines.append(f"Remove {n} posts ({int((ch.amount or 0)*100)}%) from: {names}")
        elif ch.operation == "increase_capacity":
            n = sum(max(1, int(round(len(world.teams[t].member_ids) * (ch.amount or 0)))) for t in tids)
            lines.append(f"Recruit {n} posts (+{int((ch.amount or 0)*100)}%) into: {names}")
        elif ch.operation == "merge_teams":
            lines.append("Merge teams: " + " + ".join(world.teams[t].name for t in (ch.teams or []) if t in world.teams))
        elif ch.operation == "remove_management_layer":
            lines.append(f"Remove director layer; team leads report to the chief executive; team autonomy +{int((ch.autonomy_gain or 0.3)*100)}%")
        elif ch.operation == "change_budget":
            lines.append(f"Budget {'+' if (ch.amount or 0) > 0 else ''}{int((ch.amount or 0)*100)}% for: {names}")
        elif ch.operation == "change_demand":
            lines.append(f"Demand {'+' if (ch.amount or 0) > 0 else ''}{int((ch.amount or 0)*100)}% for {len(ch.processes or [p.id for p in world.processes.values() if p.frontline])} processes")
        elif ch.operation == "enable_automation":
            lines.append(f"Automation programme (target {int((ch.amount or 0.4)*100)}% of routine work) in: {names}")
        elif ch.operation == "change_working_hours":
            lines.append(f"Contracted hours {int((ch.amount or 0)*100)}% for: {names}")
        elif ch.operation == "shock":
            lines.append(f"External shock: {ch.kind} {int((ch.amount or 0)*100)}%")
        elif ch.operation == "deploy_ai_agents":
            agents = 0.0
            for t in tids:
                rh = sum(p.arrival_rate * s.hours_mean * s.routine for p in world.processes.values() for s in p.stages if world.resolve_team(s.team_id) == t and not s.approval)
                agents += (ch.amount or 0.3) * rh / world.teams[t].ai_hours_per_agent
            lines.append(f"Deploy ≈{agents:.0f} AI agent-equivalents for {int((ch.amount or 0.3)*100)}% of routine work in: {names} (live in {ch.lag_months or 3} months)")
            lines.append("Leavers " + ("NOT replaced while agents cover the work" if ch.replace_leavers is False else "replaced as normal") + "; supervision, exceptions and implementation effort fall on staff")
        elif ch.operation == "convert_to_supervisory":
            n = sum(int(round((len(world.active_members(world.teams[t])) - 1) * (ch.amount or 0.3))) for t in tids)
            lines.append(f"Convert {n} roles ({int((ch.amount or 0.3)*100)}%) to supervising AI agents in: {names}")
        elif ch.operation == "ai_run_process":
            procs = ch.processes or _eligible_processes(world, tids)
            pn = ", ".join(world.processes[p].name for p in procs if p in world.processes) or "none eligible"
            lines.append(f"AI runs {int((ch.amount or 0.5)*100)}% of cases end to end for: {pn}")
            lines.append("Approvals " + ("delegated to AI for non-urgent items" if ch.delegate_approvals else "stay with human managers") + f"; live in {ch.lag_months or 4} months; exceptions return to staff")
        else:
            lines.append(f"{ch.operation} → {names or ch.target}")
    if plan.protected_groups:
        prot = []
        for pg in plan.protected_groups:
            prot += [world.teams[t].name for t in resolve_targets(world, pg)]
        lines.append("Protected: " + ", ".join(dict.fromkeys(prot)))
    lines.append(f"Transition: {plan.transition_period_months} months")
    lines.append("No other assumptions added.")
    return lines


def _deployment_work(world: "World", team, agents: float, lag: int, tech) -> None:
    """Implementation is real work: hours on the target team and on the technology team."""
    cfg = world.config
    for tid, hours in ((team.id, cfg.ai_deploy_hours_per_agent * agents), (tech.id if tech else None, cfg.ai_tech_hours_per_agent * agents)):
        if not tid or hours <= 0:
            continue
        p = world.internal_process(tid)
        world._item_seq += 1
        w = WorkItem(id=f"W{world._item_seq:06d}", process_id=p.id, kind="AI deployment project", priority=2, stage_index=0, team_id=tid,
                     remaining_hours=hours, stage_hours=hours, created_month=world.month, deadline_month=world.month + lag, origin_team_id=team.id)
        w.path.append((world.month, tid))
        world.work_items[w.id] = w
        world.teams[tid].queue.append(w.id)
        if tid != team.id:
            world.teams[tid].transfers_in += 1


def _eligible_processes(world: "World", targets: list[str]) -> list[str]:
    """Processes touching the target teams whose human stages are mostly routine."""
    out = []
    for p in world.processes.values():
        stages = [s for s in p.stages if not s.approval]
        if not stages:
            continue
        if any(world.resolve_team(s.team_id) in targets for s in stages) and sum(s.routine for s in stages) / len(stages) >= 0.5:
            out.append(p.id)
    return out


def _resolve_processes(world: "World", names) -> list[str]:
    if not names:
        return []
    out = []
    for n in names:
        nl = str(n).lower().strip()
        for p in world.processes.values():
            if nl == p.id or nl in p.name.lower() or nl in p.kind.lower() or p.id in nl:
                out.append(p.id)
    return list(dict.fromkeys(out))
