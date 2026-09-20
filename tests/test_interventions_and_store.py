import os, tempfile
from windtunnel.interventions.parser import rule_parse
from windtunnel.interventions.schema import validate_plan, unflatten
from windtunnel.store import Store
from windtunnel.engine import World


def test_rule_parser_scenarios():
    p = rule_parse("Reduce administrative capacity by 20% while protecting frontline delivery.")
    assert p.changes[0].operation == "reduce_capacity" and abs(p.changes[0].amount - 0.2) < 1e-6 and "frontline" in p.protected_groups
    assert rule_parse("Automate 40% of routine finance and operations work over 18 months.").changes[0].operation == "enable_automation"
    assert rule_parse("Remove one management layer and increase team autonomy.").changes[0].operation == "remove_management_layer"
    p = rule_parse("Organisation income falls 15% next year."); assert p.changes[0].operation == "shock" and p.changes[0].kind == "funding_cut"
    p = rule_parse("Demand for services doubles over two years."); assert p.changes[0].operation == "change_demand" and p.changes[0].amount == 1.0 and p.transition_period_months == 24
    p = rule_parse("Merge the fundraising and communications teams."); assert p.changes[0].operation == "merge_teams" and len(p.changes[0].teams) == 2
    p = rule_parse("Deploy AI agents for 60% of back-office work with staff supervising agent teams."); assert p.changes[0].operation == "convert_to_supervisory"


def test_flat_afm_output_validates():
    raw = {"intervention_type": "restructure", "summary": "x", "operation_1": "reduce_capacity", "target_1": "admin", "amount_percent_1": 20, "detail_1": "",
           "operation_2": "none", "target_2": "", "amount_percent_2": 0, "detail_2": "", "protected_groups": "frontline, programmes", "transition_period_months": 6}
    p = validate_plan(raw)
    assert p.changes[0].amount == 0.2 and p.protected_groups == ["frontline", "programmes"] and p.transition_period_months == 6
    raw2 = dict(raw, operation_1="merge_teams", detail_1="Fundraising and Communications")
    assert validate_plan(raw2).changes[0].teams == ["Fundraising", "Communications"]


def test_invalid_plan_rejected():
    import pytest
    with pytest.raises(Exception):
        validate_plan({"intervention_type": "restructure", "changes": []})
    with pytest.raises(Exception):
        validate_plan({"intervention_type": "restructure", "changes": [{"operation": "reduce_capacity", "amount": 250}]})


def test_store_save_load(tmp_path):
    s = Store(str(tmp_path / "t.sqlite"))
    w = World("prototype", 7, "baseline"); w.run(3)
    s.save_experiment({"id": "x1", "template": "prototype", "seed": 7, "engine": "heuristic", "plan": None, "months": 3})
    s.save_run(w, "x1", "x1-baseline", {"v": 1})
    assert s.load_run_metrics("x1-baseline")[-1]["month"] == 3
    assert s.list_runs("x1")[0]["id"] == "x1-baseline"
    assert len(s.load_run_events("x1-baseline")) == len(w.events)
