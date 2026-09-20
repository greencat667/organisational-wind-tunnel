"""Analysis: causal tracing, effect orders, baseline divergence, emergence, surprises, graph metrics, clustering."""
from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Any, Optional

from .model import Event, to_dict

# team-level metrics we compare between worlds
TEAM_METRICS = ["backlog_months", "queue", "workload", "headcount", "vacancies", "management_load", "morale", "stress",
                "turnover_12m", "errors", "transfers_in", "approvals_waiting", "completed", "dropped",
                "ai_exceptions", "downstream_ai_errors", "supervisors"]
ORG_METRICS = ["backlog_months", "queue_items", "delivery", "cycle_time", "overdue", "workload", "stress", "morale",
               "turnover_12m", "cost_ytd", "management_load", "approvals_waiting", "cooperation", "information_reach",
               "informal_ties", "errors", "headcount", "vacancies", "dropped", "ai_capacity_share", "downstream_ai_errors",
               "deskilling_index", "supervisors"]


# ----------------------------------------------------------------------------- causal graph

def causal_orders(events: list[Event], root_id: Optional[int]) -> dict[int, int]:
    """BFS from the intervention root along cause->effect edges; order = shortest causal distance."""
    if root_id is None:
        return {}
    children: dict[int, list[int]] = defaultdict(list)
    for ev in events:
        for c in ev.causes:
            children[c].append(ev.id)
    order = {root_id: 0}
    dq = deque([root_id])
    while dq:
        cur = dq.popleft()
        for ch in children.get(cur, []):
            if ch not in order:
                order[ch] = order[cur] + 1
                dq.append(ch)
    return order


def why(events: list[Event], event_id: int, max_depth: int = 8, max_nodes: int = 40) -> dict[str, Any]:
    """Reconstruct the causal chain behind an event: nodes + edges up to the intervention (or as far as recorded)."""
    by_id = {e.id: e for e in events}
    if event_id not in by_id:
        return {"nodes": [], "edges": [], "chain": []}
    nodes: dict[int, dict] = {}
    edges: list[tuple[int, int]] = []
    dq = deque([(event_id, 0)])
    while dq and len(nodes) < max_nodes:
        eid, d = dq.popleft()
        if eid in nodes:
            continue
        ev = by_id.get(eid)
        if not ev:
            continue
        nodes[eid] = {**to_dict(ev), "depth": d}
        if d >= max_depth:
            continue
        for c in ev.causes[:4]:
            if c in by_id:
                edges.append((c, eid))
                dq.append((c, d + 1))
    # a single spine: at each step follow the cause closest to the intervention root (if any), else the most significant recent cause
    root = next((e.id for e in events if e.kind == "intervention"), None)
    orders = causal_orders(events, root) if root is not None else {}
    chain = []
    cur = by_id[event_id]
    seen = set()
    while cur and cur.id not in seen and len(chain) < max_depth * 4:
        seen.add(cur.id)
        chain.append({"id": cur.id, "month": cur.month, "kind": cur.kind, "description": cur.description, "emergent": cur.emergent})
        cands = [by_id[c] for c in cur.causes if c in by_id]
        # an action event's decision is folded into it: jump to what caused the decision (the state the person saw)
        if cur.kind != "decision":
            decisions = [c for c in cands if c.kind == "decision"]
            for d in decisions:
                seen.add(d.id)
                cands += [by_id[c] for c in d.causes if c in by_id and c not in seen]
            cands = [c for c in cands if c.kind != "decision"] or decisions
        if not cands:
            break
        cands.sort(key=lambda e: (orders.get(e.id, 10**6), e.kind == "decision", not e.significant, -e.month))
        cur = cands[0]
    # keep the story readable: drop consecutive same-kind routine events (e.g. repeated redistributions), keep ends
    compact = []
    for c in chain:
        if compact and c["kind"] == compact[-1]["kind"] and c["kind"] in ("decision", "work_redistributed", "workaround", "escalation", "employee_overloaded", "work_transferred"):
            continue
        compact.append(c)
    if len(compact) > max_depth:
        compact = compact[: max_depth - 3] + compact[-3:]
    chain = compact
    chain.reverse()
    return {"nodes": list(nodes.values()), "edges": edges, "chain": chain}


# ----------------------------------------------------------------------------- divergence

def _series(history: list[dict], key: str, team: Optional[str] = None) -> list[float]:
    out = []
    for h in history:
        v = h["teams"].get(team, {}).get(key) if team else h.get(key)
        out.append(float(v) if v is not None else 0.0)
    return out


def divergence(base_hist: list[dict], int_hist: list[dict], intervention_month: int, min_effect: float = 0.25) -> list[dict[str, Any]]:
    """Variables that changed materially between baseline and intervention (same months, same seed).

    Effect size = mean absolute difference after the intervention / (baseline sd + small floor), using the last
    12 months for the 'final' comparison. Returns a ranked list."""
    n = min(len(base_hist), len(int_hist))
    if n <= intervention_month + 1:
        return []
    out = []
    keys = [(k, None) for k in ORG_METRICS] + [(k, t) for t in base_hist[-1]["teams"] for k in TEAM_METRICS]
    for key, team in keys:
        b = _series(base_hist[:n], key, team)
        x = _series(int_hist[:n], key, team)
        pre = b[: intervention_month + 1]
        sd = _sd(pre) if len(pre) > 2 else 0.0
        floor = 1.0 if key in _COUNT_METRICS else (0.05 if key in _RATIO_METRICS else max(0.1 * abs(_mean(pre)), 1e-3))
        scale = max(sd, floor, 0.1 * abs(_mean(pre)))
        post_b = b[intervention_month + 1:]
        post_x = x[intervention_month + 1:]
        diffs = [xi - bi for bi, xi in zip(post_b, post_x)]
        if not diffs:
            continue
        tail = diffs[-12:]
        effect = _mean(tail) / scale
        rel = (_mean(post_x[-12:]) - _mean(post_b[-12:])) / max(abs(_mean(post_b[-12:])), floor)
        if abs(effect) < min_effect and abs(rel) < 0.1:
            continue
        # onset: first month where |diff| exceeds scale for 3 consecutive months
        onset = None
        for i in range(len(diffs) - 2):
            if all(abs(diffs[j]) > scale for j in range(i, i + 3)):
                onset = intervention_month + 1 + i
                break
        effect = max(-20.0, min(20.0, effect))   # capped: beyond this the size is not informative
        out.append({"metric": key, "team": team, "effect_size": round(effect, 2), "relative_change": round(rel, 3),
                    "baseline_final": round(_mean(post_b[-12:]), 3), "intervention_final": round(_mean(post_x[-12:]), 3),
                    "onset_month": onset, "lag_months": (onset - intervention_month) if onset is not None else None})
    # rank by relative change (floored so zero baselines do not dominate), effect size as tie-break
    out.sort(key=lambda d: (-min(abs(d["relative_change"]), 5.0), -abs(d["effect_size"])))
    return out


_COUNT_METRICS = {"turnover_12m", "vacancies", "headcount", "queue", "queue_items", "transfers_in", "approvals_waiting", "errors",
                  "completed", "dropped", "overdue", "cooperation", "informal_ties", "ai_exceptions", "downstream_ai_errors", "supervisors"}
_RATIO_METRICS = {"backlog_months", "delivery", "workload", "stress", "morale", "management_load", "information_reach", "cycle_time",
                  "ai_capacity_share", "deskilling_index"}


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _sd(xs):
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1)) if len(xs) > 1 else 0.0


# ----------------------------------------------------------------------------- effect ordering by graph distance

def org_distance(world, targets: set[str]) -> dict[str, int]:
    """Graph distance from the intervention's target teams over the process/reporting graph."""
    adj: dict[str, set[str]] = defaultdict(set)
    for p in world.processes.values():
        tids = [world.resolve_team(s.team_id) for s in p.stages]
        for a, b in zip(tids, tids[1:]):
            if a != b:
                adj[a].add(b); adj[b].add(a)
    for t in world.teams.values():
        if t.manager_id and t.manager_id in world.employees:
            mgr = world.employees[t.manager_id]
            up = world.employees.get(mgr.manager_id) if mgr.manager_id else None
            if up and up.team_id in world.teams and up.team_id != t.id:
                adj[t.id].add(up.team_id); adj[up.team_id].add(t.id)
    dist = {t: 0 for t in targets if t in world.teams}
    dq = deque(dist)
    while dq:
        cur = dq.popleft()
        for nb in adj.get(cur, []):
            if nb not in dist:
                dist[nb] = dist[cur] + 1
                dq.append(nb)
    return dist


def classify_effects(world_int, world_base, min_effect: float = 0.25) -> dict[str, Any]:
    """Second-order-effects report: divergences labelled by graph distance and by causal order."""
    im = world_int.intervention_month or 0
    div = divergence(world_base.metrics_history, world_int.metrics_history, im, min_effect)
    targets = {t for t in world_int.intervention_targets if t in world_int.teams}
    dist = org_distance(world_int, targets)
    orders = causal_orders(world_int.events, world_int.intervention_root)
    for d in div:
        team = d["team"]
        if team is None:
            gd = None
        else:
            gd = dist.get(team)
        d["graph_distance"] = gd
        d["direct_target"] = team in targets if team else False
        # link to the latest significant event about this team/metric for "why"
        ev = _latest_event_for(world_int, team, d["metric"])
        d["event_id"] = ev.id if ev else None
        d["causal_order"] = orders.get(ev.id) if ev else None
        d["order_label"] = _order_label(d)
        d["emergent"] = not d["direct_target"]
        d["team_name"] = world_int.teams[team].name if team in world_int.teams else ("organisation" if team is None else team)
    return {"effects": div, "targets": sorted(targets), "graph_distance": dist, "intervention_month": im}


def _order_label(d: dict) -> str:
    if d["direct_target"] and d["metric"] in ("headcount", "capacity_hours", "vacancies"):
        return "first"
    gd = d.get("graph_distance")
    co = d.get("causal_order")
    if d["direct_target"]:
        return "first" if (co is not None and co <= 2) else "second"
    if gd == 1 or (co is not None and co <= 4):
        return "second"
    return "third"


_METRIC_EVENT_KINDS = {
    "backlog_months": ["backlog_threshold", "backlog_recovered", "work_transferred", "work_redistributed", "capacity_reduced"],
    "queue": ["backlog_threshold", "work_transferred", "work_redistributed"],
    "management_load": ["management_overload", "escalation", "manager_changed"],
    "turnover_12m": ["employee_left", "resignation", "turnover_spike"],
    "headcount": ["employee_left", "employee_hired", "capacity_reduced", "vacancy_blocked"],
    "vacancies": ["vacancy_opened", "vacancy_blocked", "hiring_freeze"],
    "stress": ["backlog_threshold", "overtime", "employee_left"],
    "morale": ["employee_left", "backlog_threshold", "capacity_reduced"],
    "errors": ["rework", "quality_reduced", "workaround"],
    "transfers_in": ["work_transferred", "work_redistributed"],
    "approvals_waiting": ["management_overload", "workaround"],
    "dropped": ["work_dropped"],
    "cost_ytd": ["hiring_freeze", "capacity_reduced", "employee_hired", "post_not_replaced", "ai_agents_live"],
    "downstream_ai_errors": ["ai_quality_leak", "ai_correction", "ai_incident"],
    "ai_exceptions": ["ai_incident", "supervision_gap", "ai_agents_live"],
    "supervisors": ["roles_converted", "staff_retrained"],
    "deskilling_index": ["ai_agents_live", "roles_converted"],
    "workload": ["backlog_threshold", "capacity_reduced", "work_transferred"],
}


def _latest_event_for(world, team: Optional[str], metric: str) -> Optional[Event]:
    """The event to explain a metric divergence with: kinds are tried in priority order (threshold crossings first),
    latest occurrence of the first kind that exists."""
    kinds = _METRIC_EVENT_KINDS.get(metric, ["backlog_threshold", "employee_left", "work_transferred"])
    for kind in kinds:
        for ev in reversed(world.events):
            if ev.kind == kind and (team is None or team in ev.entities) and ev.id != world.intervention_root:
                return ev
    for ev in reversed(world.events):
        if ev.significant and (team is None or team in ev.entities):
            return ev
    return None


# ----------------------------------------------------------------------------- emergence detector

def detect_emergence(world_int, world_base) -> list[dict[str, Any]]:
    """Named systemic phenomena identified from state (not scripted). Each item carries a linked event for 'why'."""
    out = []
    hi = _trailing(world_int.metrics_history, 6)
    hb = _trailing(world_base.metrics_history, 6) if world_base.metrics_history else hi
    targets = {t for t in world_int.intervention_targets if t in world_int.teams}
    for tid, tm in hi["teams"].items():
        tb = hb["teams"].get(tid, tm)
        name = world_int.teams[tid].name if tid in world_int.teams else tid
        emergent = tid not in targets
        if tm["backlog_months"] > 1.0 and tm["backlog_months"] > 2 * max(0.1, tb["backlog_months"]):
            out.append({"kind": "new_bottleneck", "team": tid, "label": f"New bottleneck: {name}", "emergent": emergent,
                        "value": tm["backlog_months"], "baseline": tb["backlog_months"], "event_id": _eid(world_int, tid, "backlog_threshold")})
        if tm["transfers_in"] >= 3 and tm["transfers_in"] > 2 * max(1, tb["transfers_in"]):
            out.append({"kind": "workload_transfer", "team": tid, "label": f"Unexpected workload transfer into {name}", "emergent": emergent,
                        "value": tm["transfers_in"], "baseline": tb["transfers_in"], "event_id": _eid(world_int, tid, "work_transferred")})
        if tm["management_load"] > 1.2 and tb["management_load"] <= 1.0:
            out.append({"kind": "management_overload", "team": tid, "label": f"Management overload: {name}", "emergent": emergent,
                        "value": tm["management_load"], "baseline": tb["management_load"], "event_id": _eid(world_int, tid, "management_overload")})
        if tm["turnover_12m"] >= 3 and tm["turnover_12m"] >= tb["turnover_12m"] + 2:
            out.append({"kind": "turnover_cluster", "team": tid, "label": f"Turnover cluster: {name}", "emergent": emergent,
                        "value": tm["turnover_12m"], "baseline": tb["turnover_12m"], "event_id": _eid(world_int, tid, "employee_left")})
    # AI-specific systemic phenomena
    for tid, tm in hi["teams"].items():
        tb = hb["teams"].get(tid, tm)
        name = world_int.teams[tid].name if tid in world_int.teams else tid
        emergent = tid not in targets
        if tm.get("ai_items", 0) + tm.get("ai_exceptions", 0) >= 5 and tm.get("ai_exceptions", 0) / max(1, tm.get("ai_items", 0) + tm.get("ai_exceptions", 0)) > 0.25:
            out.append({"kind": "ai_exception_load", "team": tid, "label": f"AI exception load on staff: {name}", "emergent": emergent,
                        "value": tm["ai_exceptions"], "baseline": 0, "event_id": _eid(world_int, tid, "ai_incident") or _eid(world_int, tid, "ai_agents_live")})
        if tm.get("downstream_ai_errors", 0) >= 3 and tm.get("ai_agents", 0) == 0:
            out.append({"kind": "quality_leakage", "team": tid, "label": f"AI defects surfacing in {name} (no agents there)", "emergent": True,
                        "value": tm["downstream_ai_errors"], "baseline": 0, "event_id": _eid(world_int, tid, "ai_quality_leak")})
        if tm.get("approvals_waiting", 0) >= 10 and tm["approvals_waiting"] > 3 * max(1, tb.get("approvals_waiting", 0)) and hi.get("ai_agents", 0) > 0:
            out.append({"kind": "approval_bottleneck", "team": tid, "label": f"Human approvals became the constraint: {name}", "emergent": emergent,
                        "value": tm["approvals_waiting"], "baseline": tb.get("approvals_waiting", 0), "event_id": _eid(world_int, tid, "management_overload")})
        if tm.get("ai_supervision_coverage", 1.0) < 0.75 and tm.get("ai_agents", 0) > 0:
            out.append({"kind": "supervision_gap", "team": tid, "label": f"AI agents under-supervised in {name}", "emergent": emergent,
                        "value": tm["ai_supervision_coverage"], "baseline": 1.0, "event_id": _eid(world_int, tid, "ai_agents_live")})
    if hi.get("deskilling_index", 0) >= 0.06:
        out.append({"kind": "deskilling", "team": None, "label": "Deskilling: staff losing proficiency in work AI now does", "emergent": True,
                    "value": hi["deskilling_index"], "baseline": hb.get("deskilling_index", 0), "event_id": None})
    # process workarounds
    wk_i = sum(1 for e in world_int.events if e.kind == "workaround" and e.month > (world_int.intervention_month or 0))
    wk_b = sum(1 for e in world_base.events if e.kind == "workaround" and e.month > (world_int.intervention_month or 0))
    if wk_i >= 5 and wk_i > 1.5 * max(1, wk_b):
        out.append({"kind": "process_workaround", "team": None, "label": "Approval workarounds spreading", "emergent": True,
                    "value": wk_i, "baseline": wk_b, "event_id": _eid(world_int, None, "workaround")})
    # informal coordination network / hubs
    hubs_i = key_people(world_int)[:3]
    hubs_b = {h["id"] for h in key_people(world_base)[:5]}
    for h in hubs_i:
        if h["id"] not in hubs_b and h["bridging"] >= 2:
            out.append({"kind": "informal_hub", "team": h["team_id"], "label": f"{h['name']} became an informal coordination hub", "emergent": True,
                        "value": h["bridging"], "baseline": 0, "event_id": _eid(world_int, h["id"], "work_transferred")})
    if hi["information_reach"] < 0.5 * max(0.05, hb["information_reach"]) and hi["information_reach"] < 0.15:
        out.append({"kind": "information_silo", "team": None, "label": "Information reach collapsed (silo forming)", "emergent": True,
                    "value": hi["information_reach"], "baseline": hb["information_reach"], "event_id": None})
    return out


def _trailing(history: list[dict], n: int) -> dict:
    """Metrics averaged over the last n months (team metrics included); the latest snapshot for non-numeric fields."""
    tail = history[-n:]
    last = dict(history[-1])
    for k, v in history[-1].items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            last[k] = sum(h.get(k, 0) or 0 for h in tail) / len(tail)
    teams = {}
    for tid, tm in history[-1]["teams"].items():
        teams[tid] = dict(tm)
        for k, v in tm.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                teams[tid][k] = sum((h["teams"].get(tid, {}).get(k, 0) or 0) for h in tail) / len(tail)
    last["teams"] = teams
    return last


def _eid(world, entity: Optional[str], kind: str) -> Optional[int]:
    for ev in reversed(world.events):
        if ev.kind == kind and (entity is None or entity in ev.entities):
            return ev.id
    return None


# ----------------------------------------------------------------------------- informal network / key people

def key_people(world, top: int = 10) -> list[dict[str, Any]]:
    """Measured (not pre-labelled) informal importance: degree, cross-team bridging, help given, decision reach."""
    out = []
    for e in world.employees.values():
        if e.status != "active":
            continue
        ties = [(k, v) for k, v in e.relationships.items() if k in world.employees and world.employees[k].status == "active"]
        cross = [k for k, v in ties if world.employees[k].team_id != e.team_id and v >= 0.3]
        strength = sum(v for _, v in ties)
        score = strength + 1.5 * len(cross) + 0.5 * e.influence * 10
        out.append({"id": e.id, "name": e.name, "team_id": e.team_id, "team": world.teams[e.team_id].name if e.team_id in world.teams else e.team_id,
                    "degree": len(ties), "bridging": len(cross), "strength": round(strength, 2), "influence": round(e.influence, 2),
                    "is_manager": e.is_manager, "score": round(score, 2)})
    out.sort(key=lambda d: -d["score"])
    return out[:top]


def informal_network(world, min_weight: float = 0.3) -> dict[str, Any]:
    edges = []
    seen = set()
    for e in world.employees.values():
        if e.status != "active":
            continue
        for k, v in e.relationships.items():
            if v >= min_weight and k in world.employees and world.employees[k].status == "active":
                key = tuple(sorted((e.id, k)))
                if key in seen:
                    continue
                seen.add(key)
                edges.append({"a": key[0], "b": key[1], "w": round(v, 2), "cross_team": world.employees[k].team_id != e.team_id})
    # team-level aggregation
    team_edges: dict[tuple[str, str], float] = defaultdict(float)
    for ed in edges:
        ta, tb = world.employees[ed["a"]].team_id, world.employees[ed["b"]].team_id
        if ta != tb:
            team_edges[tuple(sorted((ta, tb)))] += ed["w"]
    return {"edges": edges, "team_edges": [{"a": a, "b": b, "w": round(w, 2)} for (a, b), w in team_edges.items()], "key_people": key_people(world)}


def formal_network(world) -> dict[str, Any]:
    reports = [{"a": e.id, "b": e.manager_id} for e in world.employees.values() if e.status == "active" and e.manager_id in world.employees]
    proc_edges: dict[tuple[str, str], float] = defaultdict(float)
    for p in world.processes.values():
        tids = [world.resolve_team(s.team_id) for s in p.stages]
        for a, b in zip(tids, tids[1:]):
            if a != b:
                proc_edges[(a, b)] += p.arrival_rate
    return {"reports_to": reports, "process_edges": [{"a": a, "b": b, "w": round(w, 1)} for (a, b), w in proc_edges.items()]}


# ----------------------------------------------------------------------------- batch: clustering & surprises

def final_vector(history: list[dict]) -> dict[str, float]:
    h = history[-1]
    tail = history[-12:]
    return {
        "backlog_months": _mean([x["backlog_months"] for x in tail]),
        "delivery": _mean([x["delivery"] for x in tail]),
        "turnover_12m": h["turnover_12m"],
        "stress": _mean([x["stress"] for x in tail]),
        "morale": _mean([x["morale"] for x in tail]),
        "management_load": _mean([x["management_load"] for x in tail]),
        "cost_ytd": h["cost_ytd"],
        "cooperation": _mean([x["cooperation"] for x in tail]),
        "max_team_backlog": max(t["backlog_months"] for t in h["teams"].values()),
        "errors": _mean([x["errors"] for x in tail]),
        "headcount": h["headcount"],
        "ai_capacity_share": _mean([x.get("ai_capacity_share", 0.0) for x in tail]),
        "ai_exception_share": _mean([x.get("ai_exceptions", 0) / max(1, x.get("ai_items", 0) + x.get("ai_exceptions", 0)) for x in tail]),
        "downstream_ai_errors": _mean([x.get("downstream_ai_errors", 0) for x in tail]),
        "deskilling_index": h.get("deskilling_index", 0.0),
        "approvals_waiting": _mean([x.get("approvals_waiting", 0) for x in tail]),
        "supervisors": h.get("supervisors", 0),
    }


def name_cluster(centre: dict[str, float], base_centre: dict[str, float]) -> str:
    """Descriptive (not evaluative) name from where the cluster centre sits relative to baseline."""
    tags = []
    if centre["max_team_backlog"] > 2.0:
        tags.append("Bottleneck")
    if centre["turnover_12m"] > base_centre["turnover_12m"] * 1.5 + 2:
        tags.append("High-turnover")
    if centre["management_load"] > 1.15:
        tags.append("Management-load")
    if centre["delivery"] < base_centre["delivery"] * 0.85:
        tags.append("Delivery-degradation")
    if centre["cooperation"] > base_centre["cooperation"] * 1.5 + 2:
        tags.append("Workload-transfer")
    if centre.get("ai_exception_share", 0) > 0.25:
        tags.append("AI-exception load")
    if centre.get("downstream_ai_errors", 0) > 3:
        tags.append("Quality-leakage")
    if centre.get("deskilling_index", 0) > 0.06:
        tags.append("Deskilling")
    if centre["cost_ytd"] < base_centre["cost_ytd"] * 0.95 and not tags:
        tags.append("Automation recovery" if centre.get("ai_capacity_share", 0) > 0.05 else "Cost-saving")
    if not tags:
        return "Stable adaptation"
    return " / ".join(tags[:2]) + (" spiral" if "High-turnover" in tags and "Bottleneck" in tags else "")


def kmeans(vectors: list[list[float]], k: int, iters: int = 30, seed: int = 1) -> list[int]:
    import random
    if not vectors:
        return []
    k = max(1, min(k, len(vectors)))
    rng = random.Random(seed)
    dims = len(vectors[0])
    # z-score
    means = [_mean([v[d] for v in vectors]) for d in range(dims)]
    sds = [(_sd([v[d] for v in vectors]) or 1.0) for d in range(dims)]
    Z = [[(v[d] - means[d]) / sds[d] for d in range(dims)] for v in vectors]
    centres = [Z[i][:] for i in rng.sample(range(len(Z)), k)]
    labels = [0] * len(Z)
    for _ in range(iters):
        for i, z in enumerate(Z):
            labels[i] = min(range(k), key=lambda c: sum((z[d] - centres[c][d]) ** 2 for d in range(dims)))
        for c in range(k):
            members = [Z[i] for i in range(len(Z)) if labels[i] == c]
            if members:
                centres[c] = [_mean([m[d] for m in members]) for d in range(dims)]
    return labels
