import { useState } from 'react'
import { useStore } from '../lib/store'
import { api } from '../lib/api'

export function InterpretModal() {
  const it = useStore((s) => s.interpret)!
  const set = useStore((s) => s.set)
  const [editing, setEditing] = useState(false)
  const [json, setJson] = useState(JSON.stringify(it.plan, null, 2))
  const [err, setErr] = useState<string | null>(null)
  const run = async () => {
    try {
      const plan = editing ? JSON.parse(json) : it.plan
      await api('/run', { plan, text: it.text })
      set({ interpret: null, viewMode: 'split', world: 'intervention', panel: 'events' })
    } catch (e: any) { setErr(String(e.message || e)) }
  }
  return (
    <div className="modal-bg" onClick={() => set({ interpret: null })}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>INTERPRETED CHANGE</h2>
        <div className="src">{it.source === 'apple_fm' ? `Apple Foundation Model (on-device) · ${it.latency_ms} ms` : `rule-based parser (Apple model ${it.error ? 'unavailable' : 'not used'})`}{it.error ? ` · ${it.error.slice(0, 80)}` : ''}</div>
        <div className="muted" style={{ fontSize: 12, marginTop: 8, color: 'var(--text-dim)' }}>“{it.text}”</div>
        {!editing ? (
          <div className="lines">{it.interpreted.map((l, i) => <div key={i}>{l}</div>)}</div>
        ) : (
          <textarea value={json} onChange={(e) => setJson(e.target.value)} />
        )}
        {err && <div style={{ color: 'var(--danger)', fontSize: 12 }}>{err}</div>}
        <div className="actions">
          <button className="btn ghost" onClick={() => set({ interpret: null })}>CANCEL</button>
          <button className="btn" onClick={() => setEditing(!editing)}>{editing ? 'VIEW' : 'EDIT'}</button>
          <button className="btn primary" onClick={run}>RUN EXPERIMENT</button>
        </div>
      </div>
    </div>
  )
}
