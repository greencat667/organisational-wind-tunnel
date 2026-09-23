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

try:                        # only needed to talk to Apple's `fm serve`; absent in the browser build
    import httpx
except ImportError:         # pragma: no cover
    httpx = None

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
    "percent = share of routine work), change_working_hours (percent), freeze_hiring, remove_approval, shock (kind: funding_cut, funding_increase, demand_spike, staff_shortage, supplier_failure). "
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

    def responsive(self, timeout: float = 8.0) -> bool:
        """The system model daemon is shared machine-wide and can be wedged by other callers.

        Guided JSON generation (``response_format: json_schema``) is the mode that actually
        hangs in practice, even when a plain chat request answers fine — so the probe must
        exercise a schema-guided request, not plain chat, or it reports "healthy" right before
        a real call stalls for the full timeout. A positive result is cached briefly (60 s); a
        negative one is cached much longer (300 s), since a stuck daemon costs a full timeout
        to rediscover and tends to stay stuck rather than recover within seconds.
        """
        now = time.time()
        cached = getattr(self, "_resp_cache", None)
        if cached:
            ts, ok = cached
            if now - ts < (60 if ok else 300):
                return ok
        ok = self._probe(timeout)
        self._resp_cache = (now, ok)
        return ok

    def _probe(self, timeout: float) -> bool:
        schema = {"title": "Probe", "type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"]}
        try:
            r = httpx.post(self.url() + "/v1/chat/completions", json={
                "model": "system", "stream": False, "temperature": 0,
                "messages": [{"role": "user", "content": 'Reply with JSON {"word": "ready"}'}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "Probe", "schema": schema}},
            }, timeout=timeout)
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
#
# The rule parser is deliberately conservative: it would rather say "I didn't understand that part" (a warning, and no
# change) than guess. Guessing was the old failure mode — anything unrecognised became "cut admin by 20%".

_PCT = re.compile(r"(-?\d+(?:\.\d+)?)\s*%|(-?\d+(?:\.\d+)?)\s*(?:per\s*cent|percent)")
_COUNT_VERB = re.compile(r"\b(?:hire|hiring|recruit\w*|add|adding|cut|cutting|remove|removing|lose|losing|shed|shedding)\s+(?:another\s+)?(\d+)\b(?!\s*%)")
_COUNT = re.compile(r"\b(\d+)\s+(?:more\s+|new\s+|extra\s+|additional\s+)?(?:posts?|people|roles?|staff|jobs?|fte|heads?|employees?|positions?)\b")
_FRACTIONS = [(r"\bhalf\b|\bhalve[sd]?\b|\bhalving\b", 0.5), (r"\ba third\b|\bone third\b|\bone-third\b", 1 / 3), (r"\ba quarter\b|\bone quarter\b", 0.25),
              (r"\ba fifth\b|\bone fifth\b", 0.2), (r"\ba tenth\b|\bone tenth\b", 0.1), (r"\btwo thirds\b|\btwo-thirds\b", 2 / 3)]
_MULTIPLES = [(r"\bdouble[sd]?\b|\bdoubling\b", 1.0), (r"\btriple[sd]?\b|\btripling\b", 2.0)]
_MONTHS = re.compile(r"(\d+)\s*(?:months?|mths?)\b|(\d+|one|two|three|four|five)\s*years?\b|\b(?:a|one|next)\s+year\b|\b(a|one)\s+month\b")
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

# Specific names come first so "finance" targets the Finance team, not every admin team. resolve_targets() maps a name
# the organisation doesn't have (e.g. "hr" in the 100-person template) back to its function via _NAME_FALLBACK.
_TARGET_WORDS = [
    ("finance", [r"finance", r"financial accounting", r"accounts"]),
    ("business support", [r"business support"]),
    ("procurement", [r"procurement", r"purchasing"]),
    ("hr", [r"hr", r"human resources", r"people team", r"people function"]),
    ("admin", [r"admin", r"administrative", r"administration", r"back[ -]office", r"back[ -]end", r"overheads?", r"central services"]),
    ("frontline", [r"front[ -]?line", r"programmes?", r"programs?", r"delivery", r"campaign(?:s|ing|ers)?"]),
    ("fundraising", [r"fundraising", r"fundraisers?"]),
    ("comms", [r"communications", r"comms", r"marketing", r"media"]),
    ("income", [r"income teams?", r"income"]),
    ("technology", [r"technology", r"tech", r"it (?:team|department|staff|function)", r"digital", r"data"]),
    ("support", [r"operations", r"ops"]),
    ("management", [r"management layers?", r"managers", r"middle management", r"directors?", r"executive", r"leadership"]),
]
_TARGET_RES = [(tag, re.compile(r"\b(?:" + "|".join(ws) + r")\b")) for tag, ws in _TARGET_WORDS]
_SPECIFIC_UNDER = {"finance": "admin", "business support": "admin", "procurement": "admin", "hr": "admin",
                   "fundraising": "income", "comms": "income"}

_VERBS = re.compile(r"\b(cut|cuts|cutting|reduce[sd]?|reducing|remove[sd]?|removing|lose|losing|shrink|shrinking|slash|trim|hire|hiring|recruit(?:ing)?|"
                    r"grow|growing|add|adding|increase[sd]?|increasing|expand(?:ing)?|merge|merging|combine|combining|automate|automating|"
                    r"deploy(?:ing)?|introduce|introducing|flatten(?:ing)?|double|halve|triple|freeze|freezing|outsource|outsourcing|"
                    r"raise|lower|drop|fall|rise|spike|move|shift|convert|let|run|delegate|scrap|abolish|delete|invest|save|make)\b")
_NEGATION = re.compile(r"\b(?:do not|don't|dont|never|must not|mustn't|shouldn't|should not|without|avoid|no)\s+(?:\w+\s+){0,2}?"
                       r"(cut|reduc|remov|touch|affect|chang|los|shrink|redundan|hire|recruit|increas|merg|automat)")
_PROTECT = re.compile(r"(?:,?\s*(?:while|whilst|but|and)\s+)?(?:protect(?:ing)?|preserv(?:e|ing)|maintain(?:ing)?|keep(?:ing)?|ring-?fenc(?:e|ing)|"
                      r"without affecting|leav(?:e|ing)\s+(?:\w+\s+){0,3}?untouched|safeguard(?:ing)?)\s+(.+?)(?=\s+(?:and|but|while|whilst|then)\b|[.,;]|$)")
_AI_WORDS = re.compile(r"\b(?:automat\w*|ai|artificial intelligence|agents?|llms?|chatbots?|copilots?)\b")
_PROCS = (("procurement", ["procurement"]), ("invoice", ["invoic"]), ("payroll", ["expense", "payroll"]),
          ("support", ["support request", "it support", "helpdesk", "service desk"]), ("donor", ["supporter enquir", "enquir"]),
          ("logistics", ["logistic"]), ("data", ["data request"]), ("hr_case", ["people case", "hr case", "recruitment process"]),
          ("reporting", ["reporting"]))

EXAMPLES = ("e.g. “Reduce admin by 20% while protecting frontline delivery”, “Hire 10 people into technology”, "
            "“Merge finance and business support” or “Automate the back end over a year”.")


def _fraction(text: str) -> Optional[float]:
    m = _PCT.search(text)
    if m:
        return abs(float(m.group(1) or m.group(2))) / 100.0
    m = re.search(r"\b(\d+)\s*/\s*(\d+)\b", text)
    if m and int(m.group(2)) > 0 and int(m.group(1)) < int(m.group(2)):
        return int(m.group(1)) / int(m.group(2))
    for pat, v in _FRACTIONS + _MULTIPLES:
        if re.search(pat, text):
            return v
    return None


def _count(text: str) -> Optional[int]:
    m = _COUNT.search(text) or _COUNT_VERB.search(text)
    return int(m.group(1)) if m else None


def _months(text: str) -> Optional[int]:
    m = _MONTHS.search(text)
    if not m:
        return None
    if m.group(1):
        return int(m.group(1))
    if m.group(2):
        return 12 * (_WORDNUM.get(m.group(2)) or int(m.group(2)))
    if m.group(3):
        return 1
    return 12


def _targets(text: str) -> list[str]:
    t = text.lower()
    found = [tag for tag, rx in _TARGET_RES if rx.search(t)]
    # a specific name ("finance") makes its umbrella tag ("admin") redundant only if the umbrella word itself wasn't used
    return found


def _extract_protected(t: str) -> tuple[list[str], str]:
    """Pull 'while protecting X' out of the text so X can never be read as a target."""
    m = _PROTECT.search(t)
    if not m:
        return [], t
    groups = _targets(m.group(1))
    if not groups:  # "keep costs down" is not a protection clause
        return [], t
    return groups, (t[:m.start()] + t[m.end():]).strip()


def _split_clauses(t: str) -> list[str]:
    """Split on and/;/then, but re-join any fragment without its own action verb ("merge finance and business support")."""
    parts = [p for p in re.split(r"\s*(?:;|,?\s*\band then\b|,?\s*\bthen\b|,?\s*\band also\b|,?\s*\balso\b|,?\s*\band\b|,?\s*\bplus\b|,?\s*\bbut\b|,\s*(?=(?:do not|don't|never|without|avoid)\b))\s*", t) if p and p.strip()]
    out: list[str] = []
    for p in parts:
        if out and not _VERBS.search(p):
            out[-1] = f"{out[-1]} and {p}"
        else:
            out.append(p)
    return out or [t]


def _parse_clause(c: str, protected: list[str], warnings: list[str]) -> Optional[tuple[str, list[dict[str, Any]], int]]:
    """One clause → (intervention type, changes, default transition months) or None if not understood."""
    frac, count = _fraction(c), _count(c)

    def assumed(v: float, what: str) -> float:
        if frac is None and count is None:
            warnings.append(f"“{c}”: no size given — assumed {int(round(v * 100))}% {what}. Edit the plan to change it.")
        return v
    tg = [x for x in _targets(c) if x not in protected]
    reducing = bool(re.search(r"\b(cut|cuts|reduc\w*|remov\w*|lose|losing|shrink\w*|slash\w*|trim\w*|halv\w*|lower\w*|decreas\w*|fall\w*|drop\w*|save|saving|scrap|abolish|delete|redundan\w*|fewer|less)\b", c))
    growing = bool(re.search(r"\b(hire|hiring|recruit\w*|grow\w*|add|adding|increas\w*|expand\w*|doubl\w*|tripl\w*|rais\w*|rise|rising|more|invest\w*|spike)\b", c))

    if re.search(r"\b(merge|merging|combine|combining|amalgamate)\b", c):
        m = re.search(r"\b(?:merge|merging|combine|combining|amalgamate)\s+(?:the\s+)?(.+?)\s+(?:and|with|into)\s+(?:the\s+)?(.+?)(?:\s+teams?)?\s*$", c)
        names = [m.group(1), m.group(2)] if m else []
        names = [re.sub(r"\s+teams?$", "", n.strip()) for n in names]
        if len(names) < 2:
            warnings.append(f"“{c}”: couldn't tell which two teams to merge — name them, e.g. “merge finance and business support”.")
            return None
        return "structure", [{"operation": "merge_teams", "target": "all", "teams": names}], 3

    if re.search(r"\b(flatten\w*|de-?layer\w*|self-managing|multidisciplinary)\b|\bmanagement layer|\blayer of management|\bautonomy\b", c):
        gain = 0.3
        m = re.search(r"autonomy[^0-9]{0,20}(\d+)\s*%", c)
        if m:
            gain = int(m.group(1)) / 100.0
        return "structure", [{"operation": "remove_management_layer", "target": "management", "autonomy_gain": gain}], 6

    if re.search(r"\b(freez\w*|froze)\b", c) and re.search(r"\b(hiring|recruit\w*|vacanc\w*|headcount)\b", c):
        return "headcount", [{"operation": "freeze_hiring", "target": tg or ["all"]}], 1

    if re.search(r"\bapprovals?\b|\bsign-?off\b", c) and reducing and not _AI_WORDS.search(c):
        procs = [pid for pid, words in _PROCS if any(w in c for w in words)]
        if not procs:
            warnings.append(f"“{c}”: which process's approval step? e.g. “remove the approval step from procurement”.")
            return None
        return "process", [{"operation": "remove_approval", "target": "all", "process": p} for p in procs], 1

    if _AI_WORDS.search(c):
        share = min(frac, 1.0) if frac is not None else assumed(0.4, "of routine work")
        tg = [x for x in tg if x != "management"] or ["admin"]
        no_replace = any(w in c for w in ("not replace", "no replacement", "attrition", "don't replace", "do not replace", "without replacing"))
        delegate = any(w in c for w in ("delegate approval", "ai approv", "agents approve", "approvals to ai", "including approvals"))
        procs = [pid for pid, words in _PROCS if any(w in c for w in words)]
        changes: list[dict[str, Any]] = []
        if re.search(r"\b(workflows?|loops?|end[ -]to[ -]end)\b", c):
            ch = {"operation": "ai_run_process", "target": tg, "amount": share, "delegate_approvals": delegate}
            if procs:
                ch["processes"] = procs
            changes.append(ch)
            if "supervis" in c:
                changes.append({"operation": "convert_to_supervisory", "target": tg, "amount": 0.25})
        elif "supervis" in c:
            sup_share = 0.5 if re.search(r"\bhalf\b|50\s*%", c) else 0.3
            if re.search(r"\b(agents?|ai)\b", c):
                changes.append({"operation": "deploy_ai_agents", "target": tg, "amount": 0.4 if frac is None or frac == sup_share else share, "replace_leavers": not no_replace})
            changes.append({"operation": "convert_to_supervisory", "target": tg, "amount": sup_share})
        elif re.search(r"\bagents?\b|back[ -]office|back[ -]end", c):
            changes.append({"operation": "deploy_ai_agents", "target": tg, "amount": share, "replace_leavers": not no_replace})
        else:
            changes.append({"operation": "enable_automation", "target": tg, "amount": share})
        return "automation", changes, 12

    if re.search(r"\b(income|funding|grants?|donations?)\b", c) and (reducing or growing):
        amt = frac if frac is not None else assumed(0.15, "")
        kind = "funding_cut" if reducing else "funding_increase"
        return "budget", [{"operation": "shock", "target": "all", "kind": kind, "amount": min(amt, 0.9 if reducing else 3.0)}], 1

    if re.search(r"\b(budgets?|spend\w*|costs?)\b", c) and (reducing or growing):
        amt = frac if frac is not None else assumed(0.15, "")
        return "budget", [{"operation": "change_budget", "target": [x for x in tg if x != "income"] or ["all"], "amount": -min(amt, 0.9) if reducing else min(amt, 3.0)}], 1

    if re.search(r"\b(demand|caseloads?|requests|volumes?|workload coming in|enquiries)\b", c) and (reducing or growing):
        amt = frac if frac is not None else assumed(0.3, "")
        return "demand", [{"operation": "change_demand", "target": "all", "amount": -min(amt, 0.9) if reducing else min(amt, 3.0)}], 1

    if re.search(r"\b(hours|four-day|4-day|part-time|working week)\b", c):
        amt = frac if frac is not None else assumed(0.2, "")
        shorter = reducing or bool(re.search(r"\b(four-day|4-day|shorter|part-time)\b", c))
        return "process", [{"operation": "change_working_hours", "target": tg or ["all"], "amount": -min(amt, 0.5) if shorter else min(amt, 0.5)}], 1

    if re.search(r"\b(outsourc\w*|offshor\w*|insourc\w*|hybrid|office|relocat\w*|restructure|reorgani[sz]\w*)\b", c) and not (reducing or growing):
        warnings.append(f"“{c}”: the simulator has no primitive for this yet (outsourcing, relocation, hybrid working and generic "
                        "restructures aren't modelled). Nothing was added for it.")
        return None

    if growing and not reducing:
        if not tg:
            warnings.append(f"“{c}”: grow which teams? Nothing was added — name a team or function (e.g. “hire 10 people into technology”).")
            return None
        ch = {"operation": "increase_capacity", "target": tg, "amount": min(frac, 3.0) if frac is not None else (0.2 if count is not None else assumed(0.2, "growth"))}
        if count is not None:
            ch["count"] = count
        return "headcount", [ch], 1

    if reducing:
        if not tg:
            warnings.append(f"“{c}”: cut which teams? Nothing was added — name a team or function (e.g. “reduce admin by 20%”).")
            return None
        amt = frac if frac is not None else (0.2 if count is not None else assumed(0.2, "of posts"))
        if amt > 0.6:
            warnings.append(f"“{c}”: a {int(amt*100)}% cut is extreme; capped at 60% of each team's posts.")
            amt = 0.6
        ch = {"operation": "reduce_capacity", "target": tg, "amount": amt}
        if count is not None:
            ch["count"] = count
        return "restructure", [ch], 3

    warnings.append(f"“{c}”: not understood — no change was added for it.")
    return None


def rule_parse(text: str) -> ChangePlan:
    raw = text.strip()
    t = re.sub(r"\s+", " ", raw.lower()).rstrip(".!")
    warnings: list[str] = []
    protected, body = _extract_protected(t)
    months = _months(t)
    if re.search(r"\b(next|from|starting|in)\s+(year|january|april|spring|autumn|\d{4})\b", t):
        warnings.append("Start dates aren't modelled: the change begins next month and is phased over the transition period.")
    if months is not None and months > 36:
        warnings.append(f"Transition of {months} months capped at 36.")
    changes: list[dict[str, Any]] = []
    itypes: list[str] = []
    default_months: list[int] = []
    for clause in _split_clauses(body):
        clause = clause.strip(" ,")
        if not clause:
            continue
        if _NEGATION.search(clause):
            groups = [g for g in _targets(clause) if g not in protected]
            if groups:
                protected += groups
                warnings.append(f"Read “{clause}” as a constraint: {', '.join(groups)} protected.")
            else:
                warnings.append(f"“{clause}” reads as a negation; no change added for it.")
            continue
        res = _parse_clause(clause, protected, warnings)
        if res is None:
            continue
        itype, chs, dm = res
        itypes.append(itype)
        default_months.append(dm)
        changes.extend(chs)
    # protected groups shouldn't also be targets
    for ch in changes:
        tg = ch.get("target")
        if isinstance(tg, list) and ch["operation"] in ("reduce_capacity", "change_budget", "change_working_hours", "deploy_ai_agents"):
            kept = [x for x in tg if x not in protected]
            if not kept:
                warnings.append(f"{ch['operation'].replace('_', ' ')}: every target is also protected — nothing will change.")
            ch["target"] = kept or tg
    if not changes:
        warnings.append("No supported change was recognised, so there is nothing to run. Try " + EXAMPLES)
    plan = validate_plan({"intervention_type": itypes[0] if itypes else "restructure", "summary": raw[:200], "objectives": [],
                          "changes": changes[:6], "protected_groups": list(dict.fromkeys(protected)),
                          "transition_period_months": min(36, months if months is not None else (max(default_months) if default_months else 1)),
                          "source": "rules", "warnings": warnings})
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
    """Guard against model drift: amounts and protected groups the rules read directly off the text win.

    Matched per operation (a stated percentage belongs to its own clause), never copied across the whole plan."""
    by_op: dict[str, list] = {}
    for rc in rules.changes:
        by_op.setdefault(rc.operation, []).append(rc)
    for ch in plan.changes:
        cands = by_op.get(ch.operation)
        if not cands or ch.amount is None:
            continue
        rc = cands.pop(0)
        if rc.amount is not None and abs(abs(ch.amount) - abs(rc.amount)) > 0.005:
            ch.amount = rc.amount
        if rc.count is not None and ch.count is None:
            ch.count = rc.count
    if rules.protected_groups and not plan.protected_groups:
        plan.protected_groups = rules.protected_groups
    plan.warnings = list(dict.fromkeys(plan.warnings + [w for w in rules.warnings if "nothing to run" not in w]))
    if not plan.summary:
        plan.summary = text.strip()[:200]
    return plan
