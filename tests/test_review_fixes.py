"""Regression tests for the 2026-09 review: lost work, runaway loops, cooperation, CRN, parser safety, WHY chains."""
from windtunnel import analysis
from windtunnel.engine import World
from windtunnel.interventions.parser import rule_parse
from windtunnel.interventions.primitives import describe_plan, schedule_plan

ADMIN_CUT = "Reduce administrative capacity by 20% while maintaining existing frontline delivery."


def _orphans(w: World) -> int:
    """Open items that sit in no team's queue (other than corrections deliberately scheduled for next month)."""
    pending = {c["item"] for c in w.scheduled if c.get("op") == "_enqueue"}
    return sum(1 for x in w.work_items.values() if x.status in ("queued", "in_progress")
               and x.id not in w.teams[x.team_id].queue and x.id not in pending)


def _pair(text=ADMIN_CUT, seed=7, months=24):
    b = World("prototype", seed, "baseline", record_frames=False); b.run(3)
    i = b.fork("intervention"); schedule_plan(i, rule_parse(text))
    for _ in range(months):
        b.step(); i.step()
    return b, i


def test_no_work_item_goes_missing():
    b, i = _pair()
    assert _orphans(b) == 0 and _orphans(i) == 0


def test_baseline_is_stable_without_intervention():
    w = World("prototype", 7, "b", record_frames=False); w.run(39)
    d = [h["delivery"] for h in w.metrics_history[6:]]
    assert min(d) > 0.85 and w.metrics_history[-1]["backlog_months"] < 0.5


def test_workload_and_errors_stay_bounded():
    _, i = _pair(seed=42, months=36)
    assert max(e.workload for e in i.employees.values() if e.status == "active") <= i.config.max_allocation_ratio + 0.5
    for t in i.teams.values():
        assert t.errors_this_month <= max(10, 0.4 * t.completed_this_month + 10)


def test_teams_can_help_each_other():
    w = World("prototype", 7, "b", record_frames=False); w.run(12)
    assert sum(h["cooperation"] for h in w.metrics_history) > 0


def test_low_priority_work_eventually_expires():
    _, i = _pair(seed=42, months=36)
    assert sum(h["dropped"] for h in i.metrics_history) > 0
    # delaying never moves deadlines or creation months
    assert all(x.created_month <= x.deadline_month for x in i.work_items.values())


def test_common_random_numbers_survive_extra_items():
    b = World("prototype", 7, "baseline", record_frames=False); b.run(3)
    i = b.fork("intervention")
    i._item_seq += 17          # an extra item in one world must not reshuffle everyone else's luck
    b.step(); i.step()
    key = lambda w: sorted((x.rng_key, x.priority, round(x.stage_hours, 3)) for x in w.work_items.values() if x.created_month == w.month)
    assert key(b) == key(i)


def test_overtime_is_recorded():
    w = World("prototype", 42, "b", record_frames=False); w.run(3)
    schedule_plan(w, rule_parse(ADMIN_CUT)); w.run(18)
    assert any(e.overtime_hours > 0 for e in w.employees.values()) or all(d["action"] != "work_overtime" for d in w.decision_log)


def test_parser_never_guesses():
    for text in ("Buy a new office building", "Introduce hybrid working", "", "credit control improvements"):
        p = rule_parse(text)
        assert p.changes == [] and p.warnings, text


def test_parser_negation_protection_and_clauses():
    p = rule_parse("Do not cut frontline staff")
    assert p.changes == [] and "frontline" in p.protected_groups
    p = rule_parse("Double the tech team")
    assert p.changes[0].operation == "increase_capacity" and p.changes[0].amount == 1.0
    p = rule_parse("Cut budgets by 10% while protecting frontline")
    assert p.changes[0].target == ["all"] and "frontline" in p.protected_groups
    p = rule_parse("Cut admin by 20% and hire 5 people into technology, but don't cut frontline")
    assert [c.operation for c in p.changes] == ["reduce_capacity", "increase_capacity"] and p.changes[1].count == 5
    assert "frontline" in p.protected_groups
    assert "admin" not in [t for c in rule_parse("Reduce frontline over three years").changes for t in c.target]
    assert rule_parse("Increase demand by 150%").changes[0].amount == 1.5
    assert abs(rule_parse("reduce admin by 1/3").changes[0].amount - 1 / 3) < 1e-3


def test_merge_by_name_and_counts():
    w = World("prototype", 7, "x"); w.run(2)
    schedule_plan(w, rule_parse("Merge comms and fundraising")); w.run(4)
    assert len([t for t in w.teams.values() if t.member_ids and w.active_members(t)]) == 7
    w = World("prototype", 7, "x"); w.run(2)
    assert describe_plan(w, rule_parse("Cut 5 posts from HR"))[0].startswith("Remove 5 posts")


def test_why_chain_reaches_intervention():
    _, i = _pair(seed=42, months=24)
    ev = next(e for e in reversed(i.events) if e.significant and e.id in analysis.causal_orders(i.events, i.intervention_root) and e.kind != "intervention")
    res = analysis.why(i.events, ev.id)
    assert res["reaches_intervention"] and res["chain"][0]["kind"] == "intervention" and res["chain"][-1]["id"] == ev.id


def test_org_rows_not_emergent_or_third_order():
    b, i = _pair(seed=42, months=24)
    rep = analysis.classify_effects(i, b, 0.5)
    for e in rep["effects"]:
        if e["team"] is None:
            assert e["order_label"] == "organisation" and e["emergent"] is None


# ----------------------------------------------------------------------------- follow-up modelling fixes

def test_baseline_management_is_not_overloaded():
    w = World("prototype", 7, "b", record_frames=False); w.run(39)
    h = w.metrics_history[6:]
    for tid in w.teams:
        assert sum(x["teams"][tid]["management_load"] for x in h) / len(h) < 1.0, tid
        assert sum(x["teams"][tid]["approvals_waiting"] for x in h) / len(h) < 5, tid


def test_cutting_officers_frees_approval_time():
    w = World("prototype", 7, "b", record_frames=False); w.run(3)
    before = w.teams["finance"].management_capacity_hours
    schedule_plan(w, rule_parse("Reduce finance by 30%")); w.run(4)
    assert w.teams["finance"].management_capacity_hours >= before * 0.95


def test_blocked_backfill_reopens_after_freeze():
    w = World("prototype", 7, "b", record_frames=False); w.run(3)
    t = w.teams["operations"]
    t.hiring_frozen = True
    leaver = next(e for e in w.active_members(t) if e.id != t.manager_id)
    w._employee_leaves(leaver)
    assert t.blocked_backfills
    t.hiring_frozen = False
    w.step()
    assert not t.blocked_backfills
    assert any(v.reason == "backfill" for v in t.vacancies) or any(e.kind == "employee_hired" and t.id in e.entities for e in w.events[-80:])


def test_phased_supervisory_conversion_reaches_target():
    b, i = _pair("Convert half of the administrative and finance roles into supervisors of AI agent teams, with agents handling 80% of routine work.", months=14)
    for tid in ("finance", "bizsupport"):
        prog = i._conversion_progress[tid]
        assert abs(prog["done"] - round(prog["orig"] * 0.5)) <= 1


def test_supervision_slips_under_pressure():
    _, i = _pair("Deploy AI agents to take 70% of routine finance and administrative work over 6 months and do not replace leavers, "
                 "and cut admin by 25%", seed=42, months=36)
    cov = [min((x["teams"][t]["ai_supervision_coverage"] for t in x["teams"] if x["teams"][t]["ai_agents"] > 0), default=1.0)
           for x in i.metrics_history]
    assert sum(1 for c in cov if c < 0.9) >= 3


def test_every_scenario_chip_changes_something():
    """Each shipped scenario must diverge from the baseline — the AI-automation chip once did nothing at all, silently,
    because teams were never enabled for automation."""
    from windtunnel.service import SCENARIOS
    for sc in SCENARIOS:
        p = rule_parse(sc["text"])
        ops = [c.operation for c in p.changes]
        assert len(ops) == len(set(ops)) or sc["id"] == "ai_supervisors", (sc["name"], ops)
        b = World("prototype", 7, "b", record_frames=False); b.run(3)
        i = b.fork("i"); schedule_plan(i, p)
        for _ in range(18):
            b.step(); i.step()
        assert len(analysis.classify_effects(i, b, 0.5)["effects"]) >= 3, sc["name"]


def test_automation_programme_reaches_its_target_teams():
    b = World("prototype", 7, "b", record_frames=False); b.run(3)
    i = b.fork("i"); schedule_plan(i, rule_parse("Automate 40% of routine finance and operations work over 18 months."))
    for _ in range(36):
        b.step(); i.step()
    assert i.teams["operations"].automation_level > 0.2 and i.teams["finance"].automation_level > 0
    assert i.metrics_history[-1]["teams"]["operations"]["workload"] < 0.9 * b.metrics_history[-1]["teams"]["operations"]["workload"]
