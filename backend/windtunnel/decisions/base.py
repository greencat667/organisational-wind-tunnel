"""Decision engine abstraction.

Every engine receives the same compact request and returns the same decision shape, so the
simulation core never knows which model (or rule set) produced a decision. Engines return
*probabilities over the available actions* plus a confidence; the simulation core does the
sampling with its own seeded RNG so runs stay reproducible.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DecisionRequest:
    agent_id: str
    agent_kind: str                    # employee | manager
    agent_state: dict[str, Any]        # compact personal state (numbers/labels only)
    local_context: dict[str, Any]      # compact team/manager/relationship/work/recent-events context
    available_actions: list[str]       # bounded action ids the engine may choose from
    action_targets: dict[str, list[str]] = field(default_factory=dict)  # e.g. seek_help -> candidate team ids
    triggers: list[str] = field(default_factory=list)
    month: int = 0

    def state_text(self) -> str:
        """Compact newline-separated text rendering (used verbatim as model input)."""
        lines = []
        for k, v in self.agent_state.items():
            lines.append(f"{k.upper()} {_fmt(v)}")
        for k, v in self.local_context.items():
            lines.append(f"{k.upper()} {_fmt(v)}")
        if self.triggers:
            lines.append("TRIGGERS " + ", ".join(self.triggers))
        return "\n".join(lines)


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.2f}"
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v) or "none"
    if isinstance(v, dict):
        return "; ".join(f"{k}={_fmt(x)}" for k, x in v.items()) or "none"
    return str(v)


@dataclass
class AgentDecision:
    action: str                                # chosen action id (may be revised by confidence routing)
    probabilities: dict[str, float]            # engine's distribution over available actions
    confidence: float                          # 0..1
    engine: str
    latency_ms: float = 0.0
    target: Optional[str] = None               # e.g. team id for seek_help
    scores: dict[str, float] = field(default_factory=dict)   # auxiliary scalar outputs (effort, turnover pressure)
    raw: dict[str, Any] = field(default_factory=dict)        # model output for the replay inspector
    route: str = "execute"                     # execute | probabilistic | conservative (set by router)
    cached: bool = False
    fallback: bool = False                     # engine failed and heuristics were used


class AgentDecisionEngine:
    """Base class. Implement ``decide``; ``adecide`` is an async wrapper for server use."""

    name = "base"

    def decide(self, request: DecisionRequest) -> AgentDecision:  # pragma: no cover - abstract
        raise NotImplementedError

    async def adecide(self, request: DecisionRequest) -> AgentDecision:
        return await asyncio.to_thread(self.decide, request)

    def describe(self) -> dict[str, Any]:
        return {"name": self.name}

    def stats(self) -> dict[str, Any]:
        return {}

    def close(self) -> None:
        pass
