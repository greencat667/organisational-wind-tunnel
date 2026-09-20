"""Tunable simulation parameters (organisational physics). All documented in docs/SIMULATION_MODEL.md."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class SimConfig:
    start_year: int = 2027
    start_month: int = 1
    monthly_hours: float = 150.0
    productive_fraction: float = 0.92          # share of contracted hours available for work items
    manager_base_hours: float = 15.0           # management hours a manager spends regardless of span
    manager_hours_per_report: float = 3.0
    approval_hours: float = 1.0                # management hours consumed per approval stage
    max_overtime_hours: float = 20.0
    overtime_cost_multiplier: float = 1.25
    recruitment_lead_months: int = 3
    recruitment_cost: float = 4000.0
    onboarding_months: int = 4
    onboarding_start_productivity: float = 0.4
    max_items_per_process_month: int = 60      # high-volume processes are bundled into batch items
    low_priority_expiry_months: int = 3        # low-priority items this long past deadline are dropped (counted as lost work)
    max_arrival_total_multiplier: float = 3.0  # safety: cap arrivals relative to calibrated demand
    # psychology
    stress_adapt: float = 0.35
    morale_adapt: float = 0.25
    memory_decay: float = 0.9
    turnover_notice_months: int = 1
    # thresholds used for triggers/events (ratios)
    overload_threshold: float = 1.15
    backlog_high_months: float = 1.0           # backlog hours / monthly capacity
    backlog_critical_months: float = 2.0
    # decisions
    periodic_decision_fraction: float = 0.08   # share of employees making a monthly periodic decision
    max_decisions_per_month: int = 60          # cap on agent evaluations per month (keeps AI engines interactive)
    confidence_execute: float = 0.75
    confidence_probabilistic: float = 0.5
    # automation
    automation_implementation_hours_per_level: float = 400.0   # team hours needed per 100% automation level
    # organisation
    target_utilisation: float = 0.75           # slack preset: lean 0.85 · normal 0.75 · slack 0.65 (admin teams run ~12% hotter)
    # AI agents (team defaults; per-team values may be overridden by change plans)
    ai_hours_per_agent: float = 120.0
    ai_monthly_cost_per_agent: float = 900.0
    ai_supervision_hours: float = 12.0
    ai_base_exception_rate: float = 0.16
    ai_silent_error_rate: float = 0.04
    ai_incident_probability: float = 0.03      # monthly P(outage/regression) per team with live agents
    ai_learning_months: float = 9.0            # exception rate decays towards 45% of base with this time constant
    ai_drift_factor: float = 0.8               # exception rate rises by this × (1 - supervision coverage)
    ai_deploy_hours_per_agent: float = 60.0    # implementation work per agent-equivalent (target team)
    ai_tech_hours_per_agent: float = 25.0      # implementation work landing on the technology team
    skill_atrophy_per_month: float = 0.012     # proficiency lost per month when AI does >=70% of a skill's routine work
    skill_atrophy_floor: float = 0.4
    verify_share: float = 0.10                 # share of capacity spent by an employee who chooses to verify AI output
    # information
    info_share_base: float = 0.35
    # external
    job_market: float = 0.5                    # 0 = no outside options, 1 = very easy to leave
    baseline_exit_hazard: float = 0.007        # monthly probability of leaving for external/life reasons (~8%/yr), scaled by turnover intention

    def to_dict(self) -> dict:
        return asdict(self)
