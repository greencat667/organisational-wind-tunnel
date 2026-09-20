import time, json
t0=time.perf_counter()
import laya
agent = laya.load("convaiinnovations/laya")
print("laya load s", round(time.perf_counter()-t0,1), "device", agent.device)
state = """ROLE operations officer
TEAM operations
WORKLOAD 137% of capacity
TEAM_BACKLOG high (41 items, growing)
MANAGER_AVAILABILITY low
RECENT_CHANGE admin team reduced by 20% two months ago
URGENT_ITEMS 3 procurement requests waiting
NEIGHBOUR finance team has spare capacity
TRUST_IN_MANAGEMENT moderate
STRESS 0.71
MORALE 0.52"""
qs = {
 "seek_help": {"type":"noul","instructions":"Should this employee ask a neighbouring team for help with their workload?"},
 "work_overtime": {"type":"noul","instructions":"Should this employee work extra unpaid hours this month?"},
 "delay_low_priority": {"type":"noul","instructions":"Should this employee deliberately delay low-priority tasks?"},
 "escalate_workload": {"type":"noul","instructions":"Should this employee escalate their workload problem to their manager?"},
 "use_workaround": {"type":"noul","instructions":"Should this employee bypass the normal approval process to get work done faster?"},
 "collab_target": {"type":"choice","instructions":"Which team should this employee turn to for help?","criteria":{"own_team":"colleagues in the same team","finance":"the finance team, which has spare capacity","procurement":"the procurement team","manager":"their line manager","none":"nobody"}},
 "effort": {"type":"score","instructions":"How much effort will this employee put in this month?","criteria":["minimal","reduced","normal","high","maximum"]},
 "turnover_pressure": {"type":"score","instructions":"How strong is this employee's pressure to leave the organisation?","criteria":["none","low","moderate","high","very high"]},
}
for i in range(3):
    t=time.perf_counter(); r=agent.predict(state, qs); dt=(time.perf_counter()-t)*1000
    print(f"call {i} {dt:.0f}ms")
print(json.dumps(r, indent=1)[:2500])
