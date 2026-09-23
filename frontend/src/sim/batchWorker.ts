// A batch worker: its own Python, running one baseline/intervention world pair per message (no rendering). The page
// keeps a small pool of these so "many worlds" uses several cores.
import { loadWindTunnel } from './pyodide'

let wt: any = null
const ready = loadWindTunnel().then((py) => { wt = py.pyimport('windtunnel.browser') })

self.onmessage = async (e: MessageEvent) => {
  const { id, args } = e.data
  try {
    await ready
    ;(self as any).postMessage({ id, result: JSON.parse(wt.run_one(JSON.stringify(args))) })
  } catch (err: any) {
    ;(self as any).postMessage({ id, error: String(err?.message || err) })
  }
}
