from .base import AgentDecision, AgentDecisionEngine, DecisionRequest
from .heuristic import HeuristicDecisionEngine
from .recorded import RecordedDecisionEngine
from .cache import CachedDecisionEngine

__all__ = ["AgentDecision", "AgentDecisionEngine", "DecisionRequest", "HeuristicDecisionEngine",
           "RecordedDecisionEngine", "CachedDecisionEngine", "make_engine"]


def make_engine(name: str, **kwargs) -> AgentDecisionEngine:
    """Factory. Unknown or unavailable engines fall back to heuristics (the simulator must always run)."""
    name = (name or "heuristic").lower()
    if name == "heuristic":
        return HeuristicDecisionEngine()
    if name == "laya":
        from .laya_engine import LayaDecisionEngine
        return LayaDecisionEngine(**kwargs)
    if name == "needle":
        from .needle_engine import NeedleDecisionEngine
        return NeedleDecisionEngine(**kwargs)
    if name == "recorded":
        return RecordedDecisionEngine(**kwargs)
    raise ValueError(f"unknown decision engine {name!r}")
