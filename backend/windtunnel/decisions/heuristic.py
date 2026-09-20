"""Rule-based decision engine.

Produces a probability distribution over the available actions from the agent's state and
traits. Deterministic given the request (sampling happens in the simulation core). This is
also the fallback used when AI engines are unavailable or return low confidence.
"""
from __future__ import annotations

import math

from .base import AgentDecision, AgentDecisionEngine, DecisionRequest


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class HeuristicDecisionEngine(AgentDecisionEngine):
    name = "heuristic"

    def decide(self, request: DecisionRequest) -> AgentDecision:
        s = request.agent_state
        c = request.local_context
        w = float(s.get("workload", 1.0))
        stress = float(s.get("stress", 0.3))
        morale = float(s.get("morale", 0.6))
        trust = float(s.get("trust_management", 0.6))
        collab = float(s.get("collaboration_tendency", 0.5))
        esc = float(s.get("escalation_tendency", 0.5))
        risk = float(s.get("risk_tolerance", 0.5))
        auton = float(s.get("autonomy", 0.5))
        turnover = float(s.get("turnover_intention", 0.05))
        team_w = float(c.get("team_workload", 1.0))
        backlog_m = float(c.get("team_backlog_months", 0.5))
        mgr_avail = float(c.get("manager_availability", 0.7))
        neighbour_spare = float(c.get("neighbour_spare_capacity", 0.0))
        overload = max(0.0, w - 1.0)
        team_over = max(0.0, team_w - 1.0)
        pressure = max(overload, team_over, max(0.0, backlog_m - 0.8), 0.5 * float(c.get("overdue_tasks", 0) > 0))
        slack = 1.0 if pressure <= 0.0 else 0.0

        logits: dict[str, float] = {}
        for a in request.available_actions:
            if a == "continue_as_normal":
                logits[a] = 1.2 + 2.0 * slack - 3.0 * pressure
            elif a == "seek_help":
                logits[a] = -2.0 + 4.0 * pressure + 1.5 * (collab - 0.5) + 1.5 * neighbour_spare - 0.5 * (auton - 0.5)
            elif a == "work_overtime":
                logits[a] = -2.0 + 4.0 * pressure + 1.0 * (float(s.get("commitment", 0.6)) - 0.5) - 2.0 * max(0.0, stress - 0.6)
            elif a == "delay_low_priority":
                logits[a] = -1.8 + 3.5 * pressure + 0.8 * (auton - 0.5)
            elif a == "escalate_workload":
                logits[a] = -2.4 + 3.5 * pressure + 2.0 * (esc - 0.5) + 1.0 * (mgr_avail - 0.5) + 0.8 * (trust - 0.5)
            elif a == "use_workaround":
                logits[a] = -3.0 + 3.0 * pressure + 2.5 * (risk - 0.5) + 1.0 * (auton - 0.5) - 1.5 * mgr_avail
            elif a == "reduce_quality":
                logits[a] = -3.2 + 3.0 * pressure + 1.5 * max(0.0, stress - 0.5) - 1.5 * (morale - 0.5)
            elif a == "share_information":
                logits[a] = -1.0 + 1.5 * collab + 0.5 * float(c.get("holds_unshared_information", 0.0))
            elif a == "apply_for_internal_job":
                logits[a] = -2.5 + 3.0 * turnover + 1.0 * float(s.get("adaptability", 0.5))
            elif a == "leave":
                logits[a] = -4.0 + 6.0 * turnover + 1.5 * float(c.get("job_market", 0.5)) - 1.5 * float(s.get("commitment", 0.6))
            # manager actions
            elif a == "redistribute_work":
                logits[a] = -1.5 + 3.5 * pressure + 1.0 * float(c.get("member_workload_spread", 0.0))
            elif a == "request_recruitment":
                logits[a] = -2.5 + 3.0 * pressure + 1.0 * float(c.get("vacancy_budget_available", 0.0)) - 1.0 * float(c.get("hiring_frozen", 0.0)) + 1.0 * float(c.get("team_vacancies", 0) == 0)
            elif a == "approve_overtime":
                logits[a] = -2.2 + 3.5 * pressure - 1.0 * float(c.get("team_stress", 0.3))
            elif a == "protect_team":
                logits[a] = -2.5 + 2.5 * pressure + 2.0 * float(c.get("transfers_in_recent", 0.0)) - 1.0 * (collab - 0.5)
            elif a == "cancel_low_priority":
                logits[a] = -3.0 + 3.0 * pressure + 1.0 * (auton - 0.5) + 1.0 * (risk - 0.5)
            elif a == "escalate_up":
                logits[a] = -2.5 + 3.0 * pressure + 1.5 * (esc - 0.5)
            elif a == "reprioritise":
                logits[a] = -1.8 + 2.5 * pressure + 0.8 * float(c.get("frontline_share_waiting", 0.0))
            elif a == "verify_ai_output":
                logits[a] = -1.6 + 2.5 * float(c.get("ai_exception_rate", 0.0)) + 3.0 * float(c.get("ai_incident_this_month", 0.0)) + 1.0 * (1.0 - float(c.get("ai_supervision_coverage", 1.0))) - 1.5 * risk - 1.0 * pressure
            elif a == "pause_ai_agents":
                logits[a] = -2.5 + 3.5 * float(c.get("ai_incident_this_month", 0.0)) + 4.0 * max(0.0, float(c.get("ai_exception_rate", 0.0)) - 0.25) - 1.0 * risk - 1.0 * pressure
            elif a == "expand_ai_agents":
                logits[a] = -2.0 + 3.0 * pressure + 1.0 * (risk - 0.5) - 3.0 * float(c.get("ai_exception_rate", 0.0))
            elif a == "retrain_staff":
                logits[a] = -2.0 + 4.0 * (1.0 - float(c.get("ai_supervision_coverage", 1.0))) + 1.0 * float(c.get("ai_exception_rate", 0.0))
            elif a == "automate_task":
                logits[a] = -1.5 + 2.0 * float(c.get("automation_programme", 0.0)) + 1.0 * pressure + 0.5 * (risk - 0.5)
            else:
                logits[a] = -1.0
        # temperature to keep behaviour varied but not random
        m = max(logits.values())
        exps = {k: math.exp((v - m) / 0.9) for k, v in logits.items()}
        z = sum(exps.values())
        probs = {k: v / z for k, v in exps.items()}
        top = max(probs, key=probs.get)
        ranked = sorted(probs.values(), reverse=True)
        confidence = ranked[0] - (ranked[1] if len(ranked) > 1 else 0.0)
        scores = {"effort": max(0.6, min(1.15, 1.0 + 0.1 * (morale - 0.5) - 0.2 * max(0.0, stress - 0.7))),
                  "turnover_pressure": min(1.0, turnover)}
        return AgentDecision(action=top, probabilities=probs, confidence=round(0.5 + confidence / 2, 3),
                             engine=self.name, scores=scores, raw={"logits": logits})
