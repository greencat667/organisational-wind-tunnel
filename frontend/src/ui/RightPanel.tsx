import { useEffect, useState } from 'react'
import { useStore } from '../lib/store'
import { api } from '../lib/api'

export function RightPanel() {
  const selection = useStore((s) => s.selection)
  const whyEvent = useStore((s) => s.whyEvent)
  const status = useStore((s) => s.status)
  if (!selection && whyEvent === null) return (
    <div className="overlay side right">
      <div className="panel">
        <h3>Inspector</h3>
        <div className="muted">Click an employee or team in the 3D world, or an event in the timeline.</div>
        {status?.forked && <div className="muted" style={{ marginTop: 8 }}><span className="tag blue">baseline</span> and <span className="tag">intervention</span> run from the same seed with identical external luck; differences are caused by the change.</div>}
        <Legend />
      </div>
    </div>
  )
  return (
    <div className="overlay side right">
      {whyEvent !== null && <Why />}
      {selection?.kind === 'employee' && <EmployeeInspector />}
      {selection?.kind === 'team' && <TeamInspector />}
    </div>
  )
}

function Legend() {
  return (
    <div style={{ marginTop: 12 }}>
      <div className="legend"><span><i style={{ background: '#ffd27a' }} />work item</span><span><i style={{ background: '#ff7a8a' }} />transferred / urgent</span><span><i style={{ background: '#6fd3ff' }} />information</span></div>
      <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>Figures pulse faster under workload, jitter under stress, dim with low morale, rise and fade when leaving. Stacks beside teams are queued work.</div>
    </div>
  )
}

function Why() {
  const whyEvent = useStore((s) => s.whyEvent)!
  const status = useStore((s) => s.status)
  const set = useStore((s) => s.set)
  const [data, setData] = useState<any>(null)
  const world = status?.forked ? 'intervention' : 'baseline'
  useEffect(() => { setData(null); api(`/why/${world}/${whyEvent}`).then(setData).catch(() => api(`/why/baseline/${whyEvent}`).then(setData)) }, [whyEvent])
  return (
    <div className="panel" style={{ maxHeight: '55%' }}>
      <h3>Why did this happen? <button className="btn sm ghost" onClick={() => set({ whyEvent: null })}>×</button></h3>
      {!data ? <div className="muted">tracing…</div> : (
        <>
          <div className="chain">
            {data.chain.map((c: any, i: number) => (
              <div key={c.id} className={`node ${c.kind === 'intervention' ? 'root' : ''}`}>
                <div className="when">{c.date}{c.emergent ? <span className="tag">emergent</span> : null}{c.kind === 'intervention' ? <span className="tag blue">intervention</span> : null}</div>
                <div>{c.description}</div>
              </div>
            ))}
          </div>
          {data.chain.length <= 1 && <div className="muted">No recorded causes beyond this event (exogenous or first-order).</div>}
          <div className="muted" style={{ marginTop: 6 }}>{data.nodes.length} events in the causal neighbourhood. Chain follows the cause closest to the intervention at each step.</div>
        </>
      )}
    </div>
  )
}

function EmployeeInspector() {
  const sel = useStore((s) => s.selection)!
  const month = useStore((s) => s.status?.month)
  const [d, setD] = useState<any>(null)
  const [replay, setReplay] = useState<any | null>(null)
  useEffect(() => { api(`/employee/${sel.world}/${sel.id}`).then(setD).catch(() => setD(null)) }, [sel.id, sel.world, month])
  if (!d) return <div className="panel"><h3>Employee</h3><div className="muted">loading…</div></div>
  const e = d.employee
  const last = d.decisions[d.decisions.length - 1]
  return (
    <div className="panel" style={{ flex: 1 }}>
      <h3>{e.name} <span className={`tag ${sel.world === 'baseline' ? 'blue' : ''}`}>{sel.world}</span></h3>
      <div style={{ fontSize: 13 }}>{e.role_title} · {d.team.name}{e.is_manager ? ' · manager' : ''}</div>
      <div className="muted">{e.archetype} · {e.experience_months} months tenure · grade {e.grade} · {e.status}{e.onboarding_months_left ? ` · onboarding ${e.onboarding_months_left} mo` : ''}</div>
      <div style={{ marginTop: 8 }}>
        {[['Workload', e.workload, 1.5], ['Stress', e.stress, 1], ['Morale', e.morale, 1], ['Trust in management', e.trust_management, 1], ['Turnover intention', e.turnover_intention, 1], ['Team backlog (months)', d.team.backlog_months, 3]].map(([k, v, max]: any) => (
          <div key={k}><div className="row"><span>{k}</span><span>{typeof v === 'number' ? (k === 'Workload' ? `${Math.round(v * 100)}%` : v.toFixed(2)) : v}</span></div><div className="bar"><div style={{ width: `${Math.min(100, (v / max) * 100)}%`, background: k === 'Stress' || k === 'Turnover intention' ? 'var(--danger)' : 'var(--accent)' }} /></div></div>
        ))}
      </div>
      <h4>Traits</h4>
      <div className="muted" style={{ fontSize: 11 }}>{['change_tolerance', 'risk_tolerance', 'collaboration_tendency', 'escalation_tendency', 'autonomy', 'adaptability', 'institutional_knowledge'].map((k) => `${k.replace(/_/g, ' ')} ${e[k].toFixed(2)}`).join(' · ')}</div>
      <h4>Current work <span className="muted">({d.work.length})</span></h4>
      {d.work.slice(0, 6).map((w: any) => <div className="row" key={w.id}><span>{w.kind}{w.priority === 1 ? ' · urgent' : ''}</span><span>{w.remaining_hours}h</span></div>)}
      {last && (
        <>
          <h4>This month <span className="muted">· {last.engine}{last.cached ? ' · cached' : ''}{last.fallback ? ' · fallback' : ''}</span></h4>
          {Object.entries(last.probabilities).sort((a: any, b: any) => b[1] - a[1]).map(([k, v]: any) => (
            <div key={k}><div className="row"><span>{k.replace(/_/g, ' ')}</span><span>{Math.round(v * 100)}%</span></div><div className="bar"><div style={{ width: `${v * 100}%`, background: k === last.action ? 'var(--intervention)' : 'var(--accent)' }} /></div></div>
          ))}
          <div style={{ marginTop: 6, fontSize: 12 }}>ACTUAL ACTION: <b>{last.action.replace(/_/g, ' ')}</b>{last.target ? ` → ${last.target}` : ''} <span className="muted">· confidence {last.confidence} · {last.route}{last.raw?.guard ? ` · guarded (${last.raw.guard})` : ''}</span></div>
          <div className="muted" style={{ fontSize: 11 }}>triggers: {last.triggers.join(', ')} · {last.latency_ms} ms</div>
        </>
      )}
      <h4>Informal ties</h4>
      <div className="muted" style={{ fontSize: 11 }}>{d.informal_ties.map((t: any) => `${t[2]} (${t[3]}) ${t[1]}`).join(' · ') || 'none'}</div>
      <div style={{ marginTop: 10 }}><button className="btn sm" onClick={() => setReplay(replay ? null : d.decisions)}>{replay ? 'HIDE REPLAY' : 'REPLAY DECISIONS'}</button></div>
      {replay && replay.slice().reverse().map((r: any, i: number) => (
        <div key={i} style={{ marginTop: 8, borderTop: '1px solid var(--panel-border)', paddingTop: 6 }}>
          <div className="mono" style={{ fontSize: 11, color: 'var(--text-dim)' }}>month {r.month} · {r.engine} · {r.route} · conf {r.confidence} · {r.latency_ms} ms</div>
          <pre style={{ fontSize: 10, whiteSpace: 'pre-wrap', color: 'var(--text-dim)', margin: '4px 0', maxHeight: 120, overflow: 'auto' }}>{r.state_text}</pre>
          <div style={{ fontSize: 12 }}>→ <b>{r.action}</b> {r.target || ''} <span className="muted">{JSON.stringify(r.probabilities)}</span></div>
          {r.raw?.answers && <div className="muted" style={{ fontSize: 10 }}>model: {JSON.stringify(r.raw.adjusted || r.raw.answers).slice(0, 300)}</div>}
          {r.raw?.function_calls && <div className="muted" style={{ fontSize: 10 }}>needle: {JSON.stringify(r.raw.function_calls)} {r.raw.reasoning}</div>}
        </div>
      ))}
    </div>
  )
}

function TeamInspector() {
  const sel = useStore((s) => s.selection)!
  const month = useStore((s) => s.status?.month)
  const set = useStore((s) => s.set)
  const [d, setD] = useState<any>(null)
  useEffect(() => { api(`/team/${sel.world}/${sel.id}`).then(setD).catch(() => setD(null)) }, [sel.id, sel.world, month])
  if (!d) return <div className="panel"><h3>Team</h3><div className="muted">loading…</div></div>
  const t = d.team
  const h = d.history
  return (
    <div className="panel" style={{ flex: 1 }}>
      <h3>{t.name} <span className={`tag ${sel.world === 'baseline' ? 'blue' : ''}`}>{sel.world}</span></h3>
      <div className="muted">{t.function} · {d.members.length} people{t.vacancies?.length ? ` · ${t.vacancies.length} vacant` : ''}{t.protected ? ' · protected' : ''}{!t.accepting_transfers ? ' · not accepting transfers' : ''}{t.hiring_frozen ? ' · hiring frozen' : ''}{t.ai_agents ? ` · ${t.ai_agents} AI agents` : ''}</div>
      {[['Workload', t.workload, 1.5, `${Math.round(t.workload * 100)}%`], ['Backlog', t.backlog_hours / Math.max(1, t.capacity_hours), 3, `${(t.backlog_hours / Math.max(1, t.capacity_hours)).toFixed(2)} months`], ['Management load', t.management_load, 2, t.management_load.toFixed(2)], ['Morale', t.morale, 1, t.morale.toFixed(2)], ['Stress', t.stress, 1, t.stress.toFixed(2)]].map(([k, v, max, label]: any) => (
        <div key={k}><div className="row"><span>{k}</span><span>{label}</span></div><div className="bar"><div style={{ width: `${Math.min(100, (v / max) * 100)}%`, background: (k === 'Stress' && v > 0.5) || (k === 'Backlog' && v > 1) || (k === 'Management load' && v > 1.1) ? 'var(--danger)' : 'var(--accent)' }} /></div></div>
      ))}
      <div className="row"><span>Capacity</span><span>{Math.round(t.capacity_hours)} h/mo</span></div>
      <div className="row"><span>Queue</span><span>{(Object.values(d.queue_by_kind) as number[]).reduce((a, b) => a + b, 0)} items</span></div>
      <div className="row"><span>Completed / arrivals</span><span>{t.completed_this_month} / {t.arrivals_this_month}</span></div>
      <div className="row"><span>Transfers in / out</span><span>{t.transfers_in} / {t.transfers_out}</span></div>
      <div className="row"><span>Errors · approvals waiting</span><span>{t.errors_this_month} · {t.approvals_waiting}</span></div>
      <div className="row"><span>Turnover 12m · automation</span><span>{t.turnover_12m} · {Math.round(t.automation_level * 100)}%</span></div>
      <h4>Queue by kind</h4>
      {Object.entries(d.queue_by_kind).slice(0, 6).map(([k, v]: any) => <div className="row" key={k}><span>{k}</span><span>{v}</span></div>)}
      <h4>Backlog history</h4>
      <MiniChart xs={h.map((x: any) => x.backlog_months || 0)} />
      <h4>Members</h4>
      {d.members.map((m: any) => (
        <div className="row" key={m.id} style={{ cursor: 'pointer' }} onClick={() => set({ selection: { kind: 'employee', id: m.id, world: sel.world } })}>
          <span>{m.name}{m.is_manager ? ' ★' : ''} <span className="muted">{m.behaviour !== 'working' ? m.behaviour.replace(/_/g, ' ') : ''}</span></span>
          <span>{Math.round(m.workload * 100)}% · s{m.stress.toFixed(2)}</span>
        </div>
      ))}
      <h4>Recent events</h4>
      {d.events.slice().reverse().slice(0, 8).map((e: any) => <div className="event" key={e.id} onClick={() => set({ whyEvent: e.id })}><span className="when">m{e.month}</span><span>{e.description}</span></div>)}
    </div>
  )
}

function MiniChart({ xs }: { xs: number[] }) {
  if (xs.length < 2) return null
  const w = 300, h = 44
  const max = Math.max(0.5, ...xs)
  const d = xs.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i / (xs.length - 1)) * w},${h - (v / max) * (h - 4) - 2}`).join(' ')
  return <svg width={w} height={h}><line x1={0} x2={w} y1={h - (1 / max) * (h - 4) - 2} y2={h - (1 / max) * (h - 4) - 2} stroke="#ff7a8a" strokeDasharray="3 3" opacity={0.5} /><path d={d} fill="none" stroke="#ffd27a" strokeWidth={1.4} /></svg>
}
