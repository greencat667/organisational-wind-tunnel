# Laya

**Verified API (Sept 2026, `laya` 0.1.6–0.3.x, weights `convaiinnovations/laya`, ModernBERT-large 421M, Apache-2.0):**
```python
import laya
agent = laya.load("convaiinnovations/laya", device=None)        # cuda > mps > cpu
res = agent.predict(state_text, {
    "seek_help": {"type": "noul",   "instructions": "Should this employee ask a neighbouring team for help…?"},
    "help_target": {"type": "choice", "instructions": "…which team?", "criteria": {"finance": "…", "operations": "…"}},
    "effort": {"type": "score",  "instructions": "How much effort…?", "criteria": ["minimal", "reduced", "normal", "high", "maximum"]},
})
res["answers"]["seek_help"]      # {"noul": P(true), "confidence": max(p, 1-p)}
res["answers"]["help_target"]    # {"choice", "probabilities", "confidence"}
res["answers"]["effort"]         # {"score": expected level, "probabilities", "confidence"}
```

## How the wind tunnel uses it (`decisions/laya_engine.py`)
One `predict` per agent decision: a `noul` question for every available action (from `actions.py`), a `choice` for
the help target when relevant, and two `score` questions (effort, turnover pressure). P(action) = adjusted P(yes);
P(continue) = ∏(1−P(yes)). Confidence = Laya's own confidence for the winning question.

**Neutral-state calibration.** Following an earlier finding that Laya prefers concrete-sounding labels, the engine
asks every action question once on a calm reference state at load time and shifts each P(yes) in logit space so that
the neutral answer maps to 0.15. Measured neutral P(yes) on this machine: seek_help 0.88, use_workaround 0.95,
automate_task 0.94, redistribute_work 0.75, approve_overtime 0.78, protect_team 0.75 — i.e. without calibration those
actions would fire constantly. The calibration is shown in the engine description and in each decision's raw output.

## Measured (M5 Max, MPS, macOS 27)
* load 22–38 s (warm cache); first call ~1.4 s.
* 6–10 questions per call with a ~30-line state: **mean 250–300 ms**, max 0.8–1.8 s.
* A 100-person month with ~35 triggered decisions: 9–13 s. Hence the 24-decision cap for AI engines and the cache.
* In a 6-month admin-cut run after calibration Laya chose reduce_quality 108×, delay_low_priority 88×, escalate 32×,
  escalate_up 23×, continue 22×; 79% of decisions routed "execute", mean confidence 0.86; guards fired 5 times.

## Pitfalls
* Keyword bait: question wording drives P(yes) more than state does; calibrate and guard.
* Long lists of `choice` criteria degrade; prefer one `noul` per action.
* One MPS device: calls are serialised with a lock. Never run two Laya processes at once.
* No streaming, no per-call latency field (we time it ourselves).
