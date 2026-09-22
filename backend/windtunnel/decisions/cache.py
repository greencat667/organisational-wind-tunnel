"""Decision cache: reuses model output when archetype + bucketed state + available actions match.

The key deliberately discards identity (agent id, names) and fine-grained numbers so that
similar employees in similar situations share one inference. Cache behaviour is visible in
developer diagnostics via ``stats()``.
"""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict

from .base import AgentDecision, AgentDecisionEngine, DecisionRequest

# Archetype-level buckets (section 59 of the brief): similar people in similar situations share one inference.
_BUCKET_KEYS = {"workload": 0.25, "stress": 0.25, "morale": 0.25, "team_workload": 0.25, "team_backlog_months": 0.5,
                "manager_availability": 0.35, "turnover_intention": 0.2, "trust_management": 0.35, "commitment": 0.35,
                "collaboration_tendency": 0.35, "escalation_tendency": 0.35, "risk_tolerance": 0.35, "autonomy": 0.35, "adaptability": 0.35,
                "neighbour_spare_capacity": 0.3, "team_stress": 0.25, "team_morale": 0.25, "member_workload_spread": 0.5, "transfers_in_recent": 0.5,
                "frontline_share_waiting": 0.5, "urgent_tasks": 5, "overdue_tasks": 5, "approvals_waiting": 10, "team_vacancies": 2}
# free-text, identity-bearing or over-specific fields never enter the key
_EXCLUDE = {"name", "id", "relationships", "recent_events", "recent_changes", "neighbours_with_spare_capacity", "team", "team_headcount", "role",
            "my_tasks", "tenure_months", "job_market", "manager_availability_label", "team_backlog"}


def _bucket(v, step):
    try:
        return round(float(v) / step) * step
    except (TypeError, ValueError):
        return v


def cache_key(req: DecisionRequest) -> str:
    st = {k: (_bucket(v, _BUCKET_KEYS[k]) if k in _BUCKET_KEYS else v) for k, v in req.agent_state.items() if k not in _EXCLUDE}
    ctx = {k: (_bucket(v, _BUCKET_KEYS[k]) if k in _BUCKET_KEYS else v) for k, v in req.local_context.items() if k not in _EXCLUDE}
    payload = json.dumps({"k": req.agent_kind, "s": st, "c": ctx, "a": sorted(req.available_actions),
                          "t": sorted(req.triggers)}, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()


class CachedDecisionEngine(AgentDecisionEngine):
    def __init__(self, inner: AgentDecisionEngine, max_size: int = 5000):
        self.inner = inner
        self.name = inner.name
        self.max_size = max_size
        self._cache: OrderedDict[str, AgentDecision] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def decide(self, request: DecisionRequest) -> AgentDecision:
        key = cache_key(request)
        hit = self._cache.get(key)
        if hit is not None:
            self.hits += 1
            self._cache.move_to_end(key)
            d = AgentDecision(**{**hit.__dict__})
            d.cached = True
            d.latency_ms = 0.0
            # targets are team ids and aren't part of the key, so a cached target may belong to someone else's
            # situation (an Operations agent told to seek help from Operations): keep it only if it's valid here
            if d.target is not None and d.target not in request.action_targets.get(d.action, []):
                d.target = (request.action_targets.get(d.action) or [None])[0]
            return d
        self.misses += 1
        d = self.inner.decide(request)
        self._cache[key] = d
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)
        return d

    def describe(self):
        return {**self.inner.describe(), "cache": True}

    def stats(self):
        total = self.hits + self.misses
        return {**self.inner.stats(), "cache_hits": self.hits, "cache_misses": self.misses,
                "cache_hit_rate": (self.hits / total) if total else 0.0, "cache_size": len(self._cache)}

    def close(self):
        self.inner.close()
