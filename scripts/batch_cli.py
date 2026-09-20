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
    a = ap.parse_args()
    plan = rule_parse(a.text)
    print("plan:", [(c.operation, c.target, c.amount) for c in plan.changes], plan.protected_groups, plan.transition_period_months, flush=True)
    def prog(i, n):
        if i % max(1, n // 10) == 0 or i == n:
            print(f"  {i}/{n}", flush=True)
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

if __name__ == "__main__":
    main()
