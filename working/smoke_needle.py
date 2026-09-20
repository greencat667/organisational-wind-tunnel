import time, json, needle
def seek_help():
    """Ask a neighbouring team with spare capacity to take some of this employee's work."""
    return "seek_help"
def work_overtime():
    """Work extra hours this month to clear the backlog personally."""
    return "work_overtime"
def delay_low_priority():
    """Postpone the lowest-priority tasks to a later month."""
    return "delay_low_priority"
def escalate_workload():
    """Raise the overload formally with the line manager and ask for a decision."""
    return "escalate_workload"
def continue_as_normal():
    """Make no change; keep working through the queue in order."""
    return "continue_as_normal"
tools=[needle.tool(f) for f in (seek_help,work_overtime,delay_low_priority,escalate_workload,continue_as_normal)]
t0=time.perf_counter(); ag=needle.Needle(tools=tools, system=None, weights=None, auto_date=False); print("needle init s", round(time.perf_counter()-t0,1))
state = open(0).read() if False else """ROLE operations officer
WORKLOAD 137% of capacity
TEAM_BACKLOG high (41 items, growing)
MANAGER_AVAILABILITY low
NEIGHBOUR finance team has spare capacity
URGENT_ITEMS 3 procurement requests waiting
STRESS 0.71 MORALE 0.52
Decide what this employee does this month."""
for i in range(3):
    t=time.perf_counter(); r=ag.complete(state, max_new_tokens=96); dt=(time.perf_counter()-t)*1000
    print(f"call {i} {dt:.0f}ms", json.dumps({k:r.get(k) for k in ('function_calls','confidence')}))
print(json.dumps(r, indent=1)[:1500])
