"""Deterministic 3D layout for the organisation: departments as districts on a ring,
teams as clusters inside their district, employees on a sunflower spiral around the team centre."""
from __future__ import annotations

import math

GOLDEN = math.pi * (3 - math.sqrt(5))


def spiral(i: int, spacing: float = 1.05) -> tuple[float, float]:
    r = spacing * math.sqrt(i + 0.5)
    a = i * GOLDEN
    return r * math.cos(a), r * math.sin(a)


def compute_layout(departments: dict, teams: dict, employees: dict) -> dict:
    """Return {"teams": {tid: (x,z,radius)}, "departments": {did: (x,z,radius)}, "employees": {eid: (x,z)}}"""
    dept_ids = list(departments.keys())
    n_d = len(dept_ids)
    total_people = max(1, len(employees))
    ring_r = 14.0 + 0.9 * math.sqrt(total_people)
    out = {"teams": {}, "departments": {}, "employees": {}}
    for di, did in enumerate(dept_ids):
        dept = departments[did]
        if dept.name == "Executive":
            dcx, dcz = 0.0, 0.0
        else:
            k = di if di < dept_ids.index(next((d for d in dept_ids if departments[d].name == "Executive"), dept_ids[0])) else di - 1
            n_ring = n_d - (1 if any(departments[d].name == "Executive" for d in dept_ids) else 0)
            ang = 2 * math.pi * k / max(1, n_ring) - math.pi / 2
            dcx, dcz = ring_r * math.cos(ang), ring_r * math.sin(ang)
        team_ids = dept.team_ids
        n_t = len(team_ids)
        team_r_est = [2.2 + 0.85 * math.sqrt(len(teams[t].member_ids)) for t in team_ids]
        cluster_r = 0.0 if n_t == 1 else max(team_r_est) * 1.15 + 1.0
        for ti, tid in enumerate(team_ids):
            if n_t == 1:
                tx, tz = dcx, dcz
            else:
                a = 2 * math.pi * ti / n_t
                tx, tz = dcx + cluster_r * math.cos(a), dcz + cluster_r * math.sin(a)
            out["teams"][tid] = (tx, tz, team_r_est[ti])
        out["departments"][did] = (dcx, dcz, cluster_r + max(team_r_est) + 1.5)
    for tid, team in teams.items():
        tx, tz, _ = out["teams"][tid]
        for i, eid in enumerate(team.member_ids):
            sx, sz = spiral(i)
            out["employees"][eid] = (tx + sx, tz + sz)
    return out


def place_new_employee(layout: dict, team_id: str, index: int) -> tuple[float, float]:
    tx, tz, _ = layout["teams"][team_id]
    sx, sz = spiral(index)
    return tx + sx, tz + sz
