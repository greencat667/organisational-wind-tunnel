import { useEffect, useState } from 'react'
import { useStore } from '../lib/store'
import { api } from '../lib/api'
import { play } from './TopBar'
import type { Metrics } from '../lib/types'

const METRICS: [string, string, (m: Metrics) => number, (v: number) => string, boolean][] = [
  ['Delivery', 'delivery', (m) => m.delivery, (v) => `${Math.round(v * 100)}%`, false],
  ['Backlog', 'backlog_months', (m) => m.backlog_months, (v) => `${v.toFixed(2)} mo`, true],
  ['Cost (YTD)', 'cost_ytd', (m) => m.cost_ytd, (v) => `£${(v / 1e6).toFixed(2)}m`, true],
  ['Workload', 'workload', (m) => m.workload, (v) => `${Math.round(v * 100)}%`, true],
  ['Stress', 'stress', (m) => m.stress, (v) => v.toFixed(2), true],
  ['Turnover 12m', 'turnover_12m', (m) => m.turnover_12m, (v) => `${v}`, true],
  ['Mgmt load', 'management_load', (m) => m.management_load, (v) => v.toFixed(2), true],
  ['Capacity', 'capacity_hours', (m) => m.capacity_hours, (v) => `${Math.round(v / 100) / 10}k h`, false],
  ['Cooperation', 'cooperation', (m) => m.cooperation, (v) => `${v}`, false],
  ['Info reach', 'information_reach', (m) => m.information_reach, (v) => `${Math.round(v * 100)}%`, false],
]
const AI_METRICS: [string, string, (m: Metrics) => number, (v: number) => string, boolean][] = [
  ['AI agents', 'ai_agents', (m) => m.ai_agents || 0, (v) => `${v}`, false],
  ['AI exceptions', 'ai_exceptions', (m) => m.ai_exceptions || 0, (v) => `${v}/mo`, true],
  ['AI defects downstream', 'downstream_ai_errors', (m) => m.downstream_ai_errors || 0, (v) => `${v}/mo`, true],
  ['Deskilling', 'deskilling_index', (m) => m.deskilling_index || 0, (v) => v.toFixed(3), true],
]

export function Bottom() {
  const status = useStore((s) => s.status)
  const metrics = useStore((s) => s.metrics)
  const viewMonth = useStore((s) => s.viewMonth)
  const set = useStore((s) => s.set)
  const interpreting = useStore((s) => s.interpreting)
  const [text, setText] = useState('')
  const [scenarios, setScenarios] = useState<{ id: string; name: string; text: string }[]>([])
  useEffect(() => { api('/scenarios').then(setScenarios).catch(() => {}) }, [])
  const at = (w: 'baseline' | 'intervention') => {
    const ms = metrics[w]
    if (!ms.length) return null
    if (viewMonth === null) return ms[ms.length - 1]
    return ms.find((m) => m.month === viewMonth) || ms[ms.length - 1]
  }
  const b = at('baseline'), i = status?.forked ? at('intervention') : null
  const maxMonth = metrics.baseline.length ? metrics.baseline[metrics.baseline.length - 1].month : 0
  const minMonth = metrics.baseline.length ? metrics.baseline[0].month : 0

  const submit = async () => {
    if (!text.trim()) return
    set({ interpreting: true })
    try {
      const r = await api('/interpret', { text })
      set({ interpret: { text, plan: r.plan, interpreted: r.interpreted, source: r.source, latency_ms: r.latency_ms, error: r.error } })
    } finally { set({ interpreting: false }) }
  }

  return (
    <div className="overlay bottom">
      <div className="scrubber">
        <span>{metrics.baseline[0]?.label}</span>
        <input type="range" min={minMonth} max={maxMonth} value={viewMonth ?? maxMonth} onChange={(e) => { const v = +e.target.value; set({ viewMonth: v >= maxMonth ? null : v }) }} />
        <span>{status?.label}</span>
        <button className={`btn sm ${viewMonth === null ? 'active' : ''}`} onClick={() => set({ viewMonth: null })}>live</button>
        <span style={{ width: 8 }} />
        <button className="btn sm" onClick={() => play({ playing: !status?.playing })}>{status?.playing ? 'pause' : 'play'}</button>
        <button className="btn sm" onClick={() => play({ steps: 1 })}>+1 mo</button>
        <button className="btn sm" onClick={() => play({ steps: 6 })}>+6 mo</button>
        <button className="btn sm" onClick={() => play({ until_month: (status?.month || 0) + 36, speed: 10000 })}>+3 yrs</button>
        {[1, 6, 12, 10000].map((v) => <button key={v} className={`btn sm ${status?.speed === v ? 'active' : 'ghost'}`} onClick={() => play({ speed: v })}>{v === 10000 ? 'max' : v === 12 ? '1y/s' : `${v}m/s`}</button>)}
      </div>
      <div className="metrics">
        {[...METRICS, ...((i && (i.ai_agents || 0) > 0) || (b && (b.ai_agents || 0) > 0) ? AI_METRICS : [])].map(([label, key, fn, fmt, lowerBetter]) => {
          const bv = b ? fn(b) : null, iv = i ? fn(i) : null
          const series = (metrics.baseline.slice(-36)).map(fn)
          const iseries = status?.forked ? metrics.intervention.slice(-36).map(fn) : []
          return (
            <div className="metric" key={key}>
              <div className="k">{label}</div>
              <div className="v">
                <span className="b">{bv !== null ? fmt(bv) : '—'}</span>
                {iv !== null && <span className="i">{fmt(iv)}</span>}
              </div>
              {iv !== null && bv !== null && <div className="d">{delta(bv, iv, lowerBetter)}</div>}
              <Spark a={series} b={iseries} />
            </div>
          )
        })}
      </div>
      <div className="prompt">
        <input placeholder="Describe a change to test… e.g. Reduce administrative capacity by 20% while protecting frontline delivery" value={text}
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && submit()} />
        <button className="btn primary" onClick={submit} disabled={interpreting || !text.trim()}>{interpreting ? <span className="spinner" /> : 'SIMULATE CHANGE'}</button>
        {status?.forked && <button className="btn danger" onClick={async () => { await api('/discard', {}); useStore.getState().init() }}>discard</button>}
      </div>
      <div className="scenarios">
        {scenarios.map((s) => <button key={s.id} className="chip" onClick={() => setText(s.text)}>{s.name}</button>)}
      </div>
    </div>
  )
}

function delta(b: number, i: number, lowerBetter: boolean) {
  if (b === 0 && i === 0) return '='
  const rel = b !== 0 ? (i - b) / Math.abs(b) : (i > 0 ? 1 : 0)
  const sign = i >= b ? '+' : ''
  return `${sign}${Math.round(rel * 100)}% vs baseline`
}

function Spark({ a, b }: { a: number[]; b: number[] }) {
  const all = [...a, ...b]
  if (all.length < 2) return null
  const w = 90, h = 30
  const min = Math.min(...all), max = Math.max(...all)
  const path = (xs: number[]) => xs.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i / Math.max(1, xs.length - 1)) * w},${h - ((v - min) / (max - min || 1)) * (h - 4) - 2}`).join(' ')
  return (
    <svg width={w} height={h}>
      <path d={path(a)} fill="none" stroke="#7fa7ff" strokeWidth={1.2} opacity={0.8} />
      {b.length > 1 && <path d={path(b)} fill="none" stroke="#ffb566" strokeWidth={1.2} opacity={0.9} />}
    </svg>
  )
}
