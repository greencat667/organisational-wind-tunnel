// The page's side of the browser build: stands in for fetch('/api/…') and the WebSocket. Requests go to the simulation
// worker; "many worlds" batches are fanned out to a pool of batch workers and the results handed back to the service.
type Listener = (msg: any) => void

class SimClient {
  private worker: Worker
  private seq = 0
  private pending = new Map<number, { resolve: (v: any) => void; reject: (e: any) => void }>()
  private listeners = new Set<Listener>()
  private readyPromise: Promise<void>
  private pool: Worker[] = []
  boot: { state: 'loading' | 'ready' | 'error'; msg: string } = { state: 'loading', msg: 'Starting…' }
  onBoot: (b: SimClient['boot']) => void = () => {}

  constructor() {
    this.worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })
    let markReady: () => void = () => {}
    let markFailed: (e: any) => void = () => {}
    this.readyPromise = new Promise((res, rej) => { markReady = res; markFailed = rej })
    this.worker.onmessage = (e) => {
      const m = e.data
      if (m.kind === 'progress') this.setBoot({ state: 'loading', msg: m.msg })
      else if (m.kind === 'ready') { this.setBoot({ state: 'ready', msg: '' }); markReady() }
      else if (m.kind === 'error') { this.setBoot({ state: 'error', msg: m.msg }); markFailed(new Error(m.msg)) }
      else if (m.kind === 'event') this.listeners.forEach((l) => l(m.msg))
      else if (m.kind === 'reply') {
        const p = this.pending.get(m.id)
        if (!p) return
        this.pending.delete(m.id)
        if (m.status >= 400) p.reject(new Error(`${m.status} ${m.body?.detail ?? ''}`))
        else p.resolve(m.body)
      }
    }
  }

  private setBoot(b: SimClient['boot']) { this.boot = b; this.onBoot(b) }

  private call(msg: any): Promise<any> {
    const id = ++this.seq
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.worker.postMessage({ id, ...msg })
    })
  }

  onEvent(l: Listener) { this.listeners.add(l); return () => this.listeners.delete(l) }

  async request(method: string, pathWithQuery: string, body?: any): Promise<any> {
    await this.readyPromise
    const [path, qs] = pathWithQuery.split('?')
    const query = Object.fromEntries(new URLSearchParams(qs || ''))
    if (method === 'POST' && path === '/batch') return this.startBatch(body)
    return this.call({ op: 'request', method, path, query, body })
  }

  /** Prepare the batch in the simulation worker, run its worlds across the pool, then hand the results back. */
  private async startBatch(body: any) {
    const prep = await this.call({ op: 'batch_prepare', body })
    const { job_id, args } = prep
    const size = Math.max(1, Math.min(4, (navigator.hardwareConcurrency || 2) - 1))
    while (this.pool.length < size) this.pool.push(new Worker(new URL('./batchWorker.ts', import.meta.url), { type: 'module' }))
    const t0 = performance.now()
    const results: any[] = []
    let next = 0
    let failed: string | null = null
    const runOn = (w: Worker) => new Promise<void>((resolve) => {
      const go = () => {
        if (failed || next >= args.length) return resolve()
        const i = next++
        w.onmessage = (e) => {
          if (e.data.error) failed = e.data.error
          else results.push(e.data.result)
          this.call({ op: 'batch_progress', jobId: job_id, done: results.length })
          this.listeners.forEach((l) => l({ type: 'batch', job: { id: job_id, status: 'running', done: results.length, n: args.length } }))
          go()
        }
        w.postMessage({ id: i, args: args[i] })
      }
      go()
    })
    Promise.all(this.pool.map(runOn)).then(() =>
      this.call({ op: 'batch_finish', jobId: job_id, results: failed ? [] : results, error: failed, elapsed: (performance.now() - t0) / 1000 }))
    return { job_id }
  }
}

let client: SimClient | null = null
export function sim(): SimClient {
  if (!client) client = new SimClient()
  return client
}
