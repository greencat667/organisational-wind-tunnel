"""How much do agents' choices move outcomes? Runs the same worlds under deliberately extreme decision policies and
compares the spread across policies with the spread across seeds (above 1: how agents cope matters more than luck).

    .venv/bin/python scripts/coupling.py          # ~2 minutes; results are recorded in docs/VALIDATION.md
"""
import os, sys, statistics as st
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from windtunnel.engine import World
from windtunnel.decisions import HeuristicDecisionEngine
from windtunnel.decisions.base import AgentDecision, AgentDecisionEngine
from windtunnel.interventions.parser import rule_parse
from windtunnel.interventions.primitives import schedule_plan

class Policy(AgentDecisionEngine):
    """Always picks the first available action from a preference list (else continue)."""
    def __init__(self, name, prefs): self.name, self.prefs = name, prefs
    def decide(self, req):
        a = next((p for p in self.prefs if p in req.available_actions), "continue_as_normal")
        return AgentDecision(action=a, probabilities={a: 1.0}, confidence=1.0, engine=self.name)
    def describe(self): return {"name": self.name}
    def stats(self): return {}

POLICIES = {
    "rules": HeuristicDecisionEngine(),
    "passive": Policy("passive", []),
    "cut_corners": Policy("cut_corners", ["reduce_quality", "use_workaround", "delay_low_priority", "cancel_low_priority"]),
    "cooperative": Policy("cooperative", ["seek_help", "redistribute_work", "escalate_workload", "share_information", "request_recruitment"]),
    "self_sacrifice": Policy("self_sacrifice", ["work_overtime", "approve_overtime", "protect_team"]),
}
TEXT = "Reduce administrative capacity by 20% while maintaining existing frontline delivery."
KEYS = ["delivery", "backlog_months", "stress", "turnover_12m", "errors", "dropped", "cost_ytd", "defects", "fatigue"]
SEEDS = [6, 7, 11, 23, 42]
MONTHS = 24

def run(policy, seed):
    b = World("prototype", seed, "b", decision_engine=POLICIES[policy], record_frames=False); b.run(3)
    i = b.fork("i"); schedule_plan(i, rule_parse(TEXT))
    for _ in range(MONTHS): b.step(); i.step()
    avg = lambda w, k: st.mean(h[k] for h in w.metrics_history[-6:])
    return {k: (avg(b, k), avg(i, k)) for k in KEYS}

if __name__ == "__main__":
  res = {p: {s: run(p, s) for s in SEEDS} for p in POLICIES}
  print(f"{'metric':15} " + " ".join(f"{p:>14}" for p in POLICIES) + "   policy/seed spread")
  for k in KEYS:
      # outcome = intervention level (last 6 months), mean over seeds, per policy
      per_policy = {p: st.mean(res[p][s][k][1] for s in SEEDS) for p in POLICIES}
      seed_sd = st.mean(st.pstdev([res[p][s][k][1] for s in SEEDS]) for p in POLICIES)
      pol_sd = st.pstdev(list(per_policy.values()))
      print(f"{k:15} " + " ".join(f"{per_policy[p]:14.3f}" for p in POLICIES) + f"   {pol_sd / max(1e-9, seed_sd):.2f}")
  print("effect of the intervention (int - base), mean over seeds:")
  for k in KEYS:
      print(f"{k:15} " + " ".join(f"{st.mean(res[p][s][k][1] - res[p][s][k][0] for s in SEEDS):14.3f}" for p in POLICIES))
