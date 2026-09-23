# Hosting the browser version

The wind tunnel has two builds from the same code:

| | Local server (`./windtunnel.sh`) | Browser version (`npm run build:static`) |
|---|---|---|
| Where the simulation runs | Python on your machine (FastAPI) | Python in the visitor's browser (Pyodide, WebAssembly) |
| Needs | Python 3.11 + Node | nothing — any static host |
| Decision engines | rules, Laya | rules |
| Intervention parser | rules, Apple on-device model | rules |
| Many-worlds batches | a process pool | a pool of Web Workers (up to 4 cores) |
| Saved experiments | `data/windtunnel.sqlite` | the browser's IndexedDB (per browser, per site) |

Everything else — the organisation, the physics, analysis, WHY chains, saves and forks — is the same Python package.
`windtunnel/service.py` holds all of it; `server.py` (FastAPI) and `browser.py` (Pyodide) are thin front ends.

## Build and try it locally

```bash
cd frontend
npm run build:static        # → frontend/dist-static (≈2 MB; Python itself comes from the Pyodide CDN)
npm run preview:static      # → http://127.0.0.1:5182
npm run smoke:static        # end-to-end test of the built site (boots Python, runs a change, a batch, a save)
```

`npm run dev:static` runs the browser version with hot reload.

## Publish it

**Cloudflare Pages** (free): create a Pages project connected to the repository with build command
`cd frontend && npm ci && npm run build:static` and output directory `frontend/dist-static`.

**GitHub Pages** (free for public repositories): enable Pages with *Settings → Pages → Source: GitHub Actions*, then run
the **Deploy browser version to GitHub Pages** workflow from the Actions tab. It only runs when started by hand.

Any other static host works too: upload the contents of `frontend/dist-static`. Assets use relative paths, so the site
can live at a sub-path.

## What to expect

* **First visit** downloads Python and its libraries from the jsDelivr CDN (about 10 MB) and caches them; later visits
  start in a few seconds. The page shows a loading card meanwhile.
* **Speed**: WebAssembly Python is roughly 2–3× slower than native. A 100-person month takes about 0.1–0.3 s per world on
  a laptop, so normal play is smooth, "+3 yrs" takes a few seconds, and a 24-world batch a minute or two. The default
  batch size is 24 in this build (200 on the local server).
* **Every visitor has their own organisation**, running on their own machine: nothing is shared between visitors and
  nothing is sent to any server. Saved experiments stay in that browser.
* The 500-person organisation works but is noticeably slower; batches of it are best run on the local server.
