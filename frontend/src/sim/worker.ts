// The simulation worker: one Python service, driven by requests from the page and by its own play loop. Messages the
// service emits (frames, status, forked, batch) are forwarded to the page just as the server's WebSocket would.
import { loadWindTunnel } from './pyodide'

const post = (m: any) => (self as any).postMessage(m)
let wt: any = null
let py: any = null

async function syncToDisk() {
  // saved experiments live in IndexedDB so they survive reloads
  await new Promise<void>((res) => py.FS.syncfs(false, () => res()))
}

function forward(reply: any) {
  for (const ev of reply.events || []) post({ kind: 'event', msg: ev })
}

async function boot() {
  try {
    py = await loadWindTunnel((m) => post({ kind: 'progress', msg: m }))
    py.FS.mkdirTree('/persist')
    py.FS.mount(py.FS.filesystems.IDBFS, {}, '/persist')
    await new Promise<void>((res) => py.FS.syncfs(true, () => res()))
    post({ kind: 'progress', msg: 'Building the organisation…' })
    wt = py.pyimport('windtunnel.browser')
    forward(JSON.parse(wt.init('/persist/windtunnel.sqlite', 1000)))
    post({ kind: 'ready' })
    loop()
  } catch (e: any) {
    post({ kind: 'error', msg: String(e?.message || e) })
  }
}

async function loop() {
  while (true) {
    let wait = 0.05
    try {
      const r = JSON.parse(wt.tick())
      forward(r)
      wait = r.wait
    } catch (e) {
      post({ kind: 'event', msg: { type: 'status_error', error: String(e) } })
    }
    await new Promise((res) => setTimeout(res, Math.max(0, wait * 1000)))
  }
}

self.onmessage = async (e: MessageEvent) => {
  const { id, op, method, path, query, body, jobId, done, results, error, elapsed } = e.data
  try {
    let r: any
    if (op === 'request') r = JSON.parse(wt.request(method, path, JSON.stringify(query || {}), JSON.stringify(body ?? null)))
    else if (op === 'batch_prepare') r = JSON.parse(wt.batch_prepare(JSON.stringify(body || {})))
    else if (op === 'batch_progress') r = JSON.parse(wt.batch_progress(jobId, done))
    else if (op === 'batch_finish') r = JSON.parse(wt.batch_finish(jobId, JSON.stringify(results || []), error || '', elapsed || 0))
    forward(r)
    if (op === 'batch_finish' || (op === 'request' && method !== 'GET')) await syncToDisk()
    post({ kind: 'reply', id, status: r.status ?? 200, body: r.body })
  } catch (err: any) {
    post({ kind: 'reply', id, status: 500, body: { detail: String(err?.message || err) } })
  }
}

boot()
