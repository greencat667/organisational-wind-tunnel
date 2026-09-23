import { STATIC } from './mode'
import { sim } from '../sim/client'

/** Calls the wind tunnel: the local server over HTTP, or — in the static build — the in-browser simulation. */
export async function api<T = any>(path: string, body?: any, method?: string): Promise<T> {
  const m = method || (body !== undefined ? 'POST' : 'GET')
  if (STATIC) return sim().request(m, path, body)
  const res = await fetch(`/api${path}`, {
    method: m,
    headers: { 'content-type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

/** Save an export to a file (works in both builds: there's no /api URL to link to in the static one). */
export async function download(path: string, filename: string) {
  let text: string
  if (STATIC) {
    const body = await sim().request('GET', path)
    text = typeof body === 'string' ? body : JSON.stringify(body, null, 2)
  } else {
    text = await (await fetch(`/api${path}`)).text()
  }
  const url = URL.createObjectURL(new Blob([text], { type: filename.endsWith('.csv') ? 'text/csv' : 'application/json' }))
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
