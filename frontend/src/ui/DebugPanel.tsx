import { useEffect, useState } from 'react'
import { useStore } from '../lib/store'
import { api } from '../lib/api'

export function DebugPanel() {
  const [d, setD] = useState<any>(null)
  const [fps, setFps] = useState(0)
  const month = useStore((s) => s.status?.month)
  useEffect(() => { api('/diagnostics').then(setD).catch(() => {}) }, [month])
  useEffect(() => {
    let frames = 0, last = performance.now(), raf = 0
    const tick = () => { frames++; const now = performance.now(); if (now - last > 1000) { setFps(Math.round((frames * 1000) / (now - last))); frames = 0; last = now } raf = requestAnimationFrame(tick) }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])
  if (!d) return null
  const t = d.timing?.intervention || d.timing?.baseline || {}
  const es = d.engine_stats || {}
  return (
    <div className="debug">
      <span>FPS <b>{fps}</b></span>
      <span>tick <b>{t.total ? Math.round(t.total * 1000) : '—'} ms</b></span>
      <span>decisions/mo <b>{t.decisions_count ?? '—'}</b></span>
      <span>decision time <b>{t.decisions ? Math.round(t.decisions * 1000) : '—'} ms</b></span>
      <span>engine <b>{d.engine?.name}</b> {d.engine?.device || ''}</span>
      <span>model calls <b>{es.calls ?? 0}</b> mean <b>{es.mean_ms ?? '—'} ms</b></span>
      <span>cache hit <b>{es.cache_hit_rate != null ? Math.round(es.cache_hit_rate * 100) + '%' : '—'}</b> ({es.cache_size ?? 0})</span>
      <span>Apple FM <b>{d.apple_fm?.healthy ? 'up' : 'down'}</b> {d.apple_fm?.last_latency_ms} ms · {d.apple_fm?.last_source}</span>
      <span>memory <b>{d.memory_mb ? `${d.memory_mb} MB` : "—"}</b></span>
      <span>agents <b>{JSON.stringify(d.active_agents)}</b></span>
      <span>work items <b>{JSON.stringify(d.active_work_items)}</b></span>
      <span>triggers <b>{t.triggers ? Object.entries(t.triggers).map(([k, v]) => `${k}:${v}`).join(' ') : '—'}</b></span>
      {d.agreement && Object.values(d.agreement).some((a: any) => a?.n) && (
        <span style={{ gridColumn: '1 / -1' }}>model vs rules agreement <b>{Object.entries(d.agreement).map(([w, a]: any) => `${w}: ${a.agreement_rate != null ? Math.round(a.agreement_rate * 100) + '%' : '—'} (n=${a.n})`).join(' · ')}</b>
          {' '}· where they differ: {Object.entries((Object.values(d.agreement) as any[]).find((a: any) => a?.n)?.by_action || {}).slice(0, 5).map(([k, v]: any) => `${k} model ${v.model}/rules ${v.rules}`).join(', ')}</span>
      )}
    </div>
  )
}
