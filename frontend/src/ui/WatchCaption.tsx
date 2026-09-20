import { useStore } from '../lib/store'

export function WatchCaption() {
  const status = useStore((s) => s.status)
  const metrics = useStore((s) => s.metrics)
  const events = useStore((s) => s.events)
  const b = metrics.baseline[metrics.baseline.length - 1]
  const i = metrics.intervention[metrics.intervention.length - 1]
  const world = status?.forked ? 'intervention' : 'baseline'
  const recent = events[world].slice(-1)[0]
  let headline = ''
  let delta = ''
  if (b && i) {
    let best: any = null, bd = 0
    for (const tid in i.teams) {
      const x = i.teams[tid], y = b.teams[tid]
      if (!y) continue
      const d = Math.abs(x.backlog_months - y.backlog_months)
      if (d > bd) { bd = d; best = { tid, x, y } }
    }
    if (best && bd > 0.1) {
      headline = `${best.tid.replace(/_/g, ' ')} backlog`
      const rel = best.y.backlog_months > 0.05 ? Math.round(((best.x.backlog_months - best.y.backlog_months) / best.y.backlog_months) * 100) : null
      delta = rel !== null ? `${rel > 0 ? '+' : ''}${rel}% vs baseline` : `${best.x.backlog_months.toFixed(1)} months of work waiting`
    }
  }
  return (
    <div className="watch-caption">
      <div className="date">{status?.label?.toUpperCase()}</div>
      {headline ? <><div className="big">{headline}</div><div className="delta">{delta}</div></> : recent ? <div className="big" style={{ fontSize: 22 }}>{recent.description}</div> : null}
      <div style={{ marginTop: 14, fontSize: 11, color: 'var(--text-faint)' }}>press W to exit watch mode</div>
    </div>
  )
}
