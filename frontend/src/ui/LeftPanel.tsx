import { useEffect, useState } from 'react'
import { useStore } from '../lib/store'
import { api } from '../lib/api'
import type { SimEvent } from '../lib/types'

export function LeftPanel() {
  const panel = useStore((s) => s.panel)
  const set = useStore((s) => s.set)
  const status = useStore((s) => s.status)
  const tabs: [string, string][] = [['events', 'Timeline'], ['effects', 'Effects'], ['batch', 'Many worlds'], ['saved', 'Saved']]
  return (
    <div className="overlay side left">
      <div className="panel" style={{ flex: 1 }}>
        <h3>
          <span style={{ display: 'flex', gap: 4 }}>
            {tabs.map(([k, l]) => <button key={k} className={`btn sm ${panel === k || (panel === 'inspector' && k === 'events') || (panel === 'network' && k === 'events') ? 'active' : 'ghost'}`} onClick={() => set({ panel: k as any })}>{l}</button>)}
          </span>
        </h3>
        {(panel === 'events' || panel === 'inspector' || panel === 'network') && <Timeline />}
        {panel === 'effects' && (status?.forked ? <Effects /> : <div className="muted">Run an intervention to compare against the baseline.</div>)}
        {panel === 'batch' && <Batch />}
        {panel === 'saved' && <Saved />}
      </div>
    </div>
  )
}

function Timeline() {
  const events = useStore((s) => s.events)
  const status = useStore((s) => s.status)
  const world = status?.forked ? 'intervention' : 'baseline'
  const list = [...events[world]].reverse().slice(0, 80)
  const set = useStore((s) => s.set)
  const frames = useStore((s) => s.frames)
  const label = (m: number) => frames.baseline.find((f) => f.month === m)?.label || `m${m}`
  return (
    <div>
      <div className="muted" style={{ marginBottom: 6 }}>{world} · {events[world].length} significant events · click for WHY</div>
      {list.map((e) => (
        <div key={e.id} className={`event ${e.emergent ? 'em' : ''}`} onClick={() => set({ whyEvent: e.id, panel: 'inspector', selection: null })}>
          <span className="when">{label(e.month)}</span><span className="what">{e.description}</span>
        </div>
      ))}
    </div>
  )
}

export function Effects() {
  const [rep, setRep] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const set = useStore((s) => s.set)
  const month = useStore((s) => s.status?.month)
  const load = async () => { setBusy(true); try { setRep(await api('/effects?min_effect=0.5')) } finally { setBusy(false) } }
  useEffect(() => { load() }, [month])
  if (!rep) return <div className="muted">{busy ? 'analysing…' : '—'}</div>
  const groups: Record<string, any[]> = { first: [], second: [], third: [] }
  for (const e of rep.effects) groups[e.order_label]?.push(e)
  return (
    <div>
      <div className="muted" style={{ marginBottom: 8 }}>Variables that diverged from the baseline (same seed, same luck). Orders are causal distance from the intervention, not judgements.</div>
      {rep.emergence?.length > 0 && (
        <>
          <h4>Emergent effects</h4>
          {rep.emergence.map((e: any, i: number) => (
            <button key={i} className="list-btn" onClick={() => e.event_id != null && set({ whyEvent: e.event_id, panel: 'inspector' })}>
              {e.label}<span className="tag">emergent</span>
              <span className="sub">{fmt(e.value)} vs baseline {fmt(e.baseline)}</span>
            </button>
          ))}
        </>
      )}
      {(['first', 'second', 'third'] as const).map((o) => groups[o].length ? (
        <div key={o}>
          <h4>{o} order <span className="muted">({groups[o].length})</span></h4>
          {groups[o].slice(0, 10).map((e: any, i: number) => (
            <button key={i} className="list-btn" onClick={() => { if (e.event_id != null) set({ whyEvent: e.event_id, panel: 'inspector' }); if (e.team) set({ selection: { kind: 'team', id: e.team, world: 'intervention' } }) }}>
              {e.team_name} · {e.metric.replace(/_/g, ' ')}{e.emergent && <span className="tag">emergent</span>}
              <span className="sub">{fmt(e.baseline_final)} → {fmt(e.intervention_final)} · effect {e.effect_size > 0 ? '+' : ''}{e.effect_size}{e.lag_months != null ? ` · after ${e.lag_months} mo` : ''}</span>
            </button>
          ))}
        </div>
      ) : null)}
      {rep.effects.length === 0 && <div className="muted">No material divergence yet. Advance the clock.</div>}
    </div>
  )
}

function fmt(v: any) { return typeof v === 'number' ? (Math.abs(v) >= 100 ? Math.round(v).toLocaleString() : v.toFixed(2)) : String(v) }

function Batch() {
  const job = useStore((s) => s.batchJob)
  const status = useStore((s) => s.status)
  const [n, setN] = useState(200)
  const [months, setMonths] = useState(36)
  const [engine, setEngine] = useState('heuristic')
  const [explain, setExplain] = useState<string>('')
  const start = async () => {
    const r = await api('/batch', { n, months, engine })
    useStore.setState({ batchJob: { id: r.job_id, status: 'running', done: 0, n } })
    poll(r.job_id)
  }
  const poll = async (id: string) => {
    const j = await api(`/batch/${id}`)
    useStore.setState({ batchJob: j })
    if (j.status === 'running') setTimeout(() => poll(id), 800)
  }
  const s = job?.result?.summary
  return (
    <div>
      <div className="muted">Run the same intervention across many synthetic futures without rendering. Frequencies are within the model, not real-world probabilities.</div>
      <div style={{ display: 'flex', gap: 6, margin: '8px 0', alignItems: 'center' }}>
        <input className="mono" style={{ width: 70, background: '#060810', color: 'var(--text)', border: '1px solid var(--panel-border)', borderRadius: 6, padding: 5 }} type="number" value={n} onChange={(e) => setN(+e.target.value)} />
        <span className="muted">worlds ×</span>
        <input className="mono" style={{ width: 56, background: '#060810', color: 'var(--text)', border: '1px solid var(--panel-border)', borderRadius: 6, padding: 5 }} type="number" value={months} onChange={(e) => setMonths(+e.target.value)} />
        <span className="muted">months</span>
        <select value={engine} onChange={(e) => setEngine(e.target.value)} style={{ background: '#060810', color: 'var(--text)', border: '1px solid var(--panel-border)', borderRadius: 6, padding: 5 }}>
          <option value="heuristic">heuristic</option><option value="laya">laya (slow)</option><option value="needle">needle (slow)</option>
        </select>
      </div>
      <button className="btn primary" disabled={!status?.forked || job?.status === 'running'} onClick={start}>RUN {n} ORGANISATIONS</button>
      {!status?.forked && <div className="muted" style={{ marginTop: 6 }}>Run an intervention first.</div>}
      {job?.status === 'running' && <div style={{ marginTop: 8 }}><div className="muted">{job.done}/{job.n}</div><div className="bar"><div style={{ width: `${(100 * job.done) / job.n}%` }} /></div></div>}
      {job?.status === 'error' && <div style={{ color: 'var(--danger)' }}>{job.error}</div>}
      {s && (
        <div style={{ marginTop: 10 }}>
          <h4>Outcome frequencies <span className="muted">({s.n} worlds)</span></h4>
          {Object.entries(s.outcome_frequencies).map(([k, v]: any) => (
            <div key={k}><div className="row"><span>{k.replace(/_/g, ' ')}</span><span>{Math.round(v * 100)}%</span></div><div className="bar"><div style={{ width: `${v * 100}%`, background: 'var(--intervention)' }} /></div></div>
          ))}
          <h4>Bottleneck frequency by team</h4>
          {Object.entries(s.bottleneck_frequency_by_team).filter(([, v]: any) => v > 0).sort((a: any, b: any) => b[1] - a[1]).map(([k, v]: any) => <div className="row" key={k}><span>{k}</span><span>{Math.round(v * 100)}%</span></div>)}
          <h4>Outcome clusters</h4>
          {s.clusters.map((c: any) => <div className="row" key={c.id}><span>{c.name}</span><span>{Math.round(c.share * 100)}%</span></div>)}
          <h4>Distributions (p10 · p50 · p90)</h4>
          {Object.entries(s.distributions).map(([k, d]: any) => (
            <div className="row" key={k}><span>{k.replace(/_/g, ' ')}</span><span style={{ fontSize: 11 }}><span style={{ color: 'var(--baseline)' }}>{fmt(d.baseline.p10)} · {fmt(d.baseline.p50)} · {fmt(d.baseline.p90)}</span><br /><span style={{ color: 'var(--intervention)' }}>{fmt(d.intervention.p10)} · {fmt(d.intervention.p50)} · {fmt(d.intervention.p90)}</span></span></div>
          ))}
          {s.surprises?.length > 0 && (
            <>
              <h4>Unexpected consequences <span className="tag">distant</span></h4>
              <div className="muted">Variables far from the intervention in the organisation graph that moved in many worlds.</div>
              {s.surprises.map((x: any, i: number) => <div className="row" key={i}><span>{x.team_name} · {x.metric.replace(/_/g, ' ')}</span><span>{Math.round(x.frequency * 100)}%{x.median_lag != null ? ` · ~${x.median_lag} mo` : ''}</span></div>)}
            </>
          )}
          {Object.keys(s.emergence_frequency || {}).length > 0 && (<><h4>Emergent effects (share of worlds)</h4>{Object.entries(s.emergence_frequency).map(([k, v]: any) => <div className="row" key={k}><span>{k}</span><span>{Math.round(v * 100)}%</span></div>)}</>)}
          <button className="btn sm" style={{ marginTop: 8 }} onClick={async () => { const r = await api('/explain', { prompt: `Summarise these batch results for a leadership team. Intervention: ${status?.intervention_text}. Worlds: ${s.n}. Outcome frequencies: ${JSON.stringify(s.outcome_frequencies)}. Clusters: ${JSON.stringify(s.clusters.map((c: any) => [c.name, c.share]))}. Surprises: ${JSON.stringify(s.surprises.slice(0, 4).map((x: any) => [x.team_name, x.metric, x.frequency]))}.` }); setExplain(r.text || 'Apple Foundation Model unavailable for explanation right now.') }}>EXPLAIN (Apple FM)</button>
          {explain && <div className="muted" style={{ marginTop: 6, whiteSpace: 'pre-wrap', color: 'var(--text)' }}>{explain}</div>}
          <div className="muted" style={{ marginTop: 8 }}>{s.disclaimer}</div>
        </div>
      )}
    </div>
  )
}

function Saved() {
  const [data, setData] = useState<any>(null)
  const [tpl, setTpl] = useState('prototype')
  const [seed, setSeed] = useState(7)
  const [engine, setEngine] = useState('heuristic')
  const [util, setUtil] = useState(0.75)
  const [cap, setCap] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const load = () => api('/experiments').then(setData)
  useEffect(() => { load() }, [])
  const inp = { background: '#060810', color: 'var(--text)', border: '1px solid var(--panel-border)', borderRadius: 6, padding: 5 } as const
  return (
    <div>
      <h4>New experiment</h4>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <select value={tpl} onChange={(e) => setTpl(e.target.value)} style={inp}><option value="prototype">prototype · 100 people</option><option value="charity500">charity500 · 500 people</option></select>
        <input className="mono" type="number" value={seed} onChange={(e) => setSeed(+e.target.value)} style={{ ...inp, width: 64 }} />
        <select value={engine} onChange={(e) => setEngine(e.target.value)} style={inp}><option value="heuristic">heuristic rules</option><option value="laya">Laya</option><option value="needle">Needle 3</option></select>
        <select value={util} onChange={(e) => setUtil(+e.target.value)} style={inp} title="How stretched the organisation starts"><option value={0.65}>slack org (65%)</option><option value={0.75}>normal org (75%)</option><option value={0.85}>lean org (85%)</option></select>
        <input className="mono" placeholder="decisions/mo" title="Cap on agent evaluations per month, applied to every engine (blank = engine default)" value={cap} onChange={(e) => setCap(e.target.value)} style={{ ...inp, width: 92 }} />
        <button className="btn sm primary" disabled={busy} onClick={async () => { setBusy(true); try { await api('/experiment', { template: tpl, seed, engine, utilisation: util, decisions_per_month: cap ? +cap : null }); await useStore.getState().init() } finally { setBusy(false) } }}>{busy ? <span className="spinner" /> : 'NEW'}</button>
      </div>
      <div className="muted" style={{ marginTop: 4 }}>Same organisation, seed and decision cap, different engine = a fair Laya vs Needle vs rules comparison (the dev panel shows how often the model agrees with the rules). Model engines load on first use (Laya ~25 s).</div>
      <h4>Save & export</h4>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
        <button className="btn sm" onClick={async () => { await api('/save', {}); load() }}>save experiment</button>
        <a className="btn sm" href="/api/export/baseline/metrics?fmt=csv" download>metrics.csv</a>
        <a className="btn sm" href="/api/export/intervention/events" download>events.json</a>
        <a className="btn sm" href="/api/export/intervention/decisions" download>decisions.json</a>
      </div>
      <h4>Experiments <span className="muted">· load replays the saved run exactly; fork replays to a month and continues live</span></h4>
      {data?.experiments?.map((e: any) => (
        <div className="row" key={e.id} style={{ alignItems: 'center' }}>
          <span>{e.name || e.id} <span className="muted">{e.engine} · {e.months} mo{e.fork_month != null ? ` · forked m${e.fork_month}` : ''}</span></span>
          <span style={{ display: 'flex', gap: 4 }}>
            <button className="btn sm" disabled={busy} onClick={async () => { setBusy(true); try { await api(`/load/${e.id}`, {}); await useStore.getState().init() } finally { setBusy(false) } }}>load</button>
            <button className="btn sm" disabled={busy} onClick={async () => { const m = prompt(`Fork from which month? (0–${e.months})`, String(Math.max(0, (e.fork_month ?? 0) + 6))); if (m === null) return; setBusy(true); try { await api(`/load/${e.id}?month=${+m}&engine=${engine}`, {}); await useStore.getState().init() } finally { setBusy(false) } }}>fork…</button>
          </span>
        </div>
      ))}
      <h4>Batches</h4>
      {data?.batches?.map((b: any) => <div className="row" key={b.id}><span>{b.id}</span><span>{b.n} × {b.months}mo</span></div>)}
      <div className="muted" style={{ marginTop: 8 }}>Stored in a local SQLite file. No telemetry, no cloud.</div>
    </div>
  )
}
