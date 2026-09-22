import { useStore } from '../lib/store'
import { api } from '../lib/api'
import type { XRay, ViewMode } from '../lib/types'

const SPEEDS: [string, number][] = [['1 mo/s', 1], ['6 mo/s', 6], ['1 yr/s', 12], ['max', 10000]]
const XRAYS: XRay[] = ['structure', 'work', 'information', 'capacity', 'cost', 'change', 'dependencies']

export function TopBar() {
  const status = useStore((s) => s.status)
  const viewMonth = useStore((s) => s.viewMonth)
  const xray = useStore((s) => s.xray)
  const viewMode = useStore((s) => s.viewMode)
  const world = useStore((s) => s.world)
  const watch = useStore((s) => s.watch)
  const follow = useStore((s) => s.followConsequences)
  const frames = useStore((s) => s.frames)
  const set = useStore((s) => s.set)
  const label = viewMonth === null ? status?.label : (frames.baseline.find((f) => f.month === viewMonth)?.label || status?.label)
  const speedLabel = SPEEDS.find(([, v]) => v === status?.speed)?.[0] || `${status?.speed} mo/s`
  return (
    <div className="overlay topbar">
      <div className="brand"><b>ORGANISATIONAL</b> WIND TUNNEL <span style={{ marginLeft: 14, color: 'var(--text-faint)' }}>{status ? `${status.template} · seed ${status.seed} · ${status.engine}` : '…'}</span></div>
      <div className="clock">
        {viewMonth !== null && <span className="world" style={{ color: 'var(--accent-2)' }}>REPLAY</span>}
        <span>{label || '—'}</span>
        <span className="speed">{status?.playing ? '▶ ' : '❚❚ '}{speedLabel}</span>
      </div>
      <div className="controls">
        <div className="modes">
          {XRAYS.map((x) => <button key={x} className={`btn sm ${xray === x ? 'active' : 'ghost'}`} onClick={() => set({ xray: x, showNetwork: x === 'information' })}>{x}</button>)}
        </div>
        <span style={{ width: 10 }} />
        {status?.forked && (
          <>
            {(['single', 'split', 'difference'] as ViewMode[]).map((m) => <button key={m} className={`btn sm ${viewMode === m ? 'active' : ''}`} onClick={() => set({ viewMode: m })}>{m}</button>)}
            {viewMode === 'single' && <button className="btn sm" onClick={() => set({ world: world === 'baseline' ? 'intervention' : 'baseline' })}>{world}</button>}
            <button className={`btn sm ${follow ? 'active' : ''}`} title="Camera follows the strongest divergence from baseline" onClick={() => set({ followConsequences: !follow, selection: null })}>follow consequences</button>
          </>
        )}
        <button className={`btn sm ${watch ? 'active' : ''}`} onClick={() => set({ watch: !watch, selection: null })}>watch</button>
        <button className="btn sm ghost" onClick={() => set({ debug: !useStore.getState().debug })}>dev</button>
      </div>
    </div>
  )
}

export async function play(p: { playing?: boolean; speed?: number; steps?: number; until_month?: number }) {
  const st = await api('/play', p)
  // A pure speed change is a preference for whenever simulation next runs forward — it shouldn't yank
  // the view off whatever month you're currently replaying. playing/steps/until_month all mean "advance
  // the live simulation now", so those jump the view back to it as before.
  const jumpsToLive = p.playing !== undefined || p.steps !== undefined || p.until_month !== undefined
  useStore.setState(jumpsToLive ? { status: st, viewMonth: null } : { status: st })
}
