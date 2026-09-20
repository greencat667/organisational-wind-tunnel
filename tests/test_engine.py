"""Simulation physics, determinism and invariants."""
import copy
import pytest
from windtunnel.engine import World
from windtunnel.interventions.schema import validate_plan
from windtunnel.interventions.primitives import schedule_plan, resolve_targets, describe_plan
from windtunnel.orggen import generate_organisation, productive_hours


def make(seed=7, months=0):
    w = World("prototype", seed, "t")
    w.run(months)
    return w


def test_generation_sizes():
    d, t, e, p = generate_organisation("prototype", 7)
    assert len(e) == 100 and len(t) == 8 and len(p) >= 10
    assert all(tm.manager_id in e for tm in t.values())
    d2, t2, e2, p2 = generate_organisation("charity500", 7, scale=1.15)
    assert 450 <= len(e2) <= 550


def test_determinism_same_seed():
    a = make(7, 12); b = make(7, 12)
    assert a.metrics_history == b.metrics_history
    assert [e.description for e in a.events] == [e.description for e in b.events]


def test_different_seed_differs():
    a = make(7, 12); b = make(8, 12)
    assert a.metrics_history[-1]["queue_items"] != b.metrics_history[-1]["queue_items"] or a.events[-1].description != b.events[-1].description


def test_fork_identical_without_intervention():
    base = make(7, 3)
    f = base.fork("f")
    for _ in range(12):
        base.step(); f.step()
    assert base.metrics_history[-1] == f.metrics_history[-1]


def test_capacity_arithmetic_invariants():
    w = make(7, 6)
    for e in w.employees.values():
        if e.status == "active":
            # nobody works more than contracted + overtime cap
            assert e.hours_worked <= e.contracted_hours + w.config.max_overtime_hours + 1e-6
    for t in w.teams.values():
        assert t.capacity_hours >= 0
        assert t.management_capacity_hours >= 0


def test_work_not_completed_twice_and_terminated_do_nothing():
    w = make(7, 8)
    done = [x for x in w.work_items.values() if x.status == "done"]
    assert done
    assert all(x.completed_month is not None for x in done)
    for e in w.employees.values():
        if e.status == "left":
            assert not e.active_tasks
    # a done item is in no team queue
    queued = {i for t in w.teams.values() for i in t.queue}
    assert not any(x.id in queued for x in done)


def test_queue_grows_when_arrival_exceeds_capacity():
    w = make(7, 3)
    w.global_demand = 2.5
    q0 = w.metrics_history[-1]["backlog_months"]
    w.run(6)
    assert w.metrics_history[-1]["backlog_months"] > q0 * 2


def test_budget_freeze_blocks_hiring():
    w = make(7, 3)
    d = w.departments["finance"]
    d.hiring_frozen = True
    t = w.teams["finance"]
    assert not w.can_open_vacancy(t)


def test_intervention_reduces_admin_headcount_and_protects_frontline():
    base = make(7, 3)
    w = base.fork("i")
    plan = validate_plan({"intervention_type": "restructure", "summary": "admin -20%", "changes": [{"operation": "reduce_capacity", "target": "admin", "amount": 0.2}],
                          "protected_groups": ["frontline"], "transition_period_months": 3})
    lines = describe_plan(w, plan)
    assert any("Remove" in l for l in lines)
    schedule_plan(w, plan)
    assert w.teams["programmes"].protected
    for _ in range(6):
        w.step(); base.step()
    admin_b = sum(len([m for m in base.active_members(base.teams[t]) if m.status == "active"]) for t in ("finance", "bizsupport"))
    admin_i = sum(len([m for m in w.active_members(w.teams[t]) if m.status == "active"]) for t in ("finance", "bizsupport"))
    assert admin_i <= admin_b - 3
    assert w.intervention_root is not None
    removed = [e for e in w.events if e.kind == "role_removed"]
    assert removed and all(w.intervention_root in e.causes for e in removed)


def test_merge_teams_and_layer_removal():
    w = make(7, 2)
    plan = validate_plan({"intervention_type": "structure", "summary": "merge", "changes": [{"operation": "merge_teams", "target": "all", "teams": ["fundraising", "comms"]}], "transition_period_months": 1})
    schedule_plan(w, plan); w.step()
    assert "comms" not in w.teams and w.resolve_team("comms") == "fundraising"
    assert all(w.employees[m].team_id == "fundraising" for m in w.teams["fundraising"].member_ids)
    w.step()  # work still flows to the merged team
    w2 = make(7, 2)
    plan2 = validate_plan({"intervention_type": "structure", "summary": "flatten", "changes": [{"operation": "remove_management_layer", "target": "management", "autonomy_gain": 0.3}], "transition_period_months": 1})
    schedule_plan(w2, plan2); w2.step()
    ceo = w2.teams["exec"].manager_id
    assert all(w2.employees[t.manager_id].manager_id == ceo for t in w2.teams.values() if t.id != "exec" and t.manager_id)


def test_event_causality_reaches_root():
    from windtunnel import analysis
    base = make(7, 3); w = base.fork("i")
    plan = validate_plan({"intervention_type": "restructure", "summary": "admin -20%", "changes": [{"operation": "reduce_capacity", "target": "admin", "amount": 0.2}], "protected_groups": ["frontline"], "transition_period_months": 1})
    schedule_plan(w, plan)
    for _ in range(18):
        w.step(); base.step()
    orders = analysis.causal_orders(w.events, w.intervention_root)
    assert len(orders) > 5
    ev = next(e for e in w.events if e.kind == "capacity_reduced")
    chain = analysis.why(w.events, ev.id)["chain"]
    assert chain[0]["kind"] == "intervention"


def test_resolve_targets_aliases():
    w = make(7)
    assert set(resolve_targets(w, "admin_roles")) == {"finance", "bizsupport"}
    assert resolve_targets(w, "frontline") == ["programmes"]
    assert resolve_targets(w, "Finance") == ["finance"]


def test_ai_agents_add_capacity_and_exceptions():
    w = make(7, 2)
    plan = validate_plan({"intervention_type": "automation", "summary": "ai", "changes": [{"operation": "deploy_ai_agents", "target": "admin", "amount": 0.5}], "transition_period_months": 3})
    schedule_plan(w, plan); w.run(8)
    m = w.metrics_history[-1]
    assert m["ai_agents"] > 0
    assert any(e.kind == "ai_agents_live" for e in w.events)


def test_export_roundtrip_json():
    import json
    w = make(7, 4)
    s = json.dumps(w.export_state())
    assert len(s) > 1000
