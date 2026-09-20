import { create } from 'zustand'
import type { Frame, Metrics, SimEvent, Status, Structure, WorldLabel, XRay, ViewMode } from './types'
import { api } from './api'

interface Selection { kind: 'employee' | 'team'; id: string; world: WorldLabel }

interface State {
  connected: boolean
  status: Status | null
  structure: Record<WorldLabel, Structure | null>
  frames: Record<WorldLabel, Frame[]>
  metrics: Record<WorldLabel, Metrics[]>
  events: Record<WorldLabel, SimEvent[]>
  viewMonth: number | null          // null = live (latest)
  world: WorldLabel                 // which world the single view shows
  viewMode: ViewMode
  xray: XRay
  selection: Selection | null
  hover: { kind: 'employee' | 'team'; id: string; world: WorldLabel; x: number; y: number } | null
  whyEvent: number | null
  watch: boolean
  debug: boolean
  followConsequences: boolean
  showNetwork: boolean
  panel: 'events' | 'effects' | 'batch' | 'inspector' | 'network' | 'saved'
  batchJob: any | null
  interpret: { text: string; plan: any; interpreted: string[]; source: string; latency_ms: number; error: string | null } | null
  interpreting: boolean
  init: () => Promise<void>
  applyFrame: (msg: any) => void
  set: (p: Partial<State>) => void
  select: (s: Selection | null) => void
  latestFrame: (w: WorldLabel) => Frame | null
  frameAt: (w: WorldLabel, month: number | null) => Frame | null
}

export const useStore = create<State>((set, get) => ({
  connected: false,
  status: null,
  structure: { baseline: null, intervention: null },
  frames: { baseline: [], intervention: [] },
  metrics: { baseline: [], intervention: [] },
  events: { baseline: [], intervention: [] },
  viewMonth: null,
  world: 'baseline',
  viewMode: 'single',
  xray: 'work',
  selection: null,
  hover: null,
  whyEvent: null,
  watch: false,
  debug: false,
  followConsequences: false,
  showNetwork: false,
  panel: 'events',
  batchJob: null,
  interpret: null,
  interpreting: false,
  set: (p) => set(p),
  select: (s) => set({ selection: s, panel: s ? 'inspector' : get().panel }),
  latestFrame: (w) => { const f = get().frames[w]; return f.length ? f[f.length - 1] : null },
  frameAt: (w, month) => {
    const f = get().frames[w]
    if (!f.length) return null
    if (month === null) return f[f.length - 1]
    let best = f[0]
    for (const fr of f) { if (fr.month <= month) best = fr; else break }
    return best
  },
  init: async () => {
    const d = await api('/experiment')
    set({
      status: d.status,
      structure: { baseline: d.structure, intervention: d.status.forked ? d.structure : null },
      frames: { baseline: d.frames.baseline || [], intervention: d.frames.intervention || [] },
      metrics: { baseline: d.metrics.baseline || [], intervention: d.metrics.intervention || [] },
      events: { baseline: d.events.baseline || [], intervention: d.events.intervention || [] },
      world: d.status.forked ? 'intervention' : 'baseline',
      viewMode: d.status.forked ? 'split' : 'single',
    })
  },
  applyFrame: (msg) => {
    const st = get()
    const frames = { ...st.frames }
    const metrics = { ...st.metrics }
    const events = { ...st.events }
    for (const w of ['baseline', 'intervention'] as WorldLabel[]) {
      if (msg[w]) {
        frames[w] = [...frames[w], msg[w].frame]
        metrics[w] = [...metrics[w], msg[w].metrics]
        if (msg[w].frame?.new_events?.length) {
          const seen = new Set(events[w].map((e) => e.id))
          events[w] = [...events[w], ...msg[w].frame.new_events.filter((e: SimEvent) => !seen.has(e.id))]
        }
      }
    }
    set({ frames, metrics, events })
  },
}))

let ws: WebSocket | null = null
export function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  const st = useStore.getState()
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`
  ws = new WebSocket(url)
  ws.onopen = () => useStore.setState({ connected: true })
  ws.onclose = () => { useStore.setState({ connected: false }); setTimeout(connect, 1500) }
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.type === 'hello' || msg.type === 'status') useStore.setState({ status: msg.status })
    else if (msg.type === 'frame') { useStore.getState().applyFrame(msg) }
    else if (msg.type === 'forked') {
      const s = useStore.getState()
      useStore.setState({
        status: msg.status,
        structure: { ...s.structure, intervention: msg.structure },
        frames: { ...s.frames, intervention: msg.frame ? [msg.frame] : [] },
        metrics: { ...s.metrics, intervention: s.metrics.baseline.slice(-1) },
        events: { ...s.events, intervention: [] },
        world: 'intervention', viewMode: 'split',
      })
    } else if (msg.type === 'batch') { useStore.setState({ batchJob: { ...(useStore.getState().batchJob || {}), ...msg.job } }) }
  }
  void st
}
