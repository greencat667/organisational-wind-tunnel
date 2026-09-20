"""Strongly validated structured change plan (the only thing the language model may produce)."""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Operation = Literal["reduce_capacity", "increase_capacity", "merge_teams", "remove_management_layer", "change_budget",
                    "change_demand", "enable_automation", "change_working_hours", "change_reporting", "remove_approval",
                    "add_approval", "shock", "deploy_ai_agents", "convert_to_supervisory", "ai_run_process"]
InterventionType = Literal["restructure", "headcount", "budget", "automation", "demand", "process", "shock", "structure"]


class Change(BaseModel):
    operation: Operation
    target: Optional[str | list[str]] = Field(default="all", description="team id, function tag (admin/frontline/support/income/technology/management), department name, or 'all'")
    amount: Optional[float] = Field(default=None, description="fraction: 0.2 = 20%; negative for cuts where relevant")
    teams: Optional[list[str]] = None        # merge_teams
    name: Optional[str] = None               # merge_teams
    autonomy_gain: Optional[float] = None    # remove_management_layer
    processes: Optional[list[str]] = None    # change_demand
    process: Optional[str] = None            # add/remove approval
    team: Optional[str] = None               # change_reporting / add_approval
    reports_to_team: Optional[str] = None
    kind: Optional[str] = None               # shock kind
    replace_leavers: Optional[bool] = None   # deploy_ai_agents: False = attrition-based downsizing
    delegate_approvals: Optional[bool] = None  # ai_run_process
    lag_months: Optional[int] = None         # AI ops: implementation lag

    @field_validator("amount")
    @classmethod
    def _bound(cls, v):
        if v is None:
            return v
        if abs(v) > 1.0 and abs(v) <= 100:   # model gave a percentage
            v = v / 100.0
        if abs(v) > 1.0:
            raise ValueError("amount must be a fraction between -1 and 1")
        return round(v, 4)


class ChangePlan(BaseModel):
    intervention_type: InterventionType
    summary: str = Field(default="", max_length=200)
    objectives: list[str] = Field(default_factory=list, max_length=6)
    changes: list[Change] = Field(min_length=1, max_length=6)
    protected_groups: list[str] = Field(default_factory=list, max_length=6)
    transition_period_months: int = Field(default=1, ge=1, le=36)
    source: str = "rules"          # apple_fm | rules | user

    @field_validator("objectives", "protected_groups", mode="before")
    @classmethod
    def _strs(cls, v):
        return [str(x)[:80] for x in (v or [])]


# JSON schema handed to the Apple Foundation Model (guided generation).
# IMPORTANT: Apple's on-device guided generation (via `fm serve`) hangs on nested array-of-object schemas,
# so the plan is FLAT: two change slots with enum-typed operations. validate_plan() folds them back into a list.
_OPS = list(Operation.__args__)
_TARGET_DESC = "one of: admin, frontline, support, income, technology, management, all, or a team name"
AFM_SCHEMA = {
    "type": "object", "additionalProperties": False, "title": "ChangePlan",
    "properties": {
        "intervention_type": {"type": "string", "enum": list(InterventionType.__args__)},
        "summary": {"type": "string", "description": "One sentence restating the requested change. Do not predict outcomes."},
        "operation_1": {"type": "string", "enum": _OPS},
        "target_1": {"type": "string", "description": _TARGET_DESC},
        "amount_percent_1": {"type": "integer", "description": "size of the change in percent (20 for 20%); negative for cuts of budget, hours or demand; 0 if not applicable"},
        "detail_1": {"type": "string", "description": "for merge_teams: the two team names separated by ' and '; for shock: funding_cut, demand_spike, staff_shortage or supplier_failure; for AI operations: 'no replacement' if leavers are not replaced, 'delegate approvals' if AI may approve, 'processes: name, name' to name workflows; else empty"},
        "operation_2": {"type": "string", "enum": _OPS + ["none"], "description": "a second change if the request contains one, else none"},
        "target_2": {"type": "string", "description": _TARGET_DESC + ", or empty"},
        "amount_percent_2": {"type": "integer"},
        "detail_2": {"type": "string"},
        "protected_groups": {"type": "string", "description": "groups explicitly protected or kept unchanged, comma separated (e.g. frontline); empty if none"},
        "transition_period_months": {"type": "integer"},
    },
    "required": ["intervention_type", "summary", "operation_1", "target_1", "amount_percent_1", "detail_1", "operation_2", "target_2",
                 "amount_percent_2", "detail_2", "protected_groups", "transition_period_months"],
}


def unflatten(raw: dict) -> dict:
    """Fold the flat AFM output into the list-shaped plan dict."""
    if "changes" in raw:
        return raw
    changes = []
    for i in (1, 2):
        op = raw.get(f"operation_{i}")
        if not op or op == "none":
            continue
        detail = (raw.get(f"detail_{i}") or "").strip()
        ch = {"operation": op, "target": (raw.get(f"target_{i}") or "all").strip() or "all", "amount_percent": raw.get(f"amount_percent_{i}")}
        if op == "merge_teams" and detail:
            ch["teams"] = [t.strip() for t in re.split(r"\s+and\s+|,|&", detail) if t.strip()][:2]
        if op == "shock" and detail:
            ch["kind"] = detail.lower().replace(" ", "_")
        if op in ("deploy_ai_agents", "convert_to_supervisory", "ai_run_process") and detail:
            d = detail.lower()
            if "no replacement" in d or "not replace" in d or "attrition" in d:
                ch["replace_leavers"] = False
            if "delegate" in d or "ai approv" in d:
                ch["delegate_approvals"] = True
            m = re.search(r"processes?:\s*([\w ,&-]+)", d)
            if m:
                ch["process_names"] = [x.strip() for x in m.group(1).split(",") if x.strip()]
        changes.append(ch)
    pg = raw.get("protected_groups") or []
    if isinstance(pg, str):
        pg = [x.strip() for x in pg.split(",") if x.strip()]
    return {**raw, "changes": changes, "protected_groups": pg, "objectives": raw.get("objectives") or []}


def validate_plan(data: dict) -> ChangePlan:
    """Coerce the model's flat output into a validated ChangePlan (never trust the model shape)."""
    data = unflatten(dict(data))
    changes = []
    for c in data.get("changes", []):
        amt = c.get("amount")
        if amt is None and c.get("amount_percent") is not None:
            amt = float(c["amount_percent"]) / 100.0
        op = c.get("operation")
        if op in ("reduce_capacity", "increase_capacity", "enable_automation", "deploy_ai_agents", "convert_to_supervisory", "ai_run_process") and amt is not None:
            amt = abs(amt)
        if op in ("change_budget", "change_working_hours") and amt is not None and amt > 0 and any(w in str(data.get("summary", "")).lower() for w in ("cut", "reduce", "fall", "decrease", "save")):
            amt = -amt
        if op == "change_demand" and amt is not None and amt > 0 and any(w in str(data.get("summary", "")).lower() for w in ("fall", "reduce", "decrease", "drop")):
            amt = -amt
        changes.append(Change(operation=op, target=c.get("target") or "all", amount=amt, teams=c.get("teams") or None,
                              kind=c.get("kind") or None, autonomy_gain=c.get("autonomy_gain"), processes=c.get("processes") or c.get("process_names"),
                              process=c.get("process"), team=c.get("team"), reports_to_team=c.get("reports_to_team"), name=c.get("name"),
                              replace_leavers=c.get("replace_leavers"), delegate_approvals=c.get("delegate_approvals"), lag_months=c.get("lag_months")))
    return ChangePlan(intervention_type=data.get("intervention_type", "restructure"), summary=data.get("summary", "")[:200],
                      objectives=data.get("objectives", []), changes=changes, protected_groups=data.get("protected_groups", []),
                      transition_period_months=max(1, min(36, int(data.get("transition_period_months") or 1))), source=data.get("source", "rules"))
