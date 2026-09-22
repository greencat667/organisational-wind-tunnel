"""Laya-backed decision engine.

Uses the official ``laya`` package (verified API, Sept 2026):
    agent = laya.load("convaiinnovations/laya", device=None)
    result = agent.predict(state_text, questions)
    questions: {qid: {"type": "noul"|"choice"|"score", "instructions": str, "criteria": ...}}
    answers[qid] -> noul: {"noul": P(true), "confidence"}; choice: {"choice", "probabilities", "confidence"};
                    score: {"score": expected level, "probabilities", "confidence"}

Design (informed by earlier Laya-based agent projects): one ``noul`` question per available action rather than a
single crowded ``choice`` — Laya's calibrated P(true) per action is far better behaved than a
many-way choice. Two ``score`` questions give effort and turnover pressure. Everything is a single
forward pass (~0.3-0.7 s on MPS for 6-10 questions). Import is lazy so the simulator runs without torch.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any

from ..actions import ALL_ACTIONS
from .base import AgentDecision, AgentDecisionEngine, DecisionRequest

_EFFORT_LEVELS = ["minimal", "reduced", "normal", "high", "maximum"]
_TURNOVER_LEVELS = ["none", "low", "moderate", "high", "very high"]


class LayaDecisionEngine(AgentDecisionEngine):
    name = "laya"

    def __init__(self, model_id: str = "convaiinnovations/laya", device: str | None = None, ask_scores: bool = True):
        import laya  # heavy: torch + transformers

        t0 = time.perf_counter()
        self._agent = laya.load(model_id, device=device)
        self.load_seconds = round(time.perf_counter() - t0, 1)
        self.device = str(getattr(self._agent, "device", device or "?"))
        self.model_id = model_id
        self.ask_scores = ask_scores
        self._lock = threading.Lock()   # one MPS device; serialise calls
        self.calls = 0
        self.total_ms = 0.0
        self.max_ms = 0.0
        self.neutral: dict[str, float] = {}
        self._calibrate()

    _NEUTRAL_STATE = "\n".join([
        "ROLE officer", "TEAM a team", "WORKLOAD 0.70", "STRESS 0.20", "MORALE 0.70", "TRUST_MANAGEMENT 0.65", "TURNOVER_INTENTION 0.05",
        "COMMITMENT 0.65", "COLLABORATION_TENDENCY 0.50", "ESCALATION_TENDENCY 0.50", "RISK_TOLERANCE 0.50", "AUTONOMY 0.50", "ADAPTABILITY 0.50",
        "TENURE_MONTHS 48", "ARCHETYPE steady", "TEAM_WORKLOAD 0.70", "TEAM_BACKLOG_MONTHS 0.30", "TEAM_BACKLOG low", "TEAM_HEADCOUNT 12 (was 12)",
        "TEAM_VACANCIES 0", "MANAGER_AVAILABILITY 0.70", "MANAGER_AVAILABILITY_LABEL moderate", "MY_TASKS 6", "URGENT_TASKS 1", "OVERDUE_TASKS 0",
        "NEIGHBOUR_SPARE_CAPACITY 0.10", "NEIGHBOURS_WITH_SPARE_CAPACITY none", "RECENT_CHANGES none", "JOB_MARKET 0.50", "HOLDS_UNSHARED_INFORMATION 0.00",
        "TRIGGERS periodic"])

    def _calibrate(self) -> None:
        """Ask every action question on a calm, ordinary state. That P(yes) becomes the zero point for the action, so
        Laya's known preference for concrete-sounding labels (see docs/LAYA.md) does not read as a decision."""
        qs = {a: {"type": "noul", "instructions": spec.question} for a, spec in ALL_ACTIONS.items() if a != "continue_as_normal"}
        with self._lock:
            res = self._agent.predict(self._NEUTRAL_STATE, qs)
        for a, ans in res.get("answers", {}).items():
            self.neutral[a] = float(ans.get("noul", 0.5))

    def _adjust(self, a: str, p: float) -> float:
        """Shift P(yes) so that the neutral state maps to 0.15 (a low but non-zero propensity), in logit space."""
        p = min(0.999, max(0.001, p))
        n = min(0.999, max(0.001, self.neutral.get(a, 0.5)))
        logit = math.log(p / (1 - p)) - math.log(n / (1 - n)) + math.log(0.15 / 0.85)
        return 1.0 / (1.0 + math.exp(-logit))

    def _questions(self, req: DecisionRequest) -> dict[str, dict[str, Any]]:
        qs: dict[str, dict[str, Any]] = {}
        for a in req.available_actions:
            if a == "continue_as_normal":
                continue
            spec = ALL_ACTIONS.get(a)
            if spec:
                qs[a] = {"type": "noul", "instructions": spec.question}
        if req.action_targets.get("seek_help") and "seek_help" in req.available_actions:
            names = req.action_targets["seek_help"][:5]
            qs["_help_target"] = {"type": "choice", "instructions": "If this employee asks another team for help, which team should it be?",
                                  "criteria": {t: f"the {t.replace('_', ' ')} team" for t in names}}
        if self.ask_scores:
            qs["_effort"] = {"type": "score", "instructions": "How much effort will this employee put in this month?", "criteria": _EFFORT_LEVELS}
            qs["_turnover"] = {"type": "score", "instructions": "How strong is this employee's pressure to leave the organisation?", "criteria": _TURNOVER_LEVELS}
        return qs

    def decide(self, req: DecisionRequest) -> AgentDecision:
        qs = self._questions(req)
        text = req.state_text()
        t0 = time.perf_counter()
        with self._lock:
            result = self._agent.predict(text, qs)
        ms = (time.perf_counter() - t0) * 1000.0
        self.calls += 1
        self.total_ms += ms
        self.max_ms = max(self.max_ms, ms)
        answers = result.get("answers", {})
        # P(action) from noul answers; "continue" gets the probability that no action is wanted
        p_yes: dict[str, float] = {}
        conf: dict[str, float] = {}
        for a in req.available_actions:
            if a == "continue_as_normal":
                continue
            ans = answers.get(a)
            if ans and ans.get("type") == "noul":
                raw_p = float(ans.get("noul", 0.0))
                p_yes[a] = self._adjust(a, raw_p)
                conf[a] = float(ans.get("confidence", 0.5))
        none_p = 1.0
        for v in p_yes.values():
            none_p *= (1.0 - v)
        weights = dict(p_yes)
        if "continue_as_normal" in req.available_actions:
            weights["continue_as_normal"] = max(0.05, none_p)
        z = sum(weights.values()) or 1.0
        probs = {k: v / z for k, v in weights.items()}
        top = max(probs, key=probs.get) if probs else "continue_as_normal"
        # confidence: Laya's calibrated confidence for the winning action's own question (or its complement for continue)
        if top == "continue_as_normal":
            confidence = min([conf[a] for a in conf] or [0.5])
            confidence = max(confidence, none_p)
        else:
            confidence = conf.get(top, 0.5)
        target = None
        ht = answers.get("_help_target")
        if ht and ht.get("choice") in (req.action_targets.get("seek_help") or []):
            target = ht["choice"]
        scores: dict[str, float] = {}
        if "_effort" in answers:
            lvl = float(answers["_effort"].get("score", 2.0))          # 0..4, 2 = normal
            scores["effort"] = round(0.7 + 0.1125 * lvl, 3)              # 0.7 .. 1.15
        if "_turnover" in answers:
            scores["turnover_pressure"] = round(float(answers["_turnover"].get("score", 0.0)) / 4.0, 3)
        return AgentDecision(action=top, probabilities={k: round(v, 4) for k, v in probs.items()}, confidence=round(confidence, 4),
                             engine=self.name, latency_ms=round(ms, 1), target=target, scores=scores,
                             raw={"answers": answers, "usage": result.get("usage"), "questions": list(qs), "neutral": {a: round(self.neutral.get(a, 0.5), 3) for a in p_yes},
                                  "adjusted": {a: round(v, 3) for a, v in p_yes.items()}})

    def describe(self):
        return {"name": self.name, "model_id": self.model_id, "device": self.device, "load_seconds": self.load_seconds,
                "neutral_calibration": {a: round(v, 3) for a, v in self.neutral.items()}}

    def stats(self):
        return {"calls": self.calls, "mean_ms": round(self.total_ms / self.calls, 1) if self.calls else 0.0, "max_ms": round(self.max_ms, 1)}
