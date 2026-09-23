// Loads Pyodide (Python compiled to WebAssembly) and the wind tunnel's Python package into a worker. The package's .py
// files are bundled into the build as text, so the static site needs nothing but itself and the Pyodide CDN.
export const PYODIDE_VERSION = '0.27.8'
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/pyodide.mjs`

// every module of the simulator except the server-only ones (FastAPI front end, the Laya adapter)
const SOURCES = import.meta.glob(
  ['../../../backend/windtunnel/**/*.py', '!../../../backend/windtunnel/server.py', '!../../../backend/windtunnel/decisions/laya_engine.py'],
  { query: '?raw', import: 'default', eager: true },
) as Record<string, string>

export async function loadWindTunnel(onProgress?: (msg: string) => void): Promise<any> {
  onProgress?.('Downloading Python (first visit only)…')
  const { loadPyodide } = await import(/* @vite-ignore */ PYODIDE_URL)
  const py = await loadPyodide({ indexURL: PYODIDE_URL.replace('pyodide.mjs', '') })
  onProgress?.('Loading libraries…')
  await py.loadPackage(['pydantic', 'sqlite3'])
  onProgress?.('Loading the simulator…')
  for (const [file, text] of Object.entries(SOURCES)) {
    const rel = file.split('/backend/')[1]            // windtunnel/…
    const dest = `/home/pyodide/${rel}`
    py.FS.mkdirTree(dest.slice(0, dest.lastIndexOf('/')))
    py.FS.writeFile(dest, text)
  }
  py.runPython('import sys; sys.path.insert(0, "/home/pyodide")')
  return py
}
