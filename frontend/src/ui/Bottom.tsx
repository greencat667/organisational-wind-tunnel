import { useEffect, useRef, useState } from 'react'
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
  const [text, setTextState] = useState('')
  const textRef = useRef('')
  const setText = (t: string) => { textRef.current = t; setTextState(t) }
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

  // the tour's "set up the demo": fill the box and interpret, as if typed
  const pendingPrompt = useStore((s) => s.pendingPrompt)
  useEffect(() => {
    if (!pendingPrompt) return
    setText(pendingPrompt)
    set({ pendingPrompt: null })
    submit(pendingPrompt)
  }, [pendingPrompt])

  const submit = async (override?: string) => {
    const text = override ?? textRef.current
    if (!text.trim()) return
    set({ interpreting: true })
    try {
      // 1. rule-based interpretation appears immediately…
      const fast = await api('/interpret?fast=true', { text })
      set({ interpret: { text, plan: fast.plan, interpreted: fast.interpreted, source: 'rules', latency_ms: fast.latency_ms, error: null, pending: true } })
      set({ interpreting: false })
      // 2. …and is replaced by the Apple model's reading if it arrives while the modal is still showing that text, unedited
      api('/interpret', { text }).then((r) => {
        const cur = useStore.getState().interpret
        if (!cur || cur.text !== text || cur.edited) return
        if (r.source === 'apple_fm') set({ interpret: { ...cur, plan: r.plan, interpreted: r.interpreted, source: r.source, latency_ms: r.latency_ms, error: r.error, pending: false } })
        else set({ interpret: { ...cur, pending: false, error: r.error } })
      }).catch(() => { const cur = useStore.getState().interpret; if (cur && cur.text === text) set({ interpret: { ...cur, pending: false } }) })
    } finally { set({ interpreting: false }) }
  }

  // Scrubbing back and hitting play used to jump straight to live (play() always resets viewMonth to
  // null) instead of replaying forward from where you scrubbed to, like a video player would. Since the
  // frontend already holds every already-simulated month in `metrics`, replaying it is just a local
  // timer walking viewMonth forward — no backend call needed until it catches up to live.
  const [replayTimer, setReplayTimer] = useState<number | null>(null)
  useEffect(() => () => { if (replayTimer !== null) clearInterval(replayTimer) }, [replayTimer])
  const stopReplay = () => setReplayTimer((t) => { if (t !== null) clearInterval(t); return null })
  const playCmd = (p: Parameters<typeof play>[0]) => { stopReplay(); play(p) }

  const togglePlay = () => {
    if (replayTimer !== null) { stopReplay(); return }
    if (status?.playing) { play({ playing: false }); return }
    if (viewMonth === null || viewMonth >= maxMonth) { play({ playing: true }); return }
    const speed = status?.speed || 1
    if (speed >= 10000) { set({ viewMonth: null }); return }   // "max": already-simulated history has no reason to animate — jump straight to live
    const id = window.setInterval(() => {
      const cur = useStore.getState().viewMonth
      const next = (cur ?? maxMonth) + 1
      if (next >= maxMonth) { stopReplay(); set({ viewMonth: null }) } else set({ viewMonth: next })
    }, Math.max(1000 / speed, 40))
    setReplayTimer(id)
  }
  const isPlaying = !!status?.playing || replayTimer !== null

  const rootRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = rootRef.current
    if (!el) return
    const publish = () => document.documentElement.style.setProperty('--bottom-h', `${el.offsetHeight + 12}px`)
    publish()
    const ro = new ResizeObserver(publish)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  return (
    <div className="overlay bottom" ref={rootRef}>
      <div className="scrubber">
        <button className="btn sm scrub-play" title={isPlaying ? 'Pause' : viewMonth !== null && viewMonth < maxMonth ? 'Play from here' : 'Play'} onClick={togglePlay}>{isPlaying ? '❚❚' : '▶'}</button>
        <span>{metrics.baseline[0]?.label}</span>
        <input type="range" min={minMonth} max={maxMonth} value={viewMonth ?? maxMonth} onChange={(e) => { stopReplay(); const v = +e.target.value; set({ viewMonth: v >= maxMonth ? null : v }) }} />
        <span>{status?.label}</span>
        <button className={`btn sm ${viewMonth === null ? 'active' : ''}`} onClick={() => { stopReplay(); set({ viewMonth: null }) }}>live</button>
        <span style={{ width: 8 }} />
        <button className="btn sm" onClick={() => playCmd({ steps: 1 })}>+1 mo</button>
        <button className="btn sm" onClick={() => playCmd({ steps: 6 })}>+6 mo</button>
        <button className="btn sm" onClick={() => playCmd({ until_month: (status?.month || 0) + 36, speed: 10000 })}>+3 yrs</button>
        {[1, 6, 12, 10000].map((v) => <button key={v} className={`btn sm ${status?.speed === v ? 'active' : 'ghost'}`} onClick={() => playCmd({ speed: v })}>{v === 10000 ? 'max' : v === 12 ? '1y/s' : `${v}m/s`}</button>)}
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
        <button className="btn primary" onClick={() => submit()} disabled={interpreting || !text.trim()}>{interpreting ? <span className="spinner" /> : 'SIMULATE CHANGE'}</button>
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
