"""Synthetic organisation generator.

Produces a fully synthetic organisation (employees, teams, departments, processes)
from a seed. Two templates are shipped:

* ``prototype`` — ~100 employees, 8 teams (the first vertical slice)
* ``charity500`` — ~500 employees, 11 departments, ~30 teams

Arrival rates for processes are *calibrated* so that each team starts at a target
utilisation (default 0.78) — a healthy-but-not-slack baseline. Nothing here is a
claim about any real organisation.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .model import Department, Employee, Process, ProcessStage, Team

FIRST = ["Alex", "Sam", "Jordan", "Priya", "Chen", "Amara", "Luis", "Fatima", "Noah", "Zara", "Kai",
         "Maya", "Omar", "Elena", "Tariq", "Ines", "Ravi", "Sofia", "Jonah", "Leila", "Mateo", "Hana",
         "Idris", "Nadia", "Theo", "Yara", "Ezra", "Aisha", "Rowan", "Mina", "Dev", "Freya", "Kofi",
         "Lena", "Arjun", "Rosa", "Eli", "Tomasz", "Sade", "Nikhil", "Iris", "Bram", "Selin", "Owen"]
LAST = ["Morgan", "Okafor", "Lindqvist", "Nair", "Wei", "Dubois", "Haddad", "Novak", "Reyes", "Adeyemi",
        "Kowalski", "Brennan", "Sato", "Mensah", "Petrova", "Ahmed", "Fischer", "Osei", "Rahman", "Costa",
        "Byrne", "Ivanova", "Diallo", "Larsen", "Khan", "Moreau", "Singh", "Walsh", "Tanaka", "Ferreira"]

# ----------------------------------------------------------------------------
# Templates
# ----------------------------------------------------------------------------


@dataclass
class TeamTemplate:
    id: str
    name: str
    dept: str
    function: str          # frontline | admin | support | management | technology | income
    size: int
    skills: list[str]      # primary skill first
    role_title: str
    grade_range: tuple[int, int]


@dataclass
class ProcessTemplate:
    id: str
    name: str
    kind: str
    stages: list[tuple[str, str, float, bool, float]]   # (team_id, skill, hours_mean, approval, routine)
    weight: float            # relative demand weight (calibrated to utilisation later)
    origin: str | None       # team id or None (external)
    deadline_months: int
    frontline: bool
    priority_weights: tuple[float, float, float] = (0.2, 0.5, 0.3)


def prototype_template() -> tuple[list[str], list[TeamTemplate], list[ProcessTemplate]]:
    depts = ["Executive", "Finance", "Operations", "Income", "Programmes", "Technology"]
    teams = [
        TeamTemplate("exec", "Executive", "Executive", "management", 4, ["leadership", "finance"], "Director", (7, 7)),
        TeamTemplate("finance", "Finance", "Finance", "admin", 10, ["finance", "reporting"], "Finance Officer", (3, 5)),
        TeamTemplate("bizsupport", "Business Support", "Operations", "admin", 12, ["admin", "procurement", "hr"], "Administrator", (2, 4)),
        TeamTemplate("operations", "Operations", "Operations", "support", 14, ["operations", "logistics"], "Operations Officer", (3, 5)),
        TeamTemplate("fundraising", "Fundraising", "Income", "income", 14, ["fundraising", "donor_care"], "Fundraising Officer", (3, 5)),
        TeamTemplate("comms", "Communications", "Income", "income", 10, ["comms", "design"], "Communications Officer", (3, 5)),
        TeamTemplate("programmes", "Programme Delivery", "Programmes", "frontline", 24, ["programme", "delivery"], "Programme Officer", (3, 5)),
        TeamTemplate("tech", "Technology", "Technology", "technology", 12, ["tech", "data"], "Technology Analyst", (3, 5)),
    ]
    processes = [
        ProcessTemplate("procurement", "Procurement request", "procurement request",
                        [("bizsupport", "procurement", 3.0, False, 0.7), ("finance", "finance", 0.2, True, 0.3), ("finance", "finance", 1.5, False, 0.8)],
                        1.0, None, 2, False),
        ProcessTemplate("invoice", "Invoice processing", "invoice",
                        [("finance", "finance", 1.6, False, 0.85)], 1.6, None, 1, False),
        ProcessTemplate("grant", "Grant application", "grant application",
                        [("fundraising", "fundraising", 12.0, False, 0.2), ("finance", "finance", 1.0, True, 0.3),
                         ("programmes", "programme", 4.0, False, 0.2), ("fundraising", "fundraising", 3.0, False, 0.3)],
                        0.35, "fundraising", 3, True, (0.4, 0.5, 0.1)),
        ProcessTemplate("delivery", "Service delivery", "service request",
                        [("programmes", "delivery", 7.0, False, 0.25)], 3.0, None, 2, True, (0.3, 0.5, 0.2)),
        ProcessTemplate("campaign", "Campaign request", "campaign request",
                        [("comms", "comms", 6.0, False, 0.3), ("comms", "comms", 0.3, True, 0.2), ("tech", "tech", 3.0, False, 0.5), ("comms", "design", 4.0, False, 0.3)],
                        0.45, "fundraising", 2, True),
        ProcessTemplate("support", "Support request", "support request",
                        [("tech", "tech", 2.5, False, 0.6)], 1.4, None, 1, False),
        ProcessTemplate("reporting", "Management reporting", "management report",
                        [("finance", "reporting", 10.0, False, 0.5), ("exec", "leadership", 2.0, True, 0.1)], 0.25, "exec", 1, False, (0.5, 0.5, 0.0)),
        ProcessTemplate("donor", "Supporter enquiry", "supporter enquiry",
                        [("fundraising", "donor_care", 1.0, False, 0.6)], 2.4, None, 1, True),
        ProcessTemplate("logistics", "Logistics request", "logistics request",
                        [("operations", "logistics", 4.0, False, 0.5), ("bizsupport", "admin", 1.0, False, 0.8)], 1.2, "programmes", 2, False),
        ProcessTemplate("ops_delivery", "Operational delivery", "operations task",
                        [("operations", "operations", 5.0, False, 0.4)], 2.0, None, 2, True),
        ProcessTemplate("design", "Design request", "design request",
                        [("comms", "design", 3.0, False, 0.3)], 0.8, "programmes", 1, False),
        ProcessTemplate("data", "Data request", "data request",
                        [("tech", "data", 4.0, False, 0.4), ("bizsupport", "admin", 0.5, False, 0.9)], 0.6, "programmes", 2, False),
        ProcessTemplate("hr_case", "People case", "people case",
                        [("bizsupport", "hr", 4.0, False, 0.4), ("bizsupport", "hr", 0.5, True, 0.1)], 0.3, None, 2, False),
        ProcessTemplate("payroll", "Payroll & expenses", "expense claim",
                        [("bizsupport", "admin", 0.8, False, 0.9), ("finance", "finance", 0.6, False, 0.9)], 1.2, None, 1, False),
    ]
    return depts, teams, processes


def charity500_template() -> tuple[list[str], list[TeamTemplate], list[ProcessTemplate]]:
    depts = ["Executive", "Finance", "Operations", "Fundraising", "Communications", "Technology",
             "People", "Policy", "Campaigns", "Programme Delivery", "Supporter Services"]
    teams = [
        TeamTemplate("exec", "Executive", "Executive", "management", 8, ["leadership", "finance"], "Director", (7, 7)),
        TeamTemplate("finance", "Financial Accounting", "Finance", "admin", 14, ["finance", "reporting"], "Finance Officer", (3, 5)),
        TeamTemplate("fin_planning", "Planning & Analysis", "Finance", "admin", 8, ["reporting", "finance"], "Finance Analyst", (4, 5)),
        TeamTemplate("procurement", "Procurement", "Operations", "admin", 10, ["procurement", "admin"], "Procurement Officer", (3, 4)),
        TeamTemplate("facilities", "Facilities & Admin", "Operations", "admin", 16, ["admin", "logistics"], "Administrator", (2, 4)),
        TeamTemplate("operations", "Operations", "Operations", "support", 22, ["operations", "logistics"], "Operations Officer", (3, 5)),
        TeamTemplate("indiv_giving", "Individual Giving", "Fundraising", "income", 22, ["fundraising", "donor_care"], "Fundraising Officer", (3, 5)),
        TeamTemplate("major_gifts", "Philanthropy & Trusts", "Fundraising", "income", 14, ["fundraising", "finance"], "Philanthropy Manager", (4, 6)),
        TeamTemplate("legacies", "Legacies & Events", "Fundraising", "income", 12, ["fundraising", "donor_care"], "Events Officer", (3, 5)),
        TeamTemplate("comms", "Media & Content", "Communications", "income", 18, ["comms", "design"], "Communications Officer", (3, 5)),
        TeamTemplate("digital", "Digital", "Communications", "income", 14, ["design", "tech"], "Digital Producer", (3, 5)),
        TeamTemplate("brand", "Brand & Creative", "Communications", "income", 8, ["design", "comms"], "Designer", (3, 5)),
        TeamTemplate("tech", "Technology Services", "Technology", "technology", 18, ["tech", "data"], "Technology Analyst", (3, 5)),
        TeamTemplate("data", "Data & Insight", "Technology", "technology", 12, ["data", "reporting"], "Data Analyst", (3, 5)),
        TeamTemplate("crm", "CRM & Systems", "Technology", "technology", 10, ["tech", "donor_care"], "Systems Analyst", (3, 5)),
        TeamTemplate("hr", "People Partnering", "People", "admin", 12, ["hr", "admin"], "People Partner", (3, 5)),
        TeamTemplate("recruitment", "Recruitment & L&D", "People", "admin", 10, ["hr", "admin"], "Recruitment Officer", (3, 4)),
        TeamTemplate("policy", "Policy & Research", "Policy", "frontline", 16, ["policy", "programme"], "Policy Officer", (3, 5)),
        TeamTemplate("legal", "Legal & Governance", "Policy", "admin", 8, ["legal", "policy"], "Legal Adviser", (4, 6)),
        TeamTemplate("campaigns", "Campaigns", "Campaigns", "frontline", 20, ["campaigning", "comms"], "Campaigner", (3, 5)),
        TeamTemplate("mobilisation", "Community Mobilisation", "Campaigns", "frontline", 16, ["campaigning", "delivery"], "Community Organiser", (3, 4)),
        TeamTemplate("prog_north", "Programmes North", "Programme Delivery", "frontline", 34, ["programme", "delivery"], "Programme Officer", (3, 5)),
        TeamTemplate("prog_south", "Programmes South", "Programme Delivery", "frontline", 34, ["programme", "delivery"], "Programme Officer", (3, 5)),
        TeamTemplate("prog_intl", "International Programmes", "Programme Delivery", "frontline", 28, ["programme", "finance"], "Programme Manager", (4, 6)),
        TeamTemplate("prog_pmo", "Programme Office", "Programme Delivery", "admin", 12, ["admin", "reporting"], "Programme Coordinator", (2, 4)),
        TeamTemplate("supporter", "Supporter Care", "Supporter Services", "frontline", 30, ["donor_care", "admin"], "Supporter Care Adviser", (2, 3)),
        TeamTemplate("complaints", "Complaints & Quality", "Supporter Services", "support", 8, ["donor_care", "legal"], "Quality Officer", (3, 4)),
    ]
    processes = [
        ProcessTemplate("procurement", "Procurement request", "procurement request",
                        [("procurement", "procurement", 3.0, False, 0.7), ("finance", "finance", 0.2, True, 0.3), ("finance", "finance", 1.5, False, 0.8)], 1.0, None, 2, False),
        ProcessTemplate("invoice", "Invoice processing", "invoice", [("finance", "finance", 1.6, False, 0.85)], 1.8, None, 1, False),
        ProcessTemplate("grant", "Grant application", "grant application",
                        [("major_gifts", "fundraising", 12.0, False, 0.2), ("fin_planning", "finance", 1.0, True, 0.3), ("prog_north", "programme", 4.0, False, 0.2), ("major_gifts", "fundraising", 3.0, False, 0.3)],
                        0.35, "major_gifts", 3, True, (0.4, 0.5, 0.1)),
        ProcessTemplate("grant_intl", "International grant", "grant application",
                        [("prog_intl", "programme", 10.0, False, 0.2), ("fin_planning", "finance", 1.0, True, 0.3), ("legal", "legal", 2.0, False, 0.2), ("prog_intl", "finance", 3.0, False, 0.3)],
                        0.3, "prog_intl", 3, True, (0.4, 0.5, 0.1)),
        ProcessTemplate("delivery_n", "Service delivery (North)", "service request", [("prog_north", "delivery", 7.0, False, 0.25)], 3.0, None, 2, True, (0.3, 0.5, 0.2)),
        ProcessTemplate("delivery_s", "Service delivery (South)", "service request", [("prog_south", "delivery", 7.0, False, 0.25)], 3.0, None, 2, True, (0.3, 0.5, 0.2)),
        ProcessTemplate("delivery_i", "International delivery", "programme milestone", [("prog_intl", "programme", 9.0, False, 0.2), ("prog_pmo", "reporting", 1.5, False, 0.7)], 2.0, None, 2, True),
        ProcessTemplate("campaign", "Campaign request", "campaign request",
                        [("campaigns", "campaigning", 6.0, False, 0.3), ("comms", "comms", 0.3, True, 0.2), ("digital", "tech", 3.0, False, 0.5), ("brand", "design", 4.0, False, 0.3)], 0.6, "campaigns", 2, True),
        ProcessTemplate("mobilise", "Community action", "community action", [("mobilisation", "campaigning", 5.0, False, 0.3), ("comms", "comms", 1.5, False, 0.4)], 1.2, None, 2, True),
        ProcessTemplate("support", "Support request", "support request", [("tech", "tech", 2.5, False, 0.6)], 1.6, None, 1, False),
        ProcessTemplate("crm_change", "CRM change", "system change", [("crm", "tech", 5.0, False, 0.4), ("data", "data", 2.0, False, 0.5)], 0.5, "indiv_giving", 2, False),
        ProcessTemplate("reporting", "Management reporting", "management report", [("fin_planning", "reporting", 8.0, False, 0.5), ("exec", "leadership", 2.0, True, 0.1)], 0.3, "exec", 1, False, (0.5, 0.5, 0.0)),
        ProcessTemplate("donor", "Supporter enquiry", "supporter enquiry", [("supporter", "donor_care", 1.0, False, 0.6)], 3.0, None, 1, True),
        ProcessTemplate("complaint", "Complaint", "complaint", [("supporter", "donor_care", 1.5, False, 0.4), ("complaints", "donor_care", 3.0, False, 0.3)], 0.5, None, 1, True, (0.5, 0.4, 0.1)),
        ProcessTemplate("appeal", "Fundraising appeal", "appeal", [("indiv_giving", "fundraising", 8.0, False, 0.3), ("brand", "design", 3.0, False, 0.3), ("digital", "design", 3.0, False, 0.4), ("supporter", "donor_care", 2.0, False, 0.6)], 0.7, "indiv_giving", 2, True),
        ProcessTemplate("event", "Event", "event", [("legacies", "fundraising", 9.0, False, 0.3), ("facilities", "logistics", 3.0, False, 0.6)], 0.5, "legacies", 2, True),
        ProcessTemplate("logistics", "Logistics request", "logistics request", [("operations", "logistics", 4.0, False, 0.5), ("facilities", "admin", 1.0, False, 0.8)], 1.3, "prog_north", 2, False),
        ProcessTemplate("ops_delivery", "Operational delivery", "operations task", [("operations", "operations", 5.0, False, 0.4)], 2.0, None, 2, True),
        ProcessTemplate("policy_brief", "Policy briefing", "policy briefing", [("policy", "policy", 8.0, False, 0.2), ("legal", "legal", 0.5, True, 0.1), ("comms", "comms", 2.0, False, 0.4)], 0.6, "policy", 2, True),
        ProcessTemplate("legal_review", "Legal approval", "legal approval", [("legal", "legal", 3.0, False, 0.3)], 0.6, "campaigns", 1, False, (0.4, 0.5, 0.1)),
        ProcessTemplate("data_req", "Data request", "data request", [("data", "data", 4.0, False, 0.4), ("prog_pmo", "admin", 0.5, False, 0.9)], 0.7, "prog_south", 2, False),
        ProcessTemplate("hr_case", "People case", "people case", [("hr", "hr", 4.0, False, 0.4), ("hr", "hr", 0.5, True, 0.1)], 0.5, None, 2, False),
        ProcessTemplate("payroll", "Payroll & expenses", "expense claim", [("facilities", "admin", 0.8, False, 0.9), ("finance", "finance", 0.6, False, 0.9)], 1.5, None, 1, False),
        ProcessTemplate("pmo_report", "Programme report", "programme report", [("prog_pmo", "reporting", 3.0, False, 0.6), ("fin_planning", "finance", 1.0, False, 0.6)], 1.0, "prog_south", 1, False),
    ]
    return depts, teams, processes


TEMPLATES = {"prototype": prototype_template, "charity500": charity500_template}

# ----------------------------------------------------------------------------
# Generation
# ----------------------------------------------------------------------------

CALIBRATION_BOUNDS = (0.5, 2.0)  # per-process calibration may scale a rate at most this much around the global level
GRADE_SALARY = {1: 22000, 2: 26000, 3: 31000, 4: 37000, 5: 45000, 6: 56000, 7: 78000}
MONTHLY_HOURS = 150.0
ARCHETYPES = ["steady", "helper", "escalator", "self_reliant", "cautious", "mobile"]


def _trait(rng: random.Random, centre: float, spread: float = 0.18) -> float:
    return min(0.95, max(0.05, rng.gauss(centre, spread)))


def _archetype_traits(rng: random.Random, arche: str) -> dict[str, float]:
    base = dict(change_tolerance=0.5, risk_tolerance=0.5, collaboration_tendency=0.5,
                escalation_tendency=0.5, autonomy=0.5, institutional_knowledge=0.5, adaptability=0.5)
    shift = {
        "steady": {},
        "helper": {"collaboration_tendency": 0.75, "escalation_tendency": 0.4},
        "escalator": {"escalation_tendency": 0.78, "autonomy": 0.4},
        "self_reliant": {"autonomy": 0.75, "collaboration_tendency": 0.35, "risk_tolerance": 0.6},
        "cautious": {"risk_tolerance": 0.3, "change_tolerance": 0.35},
        "mobile": {"change_tolerance": 0.65, "adaptability": 0.7, "institutional_knowledge": 0.35},
    }[arche]
    base.update(shift)
    return {k: _trait(rng, v) for k, v in base.items()}


def generate_organisation(template: str = "prototype", seed: int = 7, scale: float = 1.0,
                          target_utilisation: float = 0.75):
    """Return (departments, teams, employees, processes) — all plain dataclasses."""
    rng = random.Random(seed * 7919 + 17)
    dept_names, team_templates, process_templates = TEMPLATES[template]()
    if template == "charity500" and scale == 1.0:
        scale = 1.15   # template sizes sum to ~434; 1.15 gives ~500

    departments: dict[str, Department] = {}
    for d in dept_names:
        did = d.lower().replace(" ", "_").replace("&", "and")
        departments[did] = Department(id=did, name=d, team_ids=[], budget_annual=0.0)

    teams: dict[str, Team] = {}
    employees: dict[str, Employee] = {}
    counter = 0
    used_names: set[str] = set()

    def new_name() -> str:
        for _ in range(50):
            n = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if n not in used_names:
                used_names.add(n)
                return n
        return f"Employee {counter}"

    exec_team_id = None
    for tt in team_templates:
        did = tt.dept.lower().replace(" ", "_").replace("&", "and")
        size = max(2, round(tt.size * scale))
        team = Team(id=tt.id, name=tt.name, dept_id=did, function=tt.function, manager_id=None,
                    member_ids=[], skills_provided=list(tt.skills), budget_annual=0.0,
                    autonomy=0.6 if tt.function == "frontline" else 0.4)
        if tt.function == "management":
            exec_team_id = tt.id
        departments[did].team_ids.append(tt.id)
        for i in range(size):
            counter += 1
            eid = f"E{counter:04d}"
            is_manager = (i == 0)
            grade = tt.grade_range[1] + 1 if is_manager else rng.randint(*tt.grade_range)
            grade = min(7, grade)
            arche = rng.choice(ARCHETYPES)
            traits = _archetype_traits(rng, arche)
            primary = tt.skills[0]
            skills = {primary: round(rng.uniform(0.6, 0.95), 2)}
            for s in tt.skills[1:]:
                skills[s] = round(rng.uniform(0.35, 0.75), 2)
            # a smattering of cross-functional secondary skills
            if rng.random() < 0.35:
                other = rng.choice(["admin", "finance", "comms", "tech", "programme", "operations", "hr", "data"])
                skills.setdefault(other, round(rng.uniform(0.2, 0.5), 2))
            if is_manager:
                skills["management"] = round(rng.uniform(0.5, 0.9), 2)
            exp = rng.randint(6, 180)
            emp = Employee(
                id=eid, name=new_name(), role=f"{tt.id}_{'manager' if is_manager else 'officer'}",
                role_title=(f"{tt.name} Manager" if is_manager and tt.function != "management" else tt.role_title),
                team_id=tt.id, dept_id=did, grade=grade, salary=GRADE_SALARY[grade] * rng.uniform(0.95, 1.08),
                contracted_hours=MONTHLY_HOURS * (1.0 if rng.random() > 0.15 else 0.6),
                skills=skills, experience_months=exp, is_manager=is_manager, archetype=arche,
                stress=_trait(rng, 0.22, 0.08), morale=_trait(rng, 0.7, 0.1), engagement=_trait(rng, 0.68, 0.1),
                influence=_trait(rng, 0.55 if is_manager else 0.3, 0.12), trust_management=_trait(rng, 0.62, 0.12),
                commitment=_trait(rng, 0.62, 0.12), absence_probability=round(rng.uniform(0.02, 0.05), 3),
                turnover_intention=_trait(rng, 0.08, 0.04), **traits,
            )
            emp.institutional_knowledge = min(0.95, emp.institutional_knowledge * 0.5 + min(1.0, exp / 120) * 0.5)
            employees[eid] = emp
            team.member_ids.append(eid)
            if is_manager:
                team.manager_id = eid
        team.baseline_headcount = len(team.member_ids)
        teams[tt.id] = team

    # reporting lines: officers -> team manager; team managers -> a director in exec; directors -> CEO
    exec_team = teams[exec_team_id]
    directors = [employees[e] for e in exec_team.member_ids]
    ceo = directors[0]
    ceo.role_title = "Chief Executive"
    for i, d in enumerate(directors[1:]):
        d.role_title = "Director"
        d.is_manager = True
        d.manager_id = ceo.id
        d.skills["management"] = round(rng.uniform(0.6, 0.9), 2)
    dept_list = [d for d in departments.values() if d.id != exec_team.dept_id]
    for i, dept in enumerate(dept_list):
        director = directors[1 + i % max(1, len(directors) - 1)] if len(directors) > 1 else ceo
        dept.head_id = director.id
        for tid in dept.team_ids:
            t = teams[tid]
            for eid in t.member_ids:
                e = employees[eid]
                e.manager_id = t.manager_id if eid != t.manager_id else director.id
    # exec dept
    departments[exec_team.dept_id].head_id = ceo.id
    exec_team.manager_id = ceo.id

    # informal relationships: within team (dense), across teams that share a process (sparse)
    for t in teams.values():
        for a in t.member_ids:
            for b in t.member_ids:
                if a < b and rng.random() < 0.45:
                    w = round(rng.uniform(0.3, 0.8), 2)
                    employees[a].relationships[b] = w
                    employees[b].relationships[a] = w

    # processes
    processes: dict[str, Process] = {}
    for pt in process_templates:
        stages = []
        for k, (tid, skill, hours, approval, routine) in enumerate(pt.stages):
            stages.append(ProcessStage(id=f"{pt.id}_s{k}", team_id=tid, skill=skill, hours_mean=hours,
                                       hours_sd=hours * 0.3, approval=approval, routine=routine))
        processes[pt.id] = Process(id=pt.id, name=pt.name, kind=pt.kind, stages=stages, arrival_rate=pt.weight,
                                   origin_team_id=pt.origin, deadline_months=pt.deadline_months,
                                   priority_weights=pt.priority_weights, frontline=pt.frontline)
        # cross-team informal ties along process paths
        path_teams = [s.team_id for s in stages]
        for a_t, b_t in zip(path_teams, path_teams[1:]):
            if a_t == b_t:
                continue
            for _ in range(max(1, round(2 * scale))):
                a = rng.choice(teams[a_t].member_ids)
                b = rng.choice(teams[b_t].member_ids)
                w = round(rng.uniform(0.2, 0.5), 2)
                employees[a].relationships[b] = max(employees[a].relationships.get(b, 0), w)
                employees[b].relationships[a] = max(employees[b].relationships.get(a, 0), w)

    calibrate_arrivals(teams, employees, processes, target_utilisation)

    # budgets: salaries + 18% non-pay, per team and department
    for t in teams.values():
        pay = sum(employees[e].salary for e in t.member_ids)
        t.budget_annual = round(pay * 1.18, 0)
        departments[t.dept_id].budget_annual += t.budget_annual
    return departments, teams, employees, processes


def productive_hours(emp: Employee, team_size: int) -> float:
    """Hours available for work items per month (before stress/morale effects)."""
    h = emp.contracted_hours
    if emp.is_manager:
        h -= min(h * 0.8, 15.0 + 3.0 * max(0, team_size - 1))
    elif emp.grade >= 5:
        h -= 8.0   # senior officers approve routine items
    return max(0.0, h)


FUNCTION_UTILISATION = {"admin": 0.84, "support": 0.76, "income": 0.74, "frontline": 0.74, "technology": 0.74, "management": 0.6}


def calibrate_arrivals(teams, employees, processes, target: float, iterations: int = 12) -> None:
    """Scale process arrival rates so the busiest team touched by each process sits near its function's target utilisation
    (back-office/admin teams are calibrated hotter than frontline teams — see docs/SIMULATION_MODEL.md)."""
    cap = {t.id: sum(productive_hours(employees[e], len(t.member_ids)) for e in t.member_ids) * 0.92 for t in teams.values()}
    tgt = {t.id: FUNCTION_UTILISATION.get(t.function, target) * (target / 0.75) for t in teams.values()}
    # 1) global level: scale all weights by one factor so total demand hours = target * total capacity
    total_cap = sum(cap.values())
    hours_per_weight = sum(p.arrival_rate * s.hours_mean for p in processes.values() for s in p.stages if not s.approval)
    g = (target * total_cap) / max(1e-6, hours_per_weight)
    for p in processes.values():
        p.arrival_rate *= g
    base = {p.id: p.arrival_rate for p in processes.values()}
    lo, hi = CALIBRATION_BOUNDS
    # 2) per-process: nudge towards the target for the busiest team each touches, within bounds
    for _ in range(iterations):
        demand = {tid: 0.0 for tid in teams}
        for p in processes.values():
            for s in p.stages:
                if not s.approval:
                    demand[s.team_id] += p.arrival_rate * s.hours_mean
        for p in processes.values():
            ratios = [(demand[s.team_id] / max(1.0, cap[s.team_id])) / tgt[s.team_id] for s in p.stages if not s.approval]
            if not ratios:
                continue
            u = max(ratios)
            if u <= 0:
                continue
            p.arrival_rate = min(base[p.id] * hi, max(base[p.id] * lo, p.arrival_rate * (1.0 / u) ** 0.6))
    for p in processes.values():
        p.arrival_rate = round(max(0.5, p.arrival_rate), 2)
