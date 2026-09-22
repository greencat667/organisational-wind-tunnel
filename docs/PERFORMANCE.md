# Performance and scale

Four O(n²)-in-population bottlenecks were found and fixed in one investigation, each surfaced by
profiling or by batch-testing at 10,000+ simulated employees rather than by inspection — none was
visible at the 100–500-person scale the templates ship at. In order: the original design proposal
for the `_allocate()` fix below (kept as the historical record, including the review questions it
was written to answer), then three shorter write-ups — `_process_work` plus the causal-event
lookup, the informal-relationship graph, and the work-item transfer cap.

---

# Proposal: fix the O(n²) work-allocation bottleneck in `_allocate()`

**Repo:** `organisational-wind-tunnel` (private), file `backend/windtunnel/engine.py`
**Status:** implemented, commit `d962f25`. Verification plan (section 5) run in full: 3,622
captured (team, items, members) snapshots across both templates and five seeds gave
byte-for-byte identical results old vs new; 36-month same-seed runs stayed deterministic;
`_allocate`'s share of a month's time at 2,000 employees fell from ~55% to ~13%
(cProfile); wall-clock at 10,000 employees fell from ~67s/month to ~6.5s/month — a real
improvement, short of the hoped-for near-linear scaling because `_process_work` and
`_psychology` are now the dominant cost at scale instead (a separate, unaddressed
bottleneck). One correctness bug was caught and fixed during implementation: a new
skill's heap must be seeded with each worker's *current* load ratio, not `0.0` — a worker
can already carry load from a different skill processed earlier in the same call, and a
`0.0` seed would be permanently stale (ratios only increase) and could empty the heap.
**Author's context:** this is a personal simulation project. The org size that can be
simulated is currently capped well below what the hardware could support, purely by an
algorithmic bottleneck in the core monthly work-allocation loop. This document proposes
a fix and asks a reviewer to sanity-check both the diagnosis and the proposed approach
before it's implemented, because the code in question directly determines simulation
outcomes (who does what work, who gets overloaded) and the project has existing
determinism tests that must keep passing bit-for-bit.

---

## 1. The problem, with evidence

The simulation advances one calendar month at a time (`World.step()`). Each month, for
every team, `_update_team_aggregates()` calls `_allocate()` to decide which employee
does which piece of queued work.

Benchmarked on the actual codebase (Apple Silicon Mac, single-threaded, the `heuristic`
decision engine):

| Employees (8 fixed teams) | Time per simulated month (steady state) |
|---|---|
| 100 | ~12ms |
| 500 | ~46ms |
| 2,000 | ~500-600ms |
| 5,000 | ~1.4-3.2s |
| 10,000 | ~67 **seconds** |

That's roughly quadratic, not linear, in employee count. `cProfile` on a single month at
2,000 employees confirms exactly where:

```
9,739,483 function calls in 1.167 seconds

ncalls     tottime  cumtime  function
1          0.001    1.167    engine.py:266(step)
11         0.014    0.769    engine.py:592(_allocate)
27696      0.170    0.642    {built-in method builtins.min}
3060536    0.405    0.472    engine.py:623(<lambda>)   <-- the min() key function
5631287    0.126    0.126    {method 'get' of 'dict' objects}
```

**3.06 million evaluations of one `min()` key lambda, in a single simulated month, for a
2,000-person organisation.** That line is the actual bottleneck. (An earlier hypothesis —
that `active_members()` was the culprit — was wrong; it was measured at only 199 calls/month
for the same run. That fix has already been applied since it's harmless and arguably
correct hygiene, but it made no measurable difference, which is what prompted profiling
instead of continuing to guess.)

---

## 2. The current algorithm (must be preserved exactly)

`backend/windtunnel/engine.py`, `_allocate()`:

```python
def _allocate(self, t: Team, items: list[WorkItem], members: list[Employee], balance: bool = False) -> None:
    workers = [m for m in members if m.capacity_hours > 0 and m.absent_fraction < 1.0]
    for m in members:
        m.assigned_hours = 0.0
        m.active_tasks = []
    if not workers:
        for m in members:
            m.workload = 1.5 if items else 0.0
        return
    load = {m.id: 0.0 for m in workers}
    cap = {m.id: max(1.0, m.capacity_hours) for m in workers}
    by_id = {m.id: m for m in workers}
    approvals = 0.0
    for w in sorted(items, key=lambda w: (w.priority, w.created_month, w.id)):
        stage = self.processes[w.process_id].stages[w.stage_index]
        if stage.approval:
            approvals += stage.hours_mean
            continue
        skilled = [m for m in workers if m.skills.get(stage.skill, 0.0) >= 0.2]
        if not skilled:
            continue
        keep = by_id.get(w.assignee_id) if (w.assignee_id and not balance and w.status == "in_progress") else None
        remaining = w.remaining_hours
        first = True
        while remaining > 0.01:
            if first and keep is not None and keep.skills.get(stage.skill, 0.0) >= 0.2:
                m = keep
            else:
                m = min(skilled, key=lambda m: (load[m.id] / cap[m.id], -m.skills.get(stage.skill, 0.0), m.id))
            rate = 0.55 + 0.45 * m.skills.get(stage.skill, 0.2)
            chunk = min(remaining, max(4.0, 0.35 * cap[m.id] * rate))
            load[m.id] += chunk / rate
            remaining -= chunk
            if first:
                w.assignee_id = m.id
                first = False
            if w.id not in m.active_tasks:
                m.active_tasks.append(w.id)
    for m in workers:
        m.assigned_hours = load[m.id]
        m.workload = load[m.id] / cap[m.id]
    for m in members:
        if m.id not in load:
            m.workload = 0.0
```

Semantics that any replacement **must** reproduce exactly, for existing seeds/tests to
keep passing and for the change to be behaviour-neutral:

1. **Item order is fixed and sequential**: items processed in `(priority, created_month,
   id)` order. Later items' assignment decisions depend on load left behind by earlier
   items in the *same* call — this is inherently a sequential greedy process, not
   parallelisable or reorderable.
2. **`skilled` is per-item**, not global: it's the subset of `workers` on team `t` whose
   `skills[stage.skill] >= 0.2`, and `stage.skill` varies from item to item.
3. **Sticky first chunk**: if the item was already `in_progress`, has an existing
   `assignee_id`, and we're not in `balance` mode, the *first* chunk goes to that same
   person (if they still qualify) — bypassing the "pick the minimum" step entirely for
   that one chunk.
4. **Every other chunk** (including the 2nd+ chunk of a sticky item) picks
   `min(skilled, key=(load_ratio, -skill_level, id))` — least-loaded-by-ratio first, ties
   broken by higher skill level, then by employee id (for determinism).
5. **A single item can be split into many chunks**, each potentially going to a
   *different* person, because `load` changes after every chunk and the next chunk's
   minimum can shift. Chunk size is `min(remaining, max(4.0, 0.35 * cap[m] * rate))`,
   where `rate` depends on the *chosen* worker's skill level.
6. `load[m.id]` accumulates `chunk / rate` (skill-adjusted effort hours), not raw chunk
   hours.

The reason this is expensive: for every chunk (and large items can be dozens of chunks),
`min()` does a fresh **O(|skilled|)** linear scan, and `|skilled|` grows with team size.
Both the number of items and the team size scale with population, so total cost is
`O(items × chunks_per_item × team_size)` per team per month — quadratic-ish in
population.

---

## 3. Proposed fix: a lazy-deletion priority queue per skill

Idea: instead of rescanning `skilled` from scratch for every chunk, maintain a min-heap
per distinct `stage.skill` value encountered this call, keyed by the same
`(load_ratio, -skill_level, id)` tuple used today. Use the standard **lazy-deletion**
pattern (heap entries can go stale; verify against a source-of-truth dict on pop rather
than trying to decrease-key in place, which `heapq` doesn't support directly):

```python
import heapq

def _allocate(self, t, items, members, balance=False):
    workers = [...]                    # unchanged
    load = {...}; cap = {...}; by_id = {...}   # unchanged

    heaps: dict[str, list] = {}         # skill -> heap of (ratio, -skill_lvl, id)
    skill_pool: dict[str, list[Employee]] = {}  # skill -> workers[] with that skill (built once)

    def pool_for(skill):
        p = skill_pool.get(skill)
        if p is None:
            p = [m for m in workers if m.skills.get(skill, 0.0) >= 0.2]
            skill_pool[skill] = p
            heaps[skill] = [(0.0, -m.skills.get(skill, 0.0), m.id) for m in p]
            heapq.heapify(heaps[skill])
        return p

    def pop_min(skill):
        heap = heaps[skill]
        while heap:
            ratio, neg_skill, mid = heap[0]
            if ratio == load[mid] / cap[mid]:      # still valid — nothing changed it since push
                return by_id[mid]
            heapq.heappop(heap)                     # stale — someone else's update superseded this entry
        return None   # shouldn't happen if pool_for(skill) is non-empty

    def bump(m, changed_skill_hint=None):
        """After m's load changes, refresh its entry in every skill-heap it belongs to,
        so a stale (too-high) entry elsewhere doesn't make it look permanently 'busy'."""
        ratio = load[m.id] / cap[m.id]
        for skill, pool in skill_pool.items():
            if m in pool:  # or track membership by id in a set per skill to avoid O(pool) here
                heapq.heappush(heaps[skill], (ratio, -m.skills.get(skill, 0.0), m.id))

    for w in sorted(items, key=lambda w: (w.priority, w.created_month, w.id)):
        stage = self.processes[w.process_id].stages[w.stage_index]
        if stage.approval:
            approvals += stage.hours_mean
            continue
        skilled = pool_for(stage.skill)
        if not skilled:
            continue
        keep = by_id.get(w.assignee_id) if (w.assignee_id and not balance and w.status == "in_progress") else None
        remaining = w.remaining_hours
        first = True
        while remaining > 0.01:
            if first and keep is not None and keep.skills.get(stage.skill, 0.0) >= 0.2:
                m = keep
            else:
                m = pop_min(stage.skill)
            rate = 0.55 + 0.45 * m.skills.get(stage.skill, 0.2)
            chunk = min(remaining, max(4.0, 0.35 * cap[m.id] * rate))
            load[m.id] += chunk / rate
            bump(m)                      # <-- refresh m's entry in every skill-heap it's in
            remaining -= chunk
            if first:
                w.assignee_id = m.id
                first = False
            if w.id not in m.active_tasks:
                m.active_tasks.append(w.id)
    # tail unchanged
```

**Why the `bump()` step matters and can't be skipped:** a worker can qualify for more
than one skill (`skills_provided` can list several skills per team). If worker `m` gets a
chunk via the `finance` skill-heap, their entry in the `admin` skill-heap (if they're also
`admin`-skilled and that heap already exists) is now stale — but if we only ever push a
fresh entry into the heap we *popped from*, the `admin` heap's only reference to `m` may
get discarded as stale later and never replaced, silently removing `m` from
consideration for `admin` work even though they might be the lightest-loaded person left.
The proposal pushes a fresh entry into **every** skill-pool `m` belongs to on every load
change, not just the one just used. Since the number of distinct skills in the system is
small and fixed (a handful, from `orggen.py`'s `skills_provided`), this is a small
constant-factor cost, not a new scaling problem — but it's the detail most likely to be
wrong in a first draft, and the one I'd most want a second pair of eyes on.

**Complexity:** old = `O(items × chunks_per_item × team_size)`. New =
`O((team_size + items × chunks_per_item × skills_per_worker) × log(team_size))` — the
expensive linear scan becomes a log-time heap operation, at the cost of a small constant
factor for the multi-skill refresh. For the profiled case (2,000 employees, 3.06M
`min()` evaluations against pools that can run into the hundreds), this should turn
~3 million O(team_size) scans into ~3 million O(log(team_size)) heap operations — the
kind of change that should take the 2,000-employee case from ~500ms/month toward the
15-40ms/month range, and make 10,000 employees plausible instead of a 67-second/month
wall. (This is an order-of-magnitude expectation from the complexity change, not a
verified number — see the verification plan below.)

**Secondary, lower-risk optimisation worth doing at the same time:** `skilled = [m for m
in workers if m.skills.get(stage.skill, 0.0) >= 0.2]` (line 613) is recomputed by a full
scan of `workers` **once per item** (not per chunk) — cheaper than the main bottleneck
(110ms of the 1.17s profiled second) but still `O(items × team_size)` for no reason,
since `workers`' skills don't change during `_allocate`. The `pool_for()` memoisation
above already fixes this as a side effect (each skill's pool is built once, not once per
item).

---

## 4. Correctness risks — please check these specifically

1. **Float equality staleness check** (`ratio == load[mid] / cap[mid]`). This relies on
   re-deriving the exact same float from the exact same inputs producing a bit-identical
   value, which is true in Python for deterministic arithmetic on unchanged operands —
   but I'd like a second opinion on whether there's any path where this could produce a
   false negative (treating a still-valid entry as stale, which only costs a wasted
   recompute — safe) vs. a **false positive** (treating a stale entry as valid, which
   would be an actual correctness bug — e.g. if `load[mid]` could ever be mutated and then
   restored to exactly its old value between push and pop, which I don't believe happens
   here but haven't exhaustively proven).
2. **The `bump()` "push to every skill-pool the worker belongs to" step** — is checking
   `if m in pool` (a list) the right membership test, and should it instead be a
   precomputed `set` of ids per skill for O(1) membership instead of O(pool) (which would
   silently reintroduce an O(team_size) term inside `bump()`, called once per chunk —
   this needs to be O(skills_per_worker), not O(team_size), or the fix doesn't actually
   fix the complexity)?
3. **The `keep` (sticky assignee) path bypasses the heap** for the first chunk of an
   in-progress item. `bump()` is still called after that chunk (since it's outside the
   if/else), so `keep`'s updated load should propagate correctly — but this is exactly
   the kind of edge case worth a fresh read rather than trusting the author's own check.
4. **Tie-breaking determinism**: the existing tie-break is `(-skill_level, id)` after
   load ratio. The heap tuples preserve this ordering identically, but please confirm
   `heapq`'s tuple comparison gives the same total order as the original `min(key=...)`
   for ties (it should — same tuple, same comparison semantics — but worth a second look).
5. Is there a **simpler** approach that gets most of the win with less risk? E.g., not
   maintaining a live heap at all, but re-sorting `skilled` less frequently (say, once
   every K chunks rather than every chunk) as an approximation — this would be simpler
   but would *change* which worker gets which chunk in some cases (a real behaviour
   change, not just a speed-up), so I've ruled it out, but flagging in case there's a
   correctness-preserving middle ground I'm missing.

---

## 5. Verification plan (before this is considered done)

1. **Existing suite**: `.venv/bin/python -m pytest -q tests` (51 tests, includes
   determinism, capacity arithmetic, causality) must still pass unchanged.
2. **Shadow-run equivalence check** (new, not yet written): run the *old* and *new*
   `_allocate()` against identical `(team, items, members)` snapshots across a range of
   scenarios (small/large teams, ties in load ratio, multi-skill items, sticky
   in-progress items, teams with zero capacity), and assert byte-for-byte identical
   results: same `assignee_id` per item, same `active_tasks` per employee, same
   `assigned_hours`/`workload` values (exact float equality, since both algorithms do the
   same arithmetic — only the *search* method for the minimum changes).
3. **End-to-end determinism**: run a full multi-year simulation twice with the same seed
   before and after the change and diff the exported event log / metrics history —
   should be identical.
4. **Re-run the benchmark** at 100 / 500 / 2,000 / 5,000 / 10,000 employees and confirm
   the complexity class actually changed (not just a constant-factor improvement) —
   i.e., time-per-month should grow roughly linearly with employee count afterward, not
   quadratically.

---

## 6. What I'd like the reviewer to actually do

- Sanity-check the diagnosis (section 1) — does the profiling evidence actually support
  "this line is the bottleneck," or is there a more subtle explanation?
- Review the proposed algorithm (section 3) for correctness against the semantics listed
  in section 2, especially the five risk points in section 4.
- Say whether the added complexity (a heap + lazy deletion + multi-skill bump) is
  proportionate, or whether there's a simpler data structure that gets the same
  asymptotic win with less code / less risk of a subtle bug in a scientific simulation
  where reproducibility matters.

---

# `_process_work` and the causal-event lookup

With `_allocate()` fixed, `_process_work` turned out to have the identical disease: for every work
item it rebuilt and sorted a fresh candidate list from the whole team (cProfile at 10,000 employees:
232K sort-key evaluations in one month). Fixed with the same lazy-deletion heap-per-skill technique,
keyed to reproduce the original stable sort's tie-break exactly (position in the team's member list,
not employee id, since the original never included id as a tie-breaker).

Separately, `recent_team_causes`/`recent_emp_causes` — used to attach plausible causes to every
event — look for a handful of specific event kinds, but the single most frequent event in the whole
simulation, an employee becoming overloaded, is not one of them. The event index was one flat list
per team, so every lookup walked that noise regardless of what it was actually looking for. Bucketed
the index by kind at the point events are recorded, so a lookup only ever touches the kinds it asked
for.

**Verified:** shadow run of both original algorithms against the current code across both templates
and six seeds, 30 months each — metrics history, event descriptions, and event causes lists
byte-identical in all 12 runs. Wall-clock at 10,000 employees: ~6.5s/month → ~1.3s/month.

---

# The informal-relationship graph

Even after both fixes above, wall-clock at scale was still worse than linear. Profiling traced the
remainder to org generation: every pair of teammates got a 45% chance of an informal relationship,
so relationship count per person scaled with team size, making the monthly relationship-decay loop
in `_psychology` quadratic in population by construction — a modelling choice, not an implementation
bug, and also unrealistic on its own terms (nobody maintains a relationship with 45% of a
1,000-person team).

Fixed by capping relationships per person at a fixed number regardless of team size —
`SimConfig.max_relationships_per_person`, default 150 (Dunbar's number) — enforced everywhere a
relationship can be created: org generation (both within-team and cross-team ties) and the
`seek_help` tie-strengthening action, which could otherwise keep adding ties indefinitely across a
long-running simulation. Within-team seeding was rewritten from an all-pairs Bernoulli(0.45) roll to
each person sampling a bounded number of teammates directly, which also drops generation itself from
O(team_size²) to O(team_size). Since both sides now sample independently, a pair links if *either*
side samples the other, which would roughly double the resulting average degree versus the original
one-roll-per-pair model — halved the target-degree formula (0.45 → 0.225) to compensate.

**Verified:** average relationships/person for the shipped templates barely moved (prototype 5.9 vs
previously ~6.5; charity500 9.25 vs ~9.6), while a 10,000-employee org now holds flat at the 150 cap
instead of averaging ~650. 34-test suite passes; same-seed determinism and different-seed divergence
hold for both templates over 36 months. `_psychology`'s per-employee cost roughly flattens with
scale afterward (5.2µs at 1,000 employees → 19.0µs at 20,000, versus → 120µs before). Full step() at
10,000 employees: ~1.3s/month → ~0.9s/month; 20,000 (previously impractical): ~2.8s/month.

---

# The work-item transfer cap

The three fixes above are pure performance work — verified to produce byte-identical or
statistically-equivalent output to the original code. This last one is a genuine bug fix, found by
running a 10,000-employee batch sweep and asking whether the outcome distribution still made sense
(it didn't: "stable" dropped to 0% with a different, seemingly unrelated team reported as the worst
bottleneck on every check).

`transfer_item()` taxes a work item 25% whenever it lands on a team whose declared `skills_provided`
doesn't cover its skill — a reasonable one-off penalty for working outside your speciality. But the
two actions that call it, `seek_help` and `_manager_redistribute`, gate the transfer with a looser
check, `team_can_do()`, which accepts a team if just two of its members happen to have incidental
proficiency ≥0.35 in that skill — even when it isn't the team's actual specialty. Every transfer that
only qualifies through that loophole is exactly the case that triggers the penalty, and nothing
capped how many times the same item could be re-transferred. Traced one real item at 10,000
employees: created in `operations`, bounced through bizsupport, finance, tech and comms 13 times
over 17 months, its remaining hours compounding from 1,843 to 31,258 (~17x) and single-handedly
dominating whichever team it happened to be sitting in that month.

This was never reachable at the templates' native scale — too few items in flight at once for the
unlucky streak to occur — and became close to certain at 10,000 employees, where there are ~250–300
new items a month and proportionally more transfer decisions being made.

**Fix:** `WorkItem.transfer_count`, capped at `SimConfig.max_item_transfers` (default 2) in both
callers; a capped-out item is treated as if no eligible team was found rather than blocked inside
`transfer_item()` itself, so callers' own moved-item bookkeeping stays correct.

**Verified:** the same seed that produced the 31,258-hour item now stays bounded — org-wide backlog
0.06 to 0.28 months across 36 months (was 0.06 to 3.17), worst team's own backlog never exceeds 0.89
months (was 17.9). Checked across four seeds: no item's remaining hours ever exceed exactly 1.25²
(1.5625×), regardless of how long the run goes. Re-running the 10,000-employee batch sweep afterward,
"stable" stayed at 0% — but for a legible, consistent reason: bottleneck now concentrates on
`bizsupport` (the team the admin-cut scenario actually targets) in 100% of runs, not a different
unrelated team each time. A 20% capacity cut genuinely destabilising a 10,000-person admin function
is a real finding to take on its own terms, not an artifact of the transfer bug. A 24-seed sweep at
the templates' native scale afterward confirmed nothing regressed there (stable 50%, bottleneck
41.7%, both close to the pre-investigation baseline).
