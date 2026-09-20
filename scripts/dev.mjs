// One-command launch (Node): backend (FastAPI :8765) + frontend (Vite :5180). Used by `npm run dev` in frontend/.
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const py = path.join(root, '.venv', 'bin', 'python')
if (!existsSync(py)) { console.error(`No venv at ${py}. Run: uv venv --python 3.11 .venv && uv pip install -r backend/requirements.txt`); process.exit(1) }
const env = { ...process.env, WINDTUNNEL_ENGINE: process.env.WINDTUNNEL_ENGINE || 'heuristic', WINDTUNNEL_TEMPLATE: process.env.WINDTUNNEL_TEMPLATE || 'prototype', WINDTUNNEL_SEED: process.env.WINDTUNNEL_SEED || '7' }
const back = spawn(py, ['-m', 'uvicorn', 'windtunnel.server:app', '--host', '127.0.0.1', '--port', '8765', '--log-level', 'warning'], { cwd: path.join(root, 'backend'), env, stdio: 'inherit' })
console.log(`backend  → http://127.0.0.1:8765 (engine=${env.WINDTUNNEL_ENGINE}, template=${env.WINDTUNNEL_TEMPLATE}, seed=${env.WINDTUNNEL_SEED})`)
const vite = spawn(path.join(root, 'frontend', 'node_modules', '.bin', 'vite'), ['--host', '127.0.0.1', '--port', '5180', '--strictPort'], { cwd: path.join(root, 'frontend'), env, stdio: 'inherit' })
const stop = () => { back.kill(); vite.kill(); process.exit(0) }
process.on('SIGINT', stop); process.on('SIGTERM', stop)
back.on('exit', (c) => { if (c && c !== 0) { console.error('backend exited', c); stop() } })
vite.on('exit', (c) => stop())
