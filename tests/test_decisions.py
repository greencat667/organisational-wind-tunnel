from windtunnel.decisions import make_engine, RecordedDecisionEngine, CachedDecisionEngine
from windtunnel.decisions.base import DecisionRequest
from windtunnel.decisions.cache import cache_key
from windtunnel.engine import World


def req(**over):
    st = {"workload": 1.3, "stress": 0.6, "morale": 0.5, "trust_management": 0.6, "turnover_intention": 0.1, "commitment": 0.6,
          "collaboration_tendency": 0.6, "escalation_tendency": 0.5, "risk_tolerance": 0.4, "autonomy": 0.5, "adaptability": 0.5}
    st.update(over)
    return DecisionRequest("E1", "employee", st, {"team_workload": 1.2, "team_backlog_months": 1.1, "manager_availability": 0.4, "neighbour_spare_capacity": 0.3},
                           ["continue_as_normal", "seek_help", "work_overtime", "delay_low_priority", "escalate_workload"], {"seek_help": ["finance"]}, ["overload"], 5)


def test_heuristic_probabilities_sum_and_respond_to_pressure():
    h = make_engine("heuristic")
    d = h.decide(req())
    assert abs(sum(d.probabilities.values()) - 1) < 1e-6
    calm_req = req(workload=0.7, stress=0.2)
    calm_req.local_context.update({"team_workload": 0.7, "team_backlog_months": 0.3})
    calm = h.decide(calm_req).probabilities["continue_as_normal"]
    assert calm > d.probabilities["continue_as_normal"]


def test_unknown_engine_raises_and_factory_heuristic():
    import pytest
    with pytest.raises(ValueError):
        make_engine("nope")
    assert make_engine("heuristic").name == "heuristic"


def test_recorded_engine_replays_then_falls_back():
    rec = RecordedDecisionEngine([{"month": 5, "agent_id": "E1", "action": "seek_help", "confidence": 0.9}])
    d = rec.decide(req())
    assert d.action == "seek_help" and not d.fallback
    d2 = rec.decide(DecisionRequest("E2", "employee", {}, {}, ["continue_as_normal"], {}, [], 5))
    assert d2.fallback


def test_cache_key_ignores_identity_and_buckets():
    a = cache_key(req(workload=1.0)); b = cache_key(req(workload=1.04)); c = cache_key(req(workload=1.9))
    assert a == b and a != c
    eng = CachedDecisionEngine(make_engine("heuristic"))
    eng.decide(req(workload=1.0)); eng.decide(req(workload=1.04))
    assert eng.stats()["cache_hits"] == 1


def test_confidence_routing_and_guards_in_world():
    w = World("prototype", 7, "t"); w.run(4)
    routes = {d["route"] for d in w.decision_log}
    assert routes <= {"execute", "probabilistic", "conservative"}
    for d in w.decision_log:
        assert d["action"] in d["available"]


def test_model_adapter_fallback_on_error():
    class Broken:
        name = "broken"
        def decide(self, r): raise RuntimeError("boom")
        def describe(self): return {}
        def stats(self): return {}
    w = World("prototype", 7, "t", decision_engine=Broken()); w.run(3)
    assert w.decision_log and all(d["fallback"] for d in w.decision_log)
