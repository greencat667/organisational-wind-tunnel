import { useEffect } from 'react'
import { Scene } from './scene/Scene'
import { connect, useStore } from './lib/store'
import { TopBar } from './ui/TopBar'
import { Bottom } from './ui/Bottom'
import { LeftPanel } from './ui/LeftPanel'
import { RightPanel } from './ui/RightPanel'
import { InterpretModal } from './ui/InterpretModal'
import { DebugPanel } from './ui/DebugPanel'
import { WatchCaption } from './ui/WatchCaption'
import { Tooltip } from './ui/Tooltip'

export default function App() {
  const init = useStore((s) => s.init)
  const watch = useStore((s) => s.watch)
  const debug = useStore((s) => s.debug)
  const interpret = useStore((s) => s.interpret)
  useEffect(() => { let alive = true; const go = () => init().then(() => alive && connect()).catch(() => alive && setTimeout(go, 1500)); go(); return () => { alive = false } }, [])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT' || (e.target as HTMLElement)?.tagName === 'TEXTAREA') return
      if (e.key === 'w') useStore.setState({ watch: !useStore.getState().watch })
      if (e.key === 'd') useStore.setState({ debug: !useStore.getState().debug })
      if (e.key === 'Escape') useStore.setState({ watch: false, selection: null, whyEvent: null })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  return (
    <div className="app">
      <div className="canvas-wrap"><Scene /></div>
      <TopBar />
      {!watch && <LeftPanel />}
      {!watch && <RightPanel />}
      {!watch && <Bottom />}
      {watch && <WatchCaption />}
      {debug && <DebugPanel />}
      <Tooltip />
      {interpret && <InterpretModal />}
      <div className="notice">Exploratory organisational simulation — not a prediction of employee behaviour or organisational outcomes. Synthetic organisation. Runs entirely on this machine.</div>
    </div>
  )
}
