import { useStore } from '../lib/store'

export function Tooltip() {
  const hover = useStore((s) => s.hover)
  const frames = useStore((s) => s.frames)
  const structure = useStore((s) => s.structure)
  if (!hover) return null
  const f = frames[hover.world][frames[hover.world].length - 1]
  if (!f) return null
  if (hover.kind === 'team') {
    const t = f.teams.find((x) => x.id === hover.id)
    if (!t) return null
    return <div className="tooltip" style={{ left: hover.x, top: hover.y }}><b>{t.name}</b><br /><span className="mono">{t.headcount} people · workload {Math.round(t.workload * 100)}% · backlog {t.backlog_months.toFixed(2)} mo · queue {t.queue}</span></div>
  }
  const e = f.employees.find((x) => x[0] === hover.id)
  const s = (structure[hover.world] || structure.baseline)?.employees.find((x: any) => x.id === hover.id)
  if (!e) return null
  return <div className="tooltip" style={{ left: hover.x, top: hover.y }}><b>{s?.name || e[0]}</b> <span className="mono">{s?.role_title}</span><br /><span className="mono">workload {Math.round(e[4] * 100)}% · stress {e[5].toFixed(2)} · morale {e[6].toFixed(2)} · {e[9].replace(/_/g, ' ')}</span></div>
}
