"""How individual choices outlast the month they're made in: habits, team norms, fatigue and hidden defects.

Without these, every agent action was a one-month nudge — overtime added hours this month, cutting corners raised this
month's error risk — so choices washed out and the same organisation behaved the same whoever was deciding. Each
mechanism here carries a choice forward in time or outward to other people, and records the decision that started it,
so WHY chains lead back to a person's choice:

* **Habits.** Coping strategies (cutting corners, overtime) persist for a few months while the pressure lasts, instead of
  being re-decided from scratch.
* **Team norms.** When colleagues cope a certain way, others are more likely to do the same (social proof). A norm is a
  slow-moving share of the team currently doing it; crossing a threshold is a timeline event caused by the people who
  set it.
* **Fatigue.** Sustained overtime accumulates and decays slowly, feeding stress, absence and the wish to leave.
* **Hidden defects.** Work finished while cutting corners, or pushed past an approval, can carry a defect that
  surfaces at the next team as rework, or after delivery as a correction — attributed to the decision that caused it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .model import Employee, MemoryTrace, Team, WorkItem

if TYPE_CHECKING:
    from .engine import World

HABIT_ACTIONS = ("reduce_quality", "work_overtime")
NORM_ACTIONS = ("reduce_quality", "work_overtime", "use_workaround", "seek_help")
NORM_LABELS = {"reduce_quality": "cutting corners", "work_overtime": "working overtime", "use_workaround": "bypassing approvals",
               "seek_help": "asking other teams for help"}


# ----------------------------------------------------------------------------- habits

def record_choice(world: "World", emp: Employee, action: str, event_id: int) -> None:
    """After a decision: a coping choice becomes a habit for a few months; choosing anything else ends the habit."""
    cfg = world.config
    emp.last_decision_event = event_id
    if action in HABIT_ACTIONS:
        emp.habit = action
        emp.habit_until = world.month + cfg.habit_months
        emp.habit_event = event_id
        if action == "work_overtime":
            emp.habit_overtime_hours = emp.overtime_hours
    elif action != "continue_as_normal":
        emp.habit = None


def apply_habits(world: "World") -> None:
    """Start of month, after capacity: people with a live habit keep coping the same way while still under pressure
    (last month's workload), without a fresh decision."""
    for e in world.employees.values():
        if e.status != "active" or not e.habit:
            continue
        if world.month > e.habit_until or e.workload < world.config.habit_min_workload:
            e.habit = None          # the pressure (or the habit's run) is over
            continue
        if e.habit == "work_overtime" and e.fatigue >= world.config.habit_fatigue_limit:
            e.habit = None          # can't keep it up: an exhausted person stops the extra hours, whatever the queue says
            continue
        e.current_behaviour = e.habit
        if e.habit == "reduce_quality":
            e.effort_level = max(e.effort_level, 1.1)
        elif e.habit == "work_overtime":
            e.overtime_hours = e.habit_overtime_hours
            e.capacity_hours += e.habit_overtime_hours


# ----------------------------------------------------------------------------- norms

def norm_context(team: Team) -> dict[str, float]:
    """Team norms as decision context (the rules and Laya both see them)."""
    return {f"team_norm_{a}": round(team.norms.get(a, 0.0), 2) for a in NORM_ACTIONS}


def update_norms(world: "World") -> None:
    """End of month: each norm moves towards the share of the team currently behaving that way (slowly, so one person's
    month doesn't flip it). Crossing the threshold upward is an event caused by the people doing it."""
    cfg = world.config
    for t in world.teams.values():
        members = [m for m in world.active_members(t) if m.status == "active"]
        if not members:
            continue
        # influential people set norms: the manager and informal hubs count for more than a newcomer
        weight = {m.id: 0.5 + m.influence + (1.0 if m.id == t.manager_id else 0.0) for m in members}
        total = sum(weight.values())
        for a in NORM_ACTIONS:
            doing = [m for m in members if m.current_behaviour == a]
            share = sum(weight[m.id] for m in doing) / total
            before = t.norms.get(a, 0.0)
            after = before + cfg.norm_adapt * (share - before)
            t.norms[a] = after
            if before < cfg.norm_event_threshold <= after:
                causes = [m.habit_event if m.habit == a and m.habit_event is not None else m.last_decision_event for m in doing]
                world.emit("norm_shift", t.id, "norm_shift", [t.id] + [m.id for m in doing], {"norm": round(before, 2)}, {"norm": round(after, 2)},
                           [c for c in causes if c is not None][:4], f"{NORM_LABELS[a].capitalize()} is becoming normal in {t.name}",
                           significant=True)


# ----------------------------------------------------------------------------- fatigue

def update_fatigue(world: "World", e: Employee) -> None:
    cfg = world.config
    e.fatigue = min(1.0, e.fatigue * cfg.fatigue_decay + cfg.fatigue_per_overtime_month * (e.overtime_hours / cfg.max_overtime_hours))


# ----------------------------------------------------------------------------- hidden defects

def maybe_defect(world: "World", assignee: Optional[Employee], w: WorkItem) -> None:
    """A stage finished without a visible error may still carry a hidden defect if it was rushed."""
    if assignee is None:
        return
    cfg = world.config
    rushed = assignee.current_behaviour == "reduce_quality" or assignee.effort_level > 1.05
    if rushed and world._r("defect", f"{world._wkey(w)}:{w.stage_index}") < cfg.defect_probability_rushed:
        cause = assignee.habit_event if assignee.habit == "reduce_quality" and assignee.habit_event is not None else assignee.last_decision_event
        w.hidden_defect = True
        w.defect_cause = cause
        w.defect_origin = assignee.team_id


def bypass_defect(world: "World", w: WorkItem, cause: Optional[int], team_id: str) -> None:
    """An approval skipped by a workaround sometimes lets through something it would have caught."""
    if world._r("defect_bypass", f"{world._wkey(w)}:{w.stage_index}") < world.config.defect_probability_bypass:
        w.hidden_defect = True
        w.defect_cause = cause
        w.defect_origin = team_id


def surface_at_next_stage(world: "World", w: WorkItem, at_team: Team) -> None:
    w.hidden_defect = False
    w.errors += 1
    w.remaining_hours += w.stage_hours * world.config.defect_rework_share
    at_team.errors_this_month += 1
    at_team.downstream_defects_this_month += 1
    origin = world.teams.get(w.defect_origin or "")
    world.emit("defect_surfaced", at_team.id, "defect_surfaced", [at_team.id] + ([origin.id] if origin else []), {}, {"item": w.id, "kind": w.kind},
               [w.defect_cause] if w.defect_cause is not None else [],
               f"A rushed {w.kind} from {origin.name if origin else 'upstream'} needed rework in {at_team.name}")


def surface_after_delivery(world: "World", w: WorkItem, team: Team) -> None:
    """A defect in finished work comes back next month as a priority-1 correction on the team that finished it."""
    w.hidden_defect = False
    p = world.processes[w.process_id]
    world._item_seq += 1
    hours = max(0.5, w.stage_hours * world.config.defect_rework_share * 1.5)
    c = WorkItem(id=f"W{world._item_seq:06d}", process_id=p.id, kind=f"correction ({w.kind})", priority=1, stage_index=len(p.stages) - 1,
                 team_id=team.id, remaining_hours=hours, stage_hours=hours, created_month=world.month + 1, deadline_month=world.month + 2,
                 origin_team_id=team.id, rng_key=f"{world._wkey(w)}:correction")
    c.path.append((world.month + 1, team.id))
    world.work_items[c.id] = c
    world.scheduled.append({"month": world.month + 1, "op": "_enqueue", "team": team.id, "item": c.id})
    team.downstream_defects_this_month += 1
    world.emit("complaint", team.id, "correction_raised", [team.id], {}, {"item": c.id},
               [w.defect_cause] if w.defect_cause is not None else [], f"A delivered {w.kind} from {team.name} came back for correction")
