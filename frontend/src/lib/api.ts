export async function api<T = any>(path: string, body?: any, method?: string): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: method || (body !== undefined ? 'POST' : 'GET'),
    headers: { 'content-type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}
