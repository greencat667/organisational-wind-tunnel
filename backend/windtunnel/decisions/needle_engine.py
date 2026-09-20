"""Cactus Needle 3 decision engine.

Uses the ``cactus-needle`` package (verified API, Sept 2026):
    tools = [needle.tool(fn), ...]            # zero-arg functions; docstring = tool description
    agent = needle.Needle(tools=tools, system=None, weights=None, auto_date=False)
    r = agent.complete(text, max_new_tokens=96)  -> {"function_calls": [{"name", "arguments"}], "confidence", ...}
    agent.reset()                              # every N calls (decode slows/stalls on long streaks, see project 058)

Design (informed by 058/063): at most FIVE tools per call (Needle's rendering threshold), so each
request's available actions are trimmed to the five most relevant plus "continue_as_normal"; one
Needle instance per tool-set, cached; a single global lock (never run two Needle decodes at once).
Needle returns one calibrated confidence for the call — the per-action distribution is synthetic.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from ..actions import ALL_ACTIONS
from .base import AgentDecision, AgentDecisionEngine, DecisionRequest

_LOCK = threading.Lock()
_PRIORITY = ["seek_help", "escalate_workload", "work_overtime", "delay_low_priority", "leave", "use_workaround", "reduce_quality",
             "apply_for_internal_job", "share_information",
             "redistribute_work", "request_recruitment", "approve_overtime", "protect_team", "cancel_low_priority", "escalate_up",
             "reprioritise", "automate_task"]


def _make_tool(action_id: str, doc: str):
    import needle

    def _t():
        return action_id
    _t.__name__ = action_id
    _t.__doc__ = doc
    return needle.tool(_t)


class NeedleDecisionEngine(AgentDecisionEngine):
    name = "needle"

    def __init__(self, weights: str | None = None, max_new_tokens: int = 96, reset_every: int = 12, max_tools: int = 5):
        import needle  # noqa: F401  (native ctypes library; auto-fetches weights on first use)

        self._needle = needle
        self.weights = weights
        self.max_new_tokens = max_new_tokens
        self.reset_every = reset_every
        self.max_tools = max_tools
        self._agents: dict[tuple[str, ...], Any] = {}
        self._calls_since_reset: dict[tuple[str, ...], int] = {}
        self.calls = 0
        self.total_ms = 0.0
        self.max_ms = 0.0
        self.invalid = 0

    def _select_tools(self, req: DecisionRequest) -> list[str]:
        acts = [a for a in req.available_actions if a != "continue_as_normal"]
        acts.sort(key=lambda a: _PRIORITY.index(a) if a in _PRIORITY else 99)
        # keep "leave" in view only when turnover pressure is real (avoid keyword bait)
        if "leave" in acts and float(req.agent_state.get("turnover_intention", 0)) < 0.3:
            acts.remove("leave")
        acts = acts[: self.max_tools - 1]
        return acts + ["continue_as_normal"]

    def _agent_for(self, tools: list[str]):
        key = tuple(tools)
        ag = self._agents.get(key)
        if ag is None:
            ag = self._needle.Needle(tools=[_make_tool(a, ALL_ACTIONS[a].tool_doc) for a in tools], system=None,
                                    weights=self.weights, auto_date=False)
            self._agents[key] = ag
            self._calls_since_reset[key] = 0
        return key, ag

    def decide(self, req: DecisionRequest) -> AgentDecision:
        tools = self._select_tools(req)
        text = req.state_text() + "\nDecide what this person does this month by calling exactly one tool."
        t0 = time.perf_counter()
        with _LOCK:
            key, ag = self._agent_for(tools)
            if self._calls_since_reset[key] >= self.reset_every:
                ag.reset()
                self._calls_since_reset[key] = 0
            self._calls_since_reset[key] += 1
            r = ag.complete(text, max_new_tokens=self.max_new_tokens)
        ms = (time.perf_counter() - t0) * 1000.0
        self.calls += 1
        self.total_ms += ms
        self.max_ms = max(self.max_ms, ms)
        calls = r.get("function_calls") or []
        choice = calls[0].get("name") if calls else None
        conf = r.get("confidence")
        confidence = float(conf) if isinstance(conf, (int, float)) else 0.5
        if choice not in tools:
            self.invalid += 1
            choice = "continue_as_normal"
        # synthetic distribution: confidence on the chosen tool, remainder spread (documented as synthetic)
        rest = (1.0 - confidence) / max(1, len(tools) - 1)
        probs = {a: (confidence if a == choice else rest) for a in tools}
        target = None
        if choice in req.action_targets and req.action_targets[choice]:
            target = req.action_targets[choice][0]
        return AgentDecision(action=choice, probabilities={k: round(v, 4) for k, v in probs.items()}, confidence=round(confidence, 4),
                             engine=self.name, latency_ms=round(ms, 1), target=target,
                             raw={"function_calls": calls, "reasoning": r.get("reasoning"), "tools": tools, "synthetic_probabilities": True,
                                  "suppressed": r.get("suppressed_calls")})

    def describe(self):
        return {"name": self.name, "weights": self.weights or "needle3-base", "max_tools": self.max_tools, "reset_every": self.reset_every}

    def stats(self):
        return {"calls": self.calls, "mean_ms": round(self.total_ms / self.calls, 1) if self.calls else 0.0, "max_ms": round(self.max_ms, 1),
                "invalid_tool_calls": self.invalid, "tool_sets": len(self._agents)}
