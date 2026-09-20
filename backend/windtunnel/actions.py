"""Bounded action catalogue shared by all decision engines.

Each action has: id, who may take it, a one-line question (used for Laya ``noul`` questions),
a tool docstring (used for Needle tools) and a short label for the UI. The *effects* of actions
live in ``engine.apply_action`` and are deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionSpec:
    id: str
    kind: str          # employee | manager | both
    label: str
    question: str      # Laya noul instruction
    tool_doc: str      # Needle tool docstring
    conservative: bool = False   # safe default when confidence is low


EMPLOYEE_ACTIONS: dict[str, ActionSpec] = {a.id: a for a in [
    ActionSpec("continue_as_normal", "both", "Continue as normal",
               "Should this employee simply keep working through their queue without changing anything?",
               "Make no change; keep working through the queue in priority order.", conservative=True),
    ActionSpec("seek_help", "employee", "Seek help",
               "Should this employee ask a neighbouring team or colleague with spare capacity to take some of their work?",
               "Ask a neighbouring team or colleague with spare capacity to take some of this employee's work."),
    ActionSpec("work_overtime", "employee", "Work overtime",
               "Should this employee work extra hours this month to clear the backlog?",
               "Work extra hours this month to clear the backlog personally."),
    ActionSpec("delay_low_priority", "employee", "Delay low-priority work",
               "Should this employee deliberately postpone low-priority tasks to a later month?",
               "Postpone the lowest-priority tasks to a later month."),
    ActionSpec("escalate_workload", "employee", "Escalate to manager",
               "Should this employee formally raise their overload with their manager and ask for a decision?",
               "Raise the overload formally with the line manager and ask for a decision."),
    ActionSpec("use_workaround", "employee", "Use workaround",
               "Should this employee bypass the normal approval step to get urgent work moving faster?",
               "Bypass the normal approval step so urgent work moves faster (accepting more risk of error)."),
    ActionSpec("reduce_quality", "employee", "Cut corners",
               "Should this employee cut corners on quality to get through more work?",
               "Get through more work by spending less time on each item (more errors likely)."),
    ActionSpec("share_information", "employee", "Share information",
               "Should this employee pass on what they know about recent changes to colleagues they trust?",
               "Pass on what this employee knows about recent changes to trusted colleagues."),
    ActionSpec("apply_for_internal_job", "employee", "Apply for internal vacancy",
               "Should this employee apply for an open vacancy in another team?",
               "Apply for an open vacancy in another team."),
    ActionSpec("leave", "employee", "Resign",
               "Should this employee resign from the organisation?",
               "Resign from the organisation and serve notice."),
    ActionSpec("verify_ai_output", "employee", "Double-check AI output",
               "Should this employee spend part of the month checking the AI agents' output before it goes out?",
               "Spend about a tenth of the month checking the AI agents' output before it leaves the team (slower, fewer hidden defects)."),
]}

MANAGER_ACTIONS: dict[str, ActionSpec] = {a.id: a for a in [
    EMPLOYEE_ACTIONS["continue_as_normal"],
    ActionSpec("redistribute_work", "manager", "Redistribute work",
               "Should this manager move work from overloaded team members to those with spare capacity?",
               "Move work items from overloaded team members to members with spare capacity."),
    ActionSpec("request_recruitment", "manager", "Request recruitment",
               "Should this manager request a new hire for the team?",
               "Open a vacancy and start recruiting for the team (takes months and needs budget)."),
    ActionSpec("approve_overtime", "manager", "Approve overtime",
               "Should this manager approve paid overtime for the team this quarter?",
               "Allow the team to work paid overtime for the next three months."),
    ActionSpec("protect_team", "manager", "Protect team",
               "Should this manager refuse to accept extra work transferred from other teams?",
               "Stop accepting work transferred in from other teams for the next three months."),
    ActionSpec("cancel_low_priority", "manager", "Cancel low-priority work",
               "Should this manager cancel the team's low-priority work items?",
               "Cancel the team's lowest-priority queued work items."),
    ActionSpec("escalate_up", "manager", "Escalate to director",
               "Should this manager escalate the team's capacity problem to their director?",
               "Escalate the team's capacity problem to the director for a decision."),
    ActionSpec("reprioritise", "manager", "Reprioritise",
               "Should this manager reorder the queue to prioritise frontline and urgent work first?",
               "Reorder the team's queue so urgent and frontline work is done first."),
    ActionSpec("automate_task", "manager", "Automate routine work",
               "Should this manager invest team time now in automating routine work?",
               "Invest team hours now to automate routine work (capacity gain arrives later)."),
    ActionSpec("share_information", "manager", "Brief the team",
               "Should this manager brief the team about recent organisational changes?",
               "Brief the team about recent organisational changes."),
    ActionSpec("pause_ai_agents", "manager", "Pause AI agents",
               "Should this manager pause the team's AI agents for a month after problems with their output?",
               "Pause the team's AI agents for a month (humans take all work; exceptions stop)."),
    ActionSpec("expand_ai_agents", "manager", "Expand AI agents",
               "Should this manager expand the team's AI agent pool by a fifth?",
               "Add 20% more AI agent capacity to the team (more supervision needed, live in two months)."),
    ActionSpec("retrain_staff", "manager", "Retrain staff as AI supervisors",
               "Should this manager retrain two officers as AI supervisors to close the supervision gap?",
               "Retrain two officers as supervisors of the AI agents (costs their time this month)."),
]}

ALL_ACTIONS = {**EMPLOYEE_ACTIONS, **MANAGER_ACTIONS}
