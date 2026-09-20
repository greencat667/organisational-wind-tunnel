"""Replays decisions recorded from a previous run (by month + agent id); falls back to heuristics."""
from __future__ import annotations

from .base import AgentDecision, AgentDecisionEngine, DecisionRequest
from .heuristic import HeuristicDecisionEngine


class RecordedDecisionEngine(AgentDecisionEngine):
    name = "recorded"

    def __init__(self, recording: list[dict] | None = None, source_engine: str = "recorded"):
        self._by_key: dict[tuple[int, str], dict] = {}
        for rec in recording or []:
            self._by_key[(int(rec["month"]), rec["agent_id"])] = rec
        self._fallback = HeuristicDecisionEngine()
        self.source_engine = source_engine
        self.hits = 0
        self.misses = 0

    def decide(self, request: DecisionRequest) -> AgentDecision:
        rec = self._by_key.get((request.month, request.agent_id))
        if rec and rec.get("action") in request.available_actions:
            self.hits += 1
            return AgentDecision(action=rec["action"], probabilities=rec.get("probabilities", {rec["action"]: 1.0}),
                                 confidence=float(rec.get("confidence", 1.0)), engine=f"recorded({self.source_engine})",
                                 target=rec.get("target"), scores=rec.get("scores", {}), raw={"recorded": True})
        self.misses += 1
        d = self._fallback.decide(request)
        d.fallback = True
        return d

    def stats(self):
        return {"hits": self.hits, "misses": self.misses}
