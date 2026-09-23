"""Choices that outlast the month: habits, norms, fatigue, hidden defects, workarounds, and their coupling to outcomes."""
import statistics as st

from windtunnel import behaviour
from windtunnel.decisions import HeuristicDecisionEngine
from windtunnel.decisions.base import AgentDecision, AgentDecisionEngine
from windtunnel.engine import World
from windtunnel.interventions.parser import rule_parse
from windtunnel.interventions.primitives import schedule_plan

ADMIN_CUT = "Reduce administrative capacity by 20% while maintaining existing frontline delivery."


class Policy(AgentDecisionEngine):
    def __init__(self, prefs):
        self.prefs = prefs
    name = "policy"

    def decide(self, req):
        a = next((p for p in self.prefs if p in req.available_actions), "continue_as_normal")
        return AgentDecision(action=a, probabilities={a: 1.0}, confidence=1.0, engine="policy")


def _cut(engine=None, seed=42, months=18):
    b = World("prototype", seed, "b", decision_engine=engine, record_frames=False); b.run(3)
    i = b.fork("i"); schedule_plan(i, rule_parse(ADMIN_CUT))
    for _ in range(months):
        i.step()
    return i


def test_workaround_actually_skips_the_approval():
    w = World("prototype", 7, "b", record_frames=False); w.run(3)
    item = next(x for x in w.work_items.values() if x.status == "queued" and w._next_stage_is_approval(x))
    item.workaround, item.workaround_cause = True, None
    w._move_item(item, item.stage_index + 1)
    assert item.workaround, "the flag must survive the move onto the approval stage it was meant for"
    w._move_item(item, item.stage_index + 1) if item.stage_index + 1 < len(w.processes[item.process_id].stages) else None
    assert not item.workaround, "…and not beyond it"


def test_corner_cutting_leaves_hidden_defects_traced_to_decisions():
    i = _cut(Policy(["reduce_quality"]), seed=42, months=18)
    surfaced = [e for e in i.events if e.kind in ("defect_surfaced", "complaint")]
    assert len(surfaced) > 10
    decision_ids = {e.id for e in i.events if e.kind == "decision"}
    assert sum(1 for e in surfaced if set(e.causes) & decision_ids) >= 0.8 * len(surfaced)


def test_habits_persist_and_fatigue_ends_them():
    w = World("prototype", 7, "b", record_frames=False); w.run(3)
    e = next(m for m in w.employees.values() if m.status == "active" and not m.is_manager)
    e.overtime_hours = 12.0
    behaviour.record_choice(w, e, "work_overtime", event_id=0)
    e.workload = 1.3
    e.capacity_hours, base = 100.0, 100.0
    behaviour.apply_habits(w)
    assert e.habit == "work_overtime" and e.capacity_hours == base + 12.0
    e.fatigue = w.config.habit_fatigue_limit + 0.01
    behaviour.apply_habits(w)
    assert e.habit is None


def test_norms_follow_what_influential_people_do():
    w = World("prototype", 7, "b", record_frames=False); w.run(3)
    t = w.teams["finance"]
    mgr = w.employees[t.manager_id]
    for m in w.active_members(t):
        m.current_behaviour = "working"
    mgr.current_behaviour = "reduce_quality"
    behaviour.update_norms(w)
    manager_led = t.norms["reduce_quality"]
    t.norms.clear()
    mgr.current_behaviour = "working"
    officer = next(m for m in w.active_members(t) if m.id != mgr.id)
    officer.current_behaviour = "reduce_quality"
    behaviour.update_norms(w)
    assert manager_led > t.norms["reduce_quality"] > 0


def test_how_agents_cope_changes_outcomes():
    """The coupling this module exists for: the same worlds under different coping policies must diverge."""
    rules = [_cut(HeuristicDecisionEngine(), seed=s, months=18) for s in (6, 42)]
    corners = [_cut(Policy(["reduce_quality", "use_workaround"]), seed=s, months=18) for s in (6, 42)]
    err = lambda ws: st.mean(sum(h["errors"] for h in w.metrics_history[-6:]) for w in ws)
    dfx = lambda ws: st.mean(sum(h["defects"] for h in w.metrics_history[-6:]) for w in ws)
    assert err(corners) > 1.5 * err(rules)
    assert dfx(corners) > 5 * max(1.0, dfx(rules))


def test_sustained_overtime_builds_fatigue_and_strain_drives_leaving():
    ot = _cut(Policy(["work_overtime", "approve_overtime"]), seed=42, months=18)
    assert st.mean(e.fatigue for e in ot.employees.values() if e.status == "active") > 0.05
    w = World("prototype", 7, "b", record_frames=False)
    cfg = w.config
    hz = lambda ti: cfg.baseline_exit_hazard * (1 + cfg.exit_intention_multiplier * ti)
    assert hz(0.6) > 4 * hz(0.03)      # someone at breaking point is several times likelier to leave than a calm colleague
