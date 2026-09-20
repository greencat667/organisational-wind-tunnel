"""Natural-language intervention -> validated ChangePlan.

Primary: Apple Foundation Models via Apple's own ``fm serve`` (macOS 26/27 built-in CLI) using
OpenAI-style chat completions with ``response_format: json_schema`` (guided generation). The
server is started on demand as a subprocess on a private port. Fallback: a rule-based parser so
the application always works without the model. The model only ever fills the schema — it never
decides outcomes.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from typing import Any, Optional

import httpx

from .schema import AFM_SCHEMA, ChangePlan, validate_plan

FM_PORT = int(os.environ.get("WINDTUNNEL_FM_PORT", "17976"))
FM_URL = f"http://127.0.0.1:{FM_PORT}"

SYSTEM_PROMPT = (
    "You convert a manager's natural-language description of an organisational change into a structured change plan "
    "for a simulation. Only restate what was asked. Do NOT predict consequences, outcomes, morale, productivity or costs. "
    "Targets are function tags: admin (finance, business support, HR, procurement, administration, back office), "
    "frontline (programme delivery, services), support (operations), income (fundraising, communications), technology, "
    "management (executive, directors), or all. Operations: reduce_capacity (headcount cut, percent positive), "
    "deploy_ai_agents (AI agents take on a share of a team's work; percent = share), convert_to_supervisory (staff supervise AI agents), "
    "ai_run_process (an AI runs a workflow end to end with human escalation; percent = share of cases), "
    "increase_capacity (headcount growth), merge_teams (list team names), remove_management_layer (flatten; autonomy), "
    "change_budget (percent negative for cuts), change_demand (percent, negative for falls), enable_automation (AI/automation; "
    "percent = share of routine work), change_working_hours (percent), shock (kind: funding_cut, demand_spike, staff_shortage, supplier_failure). "
    "If a group is to be protected or kept unchanged, list it in protected_groups. transition_period_months: use the stated period, else 1 "
    "for immediate changes, 6 for restructures."
)


class FMServer:
    """Manages a local `fm serve` process (Apple Foundation Models CLI)."""

    def __init__(self, port: int = FM_PORT):
        self.port = port
        self.proc: Optional[subprocess.Popen] = None
        self.available = shutil.which("fm") is not None
        self.last_latency_ms: float = 0.0
        self.calls = 0
        self.failures = 0

    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def healthy(self, timeout: float = 0.5) -> bool:
        try:
            r = httpx.get(self.url() + "/health", timeout=timeout)
            return r.status_code == 200
        except Exception:
            return False

    def responsive(self, timeout: float = 6.0) -> bool:
        """The system model daemon is shared machine-wide and can be wedged by other callers; probe with a tiny request (cached 60 s)."""
        now = time.time()
        cached = getattr(self, "_resp_cache", None)
        if cached and now - cached[0] < 60:
            return cached[1]
        ok = self._probe(timeout)
        self._resp_cache = (now, ok)
        return ok

    def _probe(self, timeout: float) -> bool:
        try:
            r = httpx.post(self.url() + "/v1/chat/completions", json={"model": "system", "stream": False,
                           "messages": [{"role": "user", "content": "Reply with the single word: ready"}]}, timeout=timeout)
            return r.status_code == 200
        except Exception:
            return False

    def ensure(self, wait_s: float = 8.0) -> bool:
        if self.healthy():
            return True
        if not self.available:
            return False
        if self.proc is None or self.proc.poll() is not None:
            try:
                self.proc = subprocess.Popen(["fm", "serve", "--port", str(self.port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                return False
        t0 = time.time()
        while time.time() - t0 < wait_s:
            if self.healthy():
                return True
            time.sleep(0.25)
        return False

    def chat_json(self, system: str, user: str, schema: dict, timeout: float = 25.0) -> dict[str, Any]:
        body = {"model": "system", "temperature": 0,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema", "json_schema": {"name": schema.get("title", "Out"), "schema": schema}},
                "stream": False}
        t0 = time.perf_counter()
        self.calls += 1
        try:
            r = httpx.post(self.url() + "/v1/chat/completions", json=body, timeout=timeout)
            r.raise_for_status()
            data = r.json()
        except Exception:
            self.failures += 1
            raise
        finally:
            self.last_latency_ms = (time.perf_counter() - t0) * 1000.0
        content = ""
        if isinstance(data, dict) and data.get("choices"):
            content = data["choices"][0].get("message", {}).get("content", "")
        else:  # some builds stream even when asked not to: parse SSE chunks
            content = _join_sse(r.text)
        return json.loads(content)

    def chat_text(self, system: str, user: str, timeout: float = 25.0) -> str:
        body = {"model": "system", "temperature": 0.3, "stream": False,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        t0 = time.perf_counter()
        self.calls += 1
        try:
            r = httpx.post(self.url() + "/v1/chat/completions", json=body, timeout=timeout)
            r.raise_for_status()
        except Exception:
            self.failures += 1
            raise
        finally:
            self.last_latency_ms = (time.perf_counter() - t0) * 1000.0
        try:
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception:
            return _join_sse(r.text)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


def _join_sse(text: str) -> str:
    out = []
    for line in text.splitlines():
        if line.startswith("data: ") and line[6:].strip() != "[DONE]":
            try:
                ch = json.loads(line[6:])
                for c in ch.get("choices", []):
                    out.append(c.get("delta", {}).get("content", "") or "")
            except json.JSONDecodeError:
                pass
    return "".join(out)


# ------------------------------------------------------------------ rule-based fallback

_PCT = re.compile(r"(-?\d+(?:\.\d+)?)\s*%|(-?\d+(?:\.\d+)?)\s*(?:per\s*cent|percent)")
_MONTHS = re.compile(r"(\d+)\s*(?:months?|mths?)|(\d+|one|two|three)\s*years?")
_WORDNUM = {"one": 1, "two": 2, "three": 3}
_TARGET_WORDS = [
    ("admin", ["admin", "administrative", "administration", "back office", "back-office", "business support", "finance", "hr", "people team", "procurement", "overhead"]),
    ("frontline", ["frontline", "front-line", "front line", "programme", "program", "delivery", "service"]),
    ("income", ["fundraising", "communications", "comms", "marketing", "income"]),
    ("technology", ["technology", "tech", "it ", "digital"]),
    ("support", ["operations", "ops "]),
    ("management", ["management layer", "managers", "middle management", "directors", "executive"]),
]


def _pct(text: str, default: float) -> float:
    m = _PCT.search(text)
    if m:
        v = float(m.group(1) or m.group(2))
        return v / 100.0
    if "half" in text or "halve" in text:
        return 0.5
    if "double" in text or "doubles" in text:
        return 1.0
    return default


def _months(text: str, default: int) -> int:
    m = _MONTHS.search(text)
    if not m:
        return default
    if m.group(1):
        return int(m.group(1))
    y = m.group(2)
    return 12 * (_WORDNUM.get(y) or int(y))


def _targets(text: str) -> list[str]:
    t = text.lower()
    found = []
    for tag, words in _TARGET_WORDS:
        if any(w in t for w in words):
            found.append(tag)
    return found


def _protected(text: str) -> list[str]:
    t = text.lower()
    m = re.search(r"(?:protect(?:ing)?|preserv(?:e|ing)|maintain(?:ing)?|keep(?:ing)?|ring-?fenc(?:e|ing)|without affecting|unchanged)\s+([^.,;]+)", t)
    if not m:
        return []
    return _targets(m.group(1))


def rule_parse(text: str) -> ChangePlan:
    t = text.lower()
    protected = _protected(text)
    months = _months(t, 1)
    changes: list[dict[str, Any]] = []
    itype = "restructure"
    if "merge" in t or "combine" in t:
        itype = "structure"
        names = re.findall(r"merge (?:the )?([\w &]+?) and (?:the )?([\w &]+?)(?: teams?)?(?:[.,;]|$)", t)
        teams = list(names[0]) if names else _targets(text)
        changes.append({"operation": "merge_teams", "target": "all", "teams": [n.strip().replace(" teams", "").replace(" team", "") for n in teams][:2]})
        months = months if months > 1 else 3
    elif "layer" in t or "flatten" in t or "autonom" in t or "self-managing" in t or "multidisciplinary" in t:
        itype = "structure"
        gain = 0.3
        m = re.search(r"autonomy[^0-9]{0,20}(\d+)\s*%", t)
        if m:
            gain = int(m.group(1)) / 100.0
        changes.append({"operation": "remove_management_layer", "target": "management", "autonomy_gain": gain})
        months = months if months > 1 else 6
    elif "automat" in t or " ai " in f" {t} " or "artificial intelligence" in t or "agents" in t:
        itype = "automation"
        share = _pct(t, 0.4)
        tg = [x for x in _targets(text) if x != "management"] or ["admin"]
        if "supervis" in t:
            changes.append({"operation": "convert_to_supervisory", "target": tg, "amount": share})
        elif "workflow" in t or "loop" in t or "end to end" in t or "end-to-end" in t:
            changes.append({"operation": "ai_run_process", "target": tg, "amount": share})
        elif "agent" in t:
            changes.append({"operation": "deploy_ai_agents", "target": tg, "amount": share})
        else:
            changes.append({"operation": "enable_automation", "target": tg, "amount": share})
        months = months if months > 1 else 12
    elif "budget" in t or "income" in t or "funding" in t or "spend" in t:
        itype = "budget"
        amt = _pct(t, 0.15)
        sign = -1 if any(w in t for w in ("cut", "reduce", "fall", "drop", "decrease", "save", "lower")) else 1
        if "income" in t or "funding" in t:
            changes.append({"operation": "shock", "target": "all", "kind": "funding_cut" if sign < 0 else "funding_increase", "amount": amt})
        else:
            changes.append({"operation": "change_budget", "target": _targets(text) or ["all"], "amount": sign * amt})
    elif "demand" in t or "caseload" in t or "requests" in t or "volume" in t:
        itype = "demand"
        amt = _pct(t, 0.3)
        sign = -1 if any(w in t for w in ("fall", "drop", "reduce", "decrease", "halve")) else 1
        changes.append({"operation": "change_demand", "target": "all", "amount": sign * amt})
        months = months if months > 1 else 1
    elif "hours" in t or "four-day" in t or "4-day" in t:
        itype = "process"
        amt = _pct(t, 0.2)
        sign = -1 if any(w in t for w in ("reduce", "cut", "four", "4-day", "shorter")) else 1
        changes.append({"operation": "change_working_hours", "target": _targets(text) or ["all"], "amount": sign * amt})
    elif any(w in t for w in ("hire", "recruit", "grow", "increase headcount", "expand", "add ")) and not any(w in t for w in ("cut", "reduce")):
        itype = "headcount"
        changes.append({"operation": "increase_capacity", "target": _targets(text) or ["frontline"], "amount": _pct(t, 0.2)})
    else:
        itype = "restructure"
        tg = [x for x in _targets(text) if x not in protected] or ["admin"]
        changes.append({"operation": "reduce_capacity", "target": tg, "amount": _pct(t, 0.2)})
        months = months if months > 1 else 3
    plan = validate_plan({"intervention_type": itype, "summary": text.strip()[:200], "objectives": [], "changes": changes,
                          "protected_groups": protected, "transition_period_months": months, "source": "rules"})
    return plan


# ------------------------------------------------------------------ public API

class InterventionParser:
    def __init__(self, fm: Optional[FMServer] = None, use_fm: bool = True):
        self.fm = fm or FMServer()
        self.use_fm = use_fm
        self.last_source = "rules"
        self.last_error: Optional[str] = None
        self.last_raw: Optional[dict] = None

    def parse(self, text: str, org_hint: str = "") -> ChangePlan:
        self.last_error = None
        rules = rule_parse(text)
        if self.use_fm and self.fm.ensure() and self.fm.responsive():
            try:
                user = f"Organisation teams: {org_hint}\n\nRequested change: {text}" if org_hint else f"Requested change: {text}"
                raw = self.fm.chat_json(SYSTEM_PROMPT, user, AFM_SCHEMA)
                self.last_raw = raw
                raw["source"] = "apple_fm"
                plan = validate_plan(raw)
                plan = _reconcile(plan, rules, text)
                self.last_source = "apple_fm"
                return plan
            except Exception as exc:  # fall back, but record why
                self.last_error = repr(exc)[:300]
        self.last_source = "rules"
        return rules

    def explain(self, prompt: str) -> str:
        """Plain-language explanation of *observed* simulation results (facts are supplied in the prompt)."""
        if self.use_fm and self.fm.ensure() and self.fm.responsive():
            try:
                return self.fm.chat_text(
                    "You write short, plain-English summaries of results from an organisational simulation. Only describe the numbers "
                    "and events you are given; do not add causes that are not listed and do not generalise to the real world. "
                    "Write at most 120 words. Refer to it as 'the simulation'.", prompt)
            except Exception as exc:
                self.last_error = repr(exc)[:300]
        return ""


def _reconcile(plan: ChangePlan, rules: ChangePlan, text: str) -> ChangePlan:
    """Guard against model drift: percentages and protected groups explicitly stated in the text win."""
    m = _PCT.search(text)
    if m:
        stated = abs(float(m.group(1) or m.group(2))) / 100.0
        for ch in plan.changes:
            if ch.operation in ("reduce_capacity", "increase_capacity", "change_budget", "change_demand", "enable_automation", "change_working_hours", "shock") and ch.amount is not None:
                if abs(abs(ch.amount) - stated) > 0.005:
                    ch.amount = stated if ch.amount >= 0 else -stated
    if rules.protected_groups and not plan.protected_groups:
        plan.protected_groups = rules.protected_groups
    if not plan.summary:
        plan.summary = text.strip()[:200]
    return plan
