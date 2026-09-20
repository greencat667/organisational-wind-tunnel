#!/usr/bin/env python
"""Run a Monte Carlo batch from the command line (no rendering).

    .venv/bin/python scripts/batch_cli.py --n 200 --months 36 --text "Reduce administrative capacity by 20%"
"""
import argparse, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "backend"))
from windtunnel import batch
from windtunnel.interventions.parser import rule_parse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--months", type=int, default=36)
    ap.add_argument("--template", default="prototype")
    ap.add_argument("--engine", default="heuristic")
    ap.add_argument("--text", default="Reduce administrative capacity by 20% while protecting frontline delivery.")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--sweep", default=None, help="SimConfig field and levels, e.g. ai_base_exception_rate=0.08,0.16,0.3 or target_utilisation=0.65,0.75,0.85")
    a = ap.parse_args()
    plan = rule_parse(a.text)
    print("plan:", [(c.operation, c.target, c.amount) for c in plan.changes], plan.protected_groups, plan.transition_period_months, flush=True)
    def prog(i, n):
        if i % max(1, n // 10) == 0 or i == n:
            print(f"  {i}/{n}", flush=True)
    if a.sweep:
        run_sweep(a, plan)
        return
    res = batch.run_batch(a.template, plan, n=a.n, months=a.months, engine=a.engine, workers=a.workers, progress=prog)
    s = res["summary"]
    print(f"\n{res['n']} simulations x 2 worlds x {res['months']} months in {res['elapsed_s']} s")
    print(json.dumps(s["outcome_frequencies"], indent=1))
    print("bottleneck frequency by team:", s["bottleneck_frequency_by_team"])
    print("clusters:", [(c["name"], c["share"]) for c in s["clusters"]])
    print("surprises:", [(x["team_name"], x["metric"], x["frequency"], x["median_lag"]) for x in s["surprises"][:8]])
    print("emergence:", s["emergence_frequency"])
    print(s["disclaimer"])
    if a.out:
        with open(a.out, "w") as f:
            json.dump({k: v for k, v in res.items() if k != "runs"}, f, indent=1)
        print("written", a.out)

def run_sweep(a, plan):
    """Sensitivity analysis: rerun the batch for each level of one SimConfig parameter and tabulate outcome frequencies."""
    from windtunnel.config import SimConfig
    field, levels = a.sweep.split("=")
    levels = [float(x) for x in levels.split(",")]
    if field not in SimConfig.__dataclass_fields__:
        raise SystemExit(f"unknown SimConfig field {field!r}; choose from: {', '.join(SimConfig.__dataclass_fields__)}")
    rows = []
    for lv in levels:
        cfg = SimConfig()
        setattr(cfg, field, int(lv) if isinstance(getattr(cfg, field), int) and not isinstance(getattr(cfg, field), bool) else lv)
        print(f"\n--- {field} = {lv} ---", flush=True)
        res = batch.run_batch(a.template, plan, n=a.n, months=a.months, engine=a.engine, workers=a.workers, config=cfg)
        s = res["summary"]
        rows.append((lv, s["outcome_frequencies"], {k: v["intervention"]["p50"] for k, v in s["distributions"].items()}))
        print(f"  {res['elapsed_s']} s; stable {s['outcome_frequencies']['stable']:.0%}; clusters {[(c['name'], c['share']) for c in s['clusters'][:3]]}", flush=True)
    keys = sorted({k for _, o, _ in rows for k in o})
    print(f"\nSensitivity of outcome frequencies to {field} (n={a.n} worlds per level; frequencies within the model):")
    print("level".ljust(10) + "".join(k[:22].ljust(24) for k in keys))
    for lv, o, _ in rows:
        print(f"{lv:<10}" + "".join(f"{o.get(k, 0):<24.2f}" for k in keys))
    print("\nMedian intervention metrics per level:")
    mkeys = ["backlog_months", "delivery", "turnover_12m", "stress", "cost_ytd", "max_team_backlog"]
    print("level".ljust(10) + "".join(k.ljust(18) for k in mkeys))
    for lv, _, d in rows:
        print(f"{lv:<10}" + "".join(f"{d.get(k, 0):<18.3g}" for k in mkeys))
    if a.out:
        with open(a.out, "w") as f:
            json.dump({"field": field, "rows": [{"level": lv, "outcomes": o, "medians": d} for lv, o, d in rows]}, f, indent=1)
        print("written", a.out)


if __name__ == "__main__":
    main()
