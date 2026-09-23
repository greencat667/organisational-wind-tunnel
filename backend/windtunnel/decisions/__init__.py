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
        raise ValueError("the Needle engine was removed in Sept 2026 (slow, unstable on long runs, no added value over "
                         "rules or Laya — see docs/VALIDATION.md); use 'heuristic' or 'laya'")
    if name == "recorded":
        return RecordedDecisionEngine(**kwargs)
    raise ValueError(f"unknown decision engine {name!r}")
