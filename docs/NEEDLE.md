# Cactus Needle 3

**Verified API (Sept 2026, `cactus-needle` 3.0.2, Apache-2.0, 8–29 MB native model, weights auto-fetched from
`Cactus-Compute/needle3` into `~/.cache/cactus-needle/`):**
```python
import needle
def seek_help():
    """Ask a neighbouring team or colleague with spare capacity to take some of this employee's work."""
    return "seek_help"
tools = [needle.tool(seek_help), ...]                       # zero-arg functions; the docstring is the tool description
agent = needle.Needle(tools=tools, system=None, weights=None, auto_date=False)
r = agent.complete(state_text, max_new_tokens=96)
r["function_calls"][0]["name"], r["confidence"], r["reasoning"], r["suppressed_calls"]
agent.reset()                                               # periodically: decode slows/stalls on long streaks
```

## How the wind tunnel uses it (`decisions/needle_engine.py`)
Needle is tool-oriented, so each request's available actions become tools — **at most five** (Needle renders ≤5 tools
directly; beyond that retrieval filters them). Actions are ranked by relevance; `leave` is only
offered when turnover intention ≥ 0.3 to avoid keyword bait. One `Needle` instance per distinct tool set (cached), a
global lock (never two decodes at once), `reset()` every 12 calls. The first function call wins; an unknown tool name
maps to continue_as_normal (counted as `invalid_tool_calls`). Needle gives **one** confidence per call, so the
per-action distribution shown in the inspector is synthetic (flagged `synthetic_probabilities: true`).

## Measured (M5 Max)
* init 0.1 s; 150–180 ms per call with a 10-line state; **~500 ms** with the full ~30-line context and 5 tools.
* 6-month admin-cut run, 24 decisions/month: 12–14 s per month; mean confidence 0.73; routes execute 47% /
  probabilistic 34% / conservative 19%; 24 of 188 calls named a tool that was not offered (mapped to continue);
  actions: continue 65, delay_low_priority 35, escalate 24, overtime 19, protect_team 12, reduce_quality 8, workaround 8,
  request_recruitment 5 — a more varied distribution than Laya's on the same world. Guards fired 26 times.
* Needle keeps conversational state ("Earlier work_overtime …" appears in reasoning) — hence periodic reset.

## Pitfalls
* Tuned/pruned weights return `confidence=None`; only base weights are calibrated.
* Multi-process contention makes latency explode (95 ms → minutes). One Needle process per machine.
* Cap `max_new_tokens` (default 512 can loop for a minute on small rungs).
* Bias towards the most concrete tool name; use downgrade-only guards.
