"""Monte Carlo batch runner: many seeds, no rendering, baseline + intervention per seed.

Runs in a multiprocessing pool with the heuristic engine by default (AI engines are single-device and
slow; they can be used for small N). Produces frequencies *within the model*, never real-world probabilities.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import sys
import time
from typing import Any, Callable, Optional

from . import analysis
from .config import SimConfig
from .engine import World
from .interventions.primitives import schedule_plan
from .interventions.schema import ChangePlan, validate_plan

# variation: each seed changes agent parameters, arrivals, absence, turnover, external events, decision sampling.


def _init_worker(backend_dir: str) -> None:
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)


def _run_one(args: tuple) -> dict[str, Any]:
    template, seed, plan_dict, months, settle, engine_name, config_dict, scale = args
    from .decisions import make_engine
    try:
        engine = make_engine(engine_name)
    except Exception:
        engine = make_engine("heuristic")
    cfg = SimConfig(**config_dict) if config_dict else SimConfig()
    base = World(template, seed, "baseline", decision_engine=engine, config=cfg, scale=scale, record_frames=False)
    base.run(settle)
    inter = base.fork("intervention")
    plan = validate_plan(plan_dict)
    schedule_plan(inter, plan)
    for _ in range(months):
        base.step()
        inter.step()
    eff = analysis.classify_effects(inter, base, min_effect=0.5)
    emerg = analysis.detect_emergence(inter, base)
    return {
        "seed": seed,
        "base": analysis.final_vector(base.metrics_history),
        "int": analysis.final_vector(inter.metrics_history),
        "base_hist": [{k: m[k] for k in ("month", "backlog_months", "delivery", "turnover_12m", "stress", "management_load", "cost_ytd")} for m in base.metrics_history],
        "int_hist": [{k: m[k] for k in ("month", "backlog_months", "delivery", "turnover_12m", "stress", "management_load", "cost_ytd")} for m in inter.metrics_history],
        "team_backlog_int": {t: v["backlog_months"] for t, v in inter.metrics_history[-1]["teams"].items()},
        "team_backlog_base": {t: v["backlog_months"] for t, v in base.metrics_history[-1]["teams"].items()},
        "effects": [{k: e[k] for k in ("metric", "team", "team_name", "effect_size", "relative_change", "lag_months", "order_label", "emergent", "graph_distance")} for e in eff["effects"][:25]],
        "emergence": [{k: e[k] for k in ("kind", "team", "label", "emergent")} for e in emerg],
        "significant_events": sum(1 for e in inter.events if e.significant),
        "decisions": len(inter.decision_log),
    }


def run_batch(template: str, plan: ChangePlan | dict, n: int = 100, months: int = 36, settle: int = 3, engine: str = "heuristic",
              seed0: int = 1000, config: Optional[SimConfig] = None, scale: float = 1.0, workers: Optional[int] = None,
              progress: Optional[Callable[[int, int], None]] = None) -> dict[str, Any]:
    plan_dict = plan.model_dump() if hasattr(plan, "model_dump") else plan
    cfg = config.to_dict() if config else None
    args = [(template, seed0 + i, plan_dict, months, settle, engine, cfg, scale) for i in range(n)]
    t0 = time.perf_counter()
    results: list[dict[str, Any]] = []
    if engine != "heuristic" or n <= 2:
        for i, a in enumerate(args):
            results.append(_run_one(a))
            if progress:
                progress(i + 1, n)
    else:
        workers = workers or max(1, min(8, (mp.cpu_count() or 2) - 1))
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with mp.get_context("spawn").Pool(workers, initializer=_init_worker, initargs=(backend_dir,)) as pool:
            for i, r in enumerate(pool.imap_unordered(_run_one, args, chunksize=max(1, n // (workers * 4)))):
                results.append(r)
                if progress:
                    progress(i + 1, n)
    results.sort(key=lambda r: r["seed"])
    elapsed = time.perf_counter() - t0
    return {"n": n, "months": months, "engine": engine, "elapsed_s": round(elapsed, 1), "summary": summarise(results, template), "runs": results}


def summarise(results: list[dict[str, Any]], template: str = "") -> dict[str, Any]:
    n = len(results)
    if n == 0:
        return {}

    def freq(pred) -> float:
        return round(sum(1 for r in results if pred(r)) / n, 3)

    def dist(key: str, which: str) -> dict[str, float]:
        xs = sorted(r[which][key] for r in results)
        return {"p10": round(xs[int(0.1 * (n - 1))], 3), "p50": round(xs[int(0.5 * (n - 1))], 3), "p90": round(xs[int(0.9 * (n - 1))], 3), "mean": round(sum(xs) / n, 3)}

    teams = list(results[0]["team_backlog_int"].keys())
    bottleneck_freq = {t: freq(lambda r, t=t: r["team_backlog_int"][t] > 1.0 and r["team_backlog_int"][t] > 2 * max(0.1, r["team_backlog_base"][t])) for t in teams}
    outcomes = {
        "bottleneck_anywhere": freq(lambda r: r["int"]["max_team_backlog"] > 1.0 and r["int"]["max_team_backlog"] > 2 * max(0.1, r["base"]["max_team_backlog"])),
        "delivery_deterioration_gt10pct": freq(lambda r: r["int"]["delivery"] < 0.9 * r["base"]["delivery"]),
        "severe_delivery_deterioration_gt25pct": freq(lambda r: r["int"]["delivery"] < 0.75 * r["base"]["delivery"]),
        "turnover_up": freq(lambda r: r["int"]["turnover_12m"] > r["base"]["turnover_12m"] + 2),
        "management_overload": freq(lambda r: r["int"]["management_load"] > 1.15 and r["base"]["management_load"] <= 1.15),
        "net_cost_saving": freq(lambda r: r["int"]["cost_ytd"] < 0.98 * r["base"]["cost_ytd"]),
        "stress_up": freq(lambda r: r["int"]["stress"] > r["base"]["stress"] + 0.05),
        "stable": freq(lambda r: r["int"]["max_team_backlog"] < 1.0 and r["int"]["delivery"] >= 0.9 * r["base"]["delivery"] and r["int"]["turnover_12m"] <= r["base"]["turnover_12m"] + 2),
    }
    # clusters
    keys = ["backlog_months", "delivery", "turnover_12m", "stress", "management_load", "cooperation", "max_team_backlog"]
    vectors = [[r["int"][k] - r["base"][k] for k in keys] for r in results]
    k = 2 if n < 12 else 3 if n < 60 else 4
    labels = analysis.kmeans(vectors, k) if n >= 4 else [0] * n
    clusters = []
    base_centre = {kk: sum(r["base"][kk] for r in results) / n for kk in results[0]["base"]}
    for c in range(max(labels) + 1 if labels else 0):
        members = [r for r, l in zip(results, labels) if l == c]
        if not members:
            continue
        centre = {kk: sum(r["int"][kk] for r in members) / len(members) for kk in results[0]["int"]}
        clusters.append({"id": c, "size": len(members), "share": round(len(members) / n, 3), "name": analysis.name_cluster(centre, base_centre),
                         "centre": {kk: round(v, 3) for kk, v in centre.items()}, "seeds": [r["seed"] for r in members][:20]})
    clusters.sort(key=lambda c: -c["size"])
    # surprises: distant variables that moved in a large share of runs
    tally: dict[tuple, dict] = {}
    for r in results:
        seen = set()
        for e in r["effects"]:
            key = (e["metric"], e["team"])
            if key in seen:
                continue
            seen.add(key)
            d = tally.setdefault(key, {"metric": e["metric"], "team": e["team"], "team_name": e["team_name"], "count": 0, "lags": [], "effects": [], "graph_distance": e["graph_distance"], "emergent": e["emergent"], "order_label": e["order_label"]})
            d["count"] += 1
            if e["lag_months"] is not None:
                d["lags"].append(e["lag_months"])
            d["effects"].append(e["effect_size"])
    surprises = []
    for d in tally.values():
        d["frequency"] = round(d["count"] / n, 3)
        d["median_lag"] = sorted(d["lags"])[len(d["lags"]) // 2] if d["lags"] else None
        d["mean_effect"] = round(sum(d["effects"]) / len(d["effects"]), 2)
        d.pop("lags"); d.pop("effects")
        if d["emergent"] and d["frequency"] >= 0.2 and (d["graph_distance"] is None or d["graph_distance"] >= 1):
            surprises.append(d)
    surprises.sort(key=lambda d: (-(d["graph_distance"] or 0), -d["frequency"]))
    emergence_freq: dict[str, int] = {}
    for r in results:
        for e in r["emergence"]:
            emergence_freq[e["label"]] = emergence_freq.get(e["label"], 0) + 1
    return {"n": n, "outcome_frequencies": outcomes, "bottleneck_frequency_by_team": bottleneck_freq,
            "distributions": {k: {"baseline": dist(k, "base"), "intervention": dist(k, "int")} for k in ("backlog_months", "delivery", "turnover_12m", "stress", "management_load", "cost_ytd", "max_team_backlog", "cooperation")},
            "clusters": clusters, "surprises": surprises[:12],
            "emergence_frequency": {k: round(v / n, 3) for k, v in sorted(emergence_freq.items(), key=lambda kv: -kv[1])[:12]},
            "disclaimer": "Frequencies are within the simulation model, not real-world probabilities."}
