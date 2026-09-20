"""AI agent mechanics: capacity, supervision, exceptions, silent errors, incidents, atrophy, attrition, delegated approvals."""
from windtunnel.engine import World
from windtunnel import ai
from windtunnel.interventions.parser import rule_parse
from windtunnel.interventions.schema import validate_plan
from windtunnel.interventions.primitives import schedule_plan, describe_plan


def run_scenario(text, months=30, seed=7):
    base = World("prototype", seed, "baseline"); base.run(3)
    w = base.fork("intervention")
    plan = rule_parse(text)
    schedule_plan(w, plan)
    for _ in range(months):
        base.step(); w.step()
    return base, w, plan


def test_deploy_agents_creates_capacity_costs_and_exceptions():
    base, w, plan = run_scenario("Deploy AI agents to take 70% of routine finance and administrative work over 6 months.", months=18)
    m = w.metrics_history[-1]
    assert m["ai_agents"] > 5
    fin = w.teams["finance"]
    assert fin.ai_capacity_hours > 0 and fin.ai_live_month is not None
    assert sum(h["ai_exceptions"] for h in w.metrics_history) > 0
    assert sum(h["ai_items"] for h in w.metrics_history) > 100
    assert m["ai_cost_month"] > 0
    # implementation work landed on the target team and the technology team
    kinds = [x.kind for x in w.work_items.values() if x.kind == "AI deployment project"]
    assert len(kinds) >= 3
    assert any(x.team_id == "tech" for x in w.work_items.values() if x.kind == "AI deployment project")


def test_supervision_comes_off_human_capacity():
    base, w, _ = run_scenario("Deploy AI agents to take 80% of routine finance work.", months=12)
    fb = base.teams["finance"]; fi = w.teams["finance"]
    # same people, less human capacity because supervision hours are deducted
    assert fi.capacity_hours < fb.capacity_hours * 0.98
    assert 0 < fi.ai_supervision_coverage <= 1.0


def test_exception_rate_learns_down_and_drifts_up():
    w = World("prototype", 7, "t"); t = w.teams["finance"]
    t.ai_agents = 5; t.ai_live_month = 0; w.month = 0
    members = [m for m in w.active_members(t)]
    for m in members: m.capacity_hours = 100.0
    ai.apply_capacity(w, t, members, 1000.0)
    early = t.ai_exception_rate
    w.month = 24
    for m in members: m.capacity_hours = 100.0
    ai.apply_capacity(w, t, members, 1000.0)
    late = t.ai_exception_rate
    assert late < early
    # no humans to supervise -> agents idle, coverage 0, rate drifts up
    w.month = 25
    for m in members: m.capacity_hours = 0.0
    ai.apply_capacity(w, t, members, 0.0)
    assert t.ai_capacity_hours == 0.0 and t.ai_supervision_coverage == 0.0 and t.ai_exception_rate > late


def test_silent_errors_surface_downstream_with_causes():
    base, w, _ = run_scenario("Let AI run the procurement, invoicing and expenses workflows end to end for 90% of cases.", months=24)
    leaks = [e for e in w.events if e.kind in ("ai_quality_leak", "ai_correction")]
    assert leaks
    assert all(e.causes for e in leaks)
    assert sum(h["downstream_ai_errors"] for h in w.metrics_history) >= len(leaks) * 0.5


def test_attrition_based_downsizing_does_not_backfill():
    base, w, plan = run_scenario("Automate the back office: deploy AI agents to take 70% of routine finance, HR and administrative work over 6 months, and do not replace leavers in those teams.", months=36)
    assert plan.changes[0].replace_leavers is False
    assert not w.teams["finance"].replace_leavers
    admin_i = sum(len([m for m in w.active_members(w.teams[t]) if m.status == "active"]) for t in ("finance", "bizsupport"))
    admin_b = sum(len([m for m in base.active_members(base.teams[t]) if m.status == "active"]) for t in ("finance", "bizsupport"))
    assert admin_i < admin_b
    assert any(e.kind == "post_not_replaced" for e in w.events)


def test_supervisory_conversion_changes_roles_and_hires_keep_mix():
    base, w, _ = run_scenario("Convert half of the administrative and finance roles into supervisors of AI agent teams, with agents handling 80% of routine work.", months=30)
    sups = [e for e in w.employees.values() if e.status == "active" and e.role_kind == "supervisor"]
    assert len(sups) >= 6
    assert all("ai_supervision" in e.skills for e in sups)
    assert w.metrics_history[-1]["supervisors"] == len(sups)
    assert any(e.kind == "roles_converted" for e in w.events)


def test_delegated_approvals_pass_and_incidents_happen():
    base, w, plan = run_scenario("Let AI run the procurement, invoicing and expenses workflows end to end for 80% of cases, including approvals, with humans handling exceptions only.", months=30)
    assert plan.changes[0].delegate_approvals is True
    assert w.processes["procurement"].ai_delegated_approvals
    assert any(x.ai_approved for x in w.work_items.values())
    # with a 3%/month incident probability over 30 months and two teams, at least one incident is expected in this seed
    assert any(e.kind == "ai_incident" for e in w.events)


def test_skill_atrophy_bounded_and_index_reported():
    base, w, _ = run_scenario("Deploy AI agents to take 90% of routine finance work.", months=30)
    for e in w.employees.values():
        for k, v in e.skills.items():
            assert 0.0 <= v <= 1.0
            if e.team_id == "finance" and k in e.skill_at_start:
                assert v >= min(e.skill_at_start[k], w.config.skill_atrophy_floor) - 1e-9
    assert w.metrics_history[-1]["deskilling_index"] >= 0.0


def test_manager_ai_actions_available_when_relevant():
    w = World("prototype", 7, "t"); w.run(1)
    t = w.teams["finance"]; mgr = w.employees[t.manager_id]
    acts, _ = w.available_actions(mgr, "manager")
    assert "pause_ai_agents" not in acts
    t.ai_agents = 4; t.ai_capacity_hours = 400; t.ai_supervision_coverage = 0.6; t.programme_expandable = True
    acts, _ = w.available_actions(mgr, "manager")
    assert "pause_ai_agents" in acts and "retrain_staff" in acts
    off = next(m for m in w.active_members(t) if m.id != t.manager_id)
    acts, _ = w.available_actions(off, "employee")
    assert "verify_ai_output" in acts


def test_describe_plan_ai_lines():
    w = World("prototype", 7, "t")
    plan = rule_parse("Let AI run the procurement and invoicing workflows end to end for 80% of cases, including approvals.")
    lines = describe_plan(w, plan)
    assert any("Procurement" in l for l in lines) and any("delegated" in l for l in lines)
