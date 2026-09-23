# Privacy

* **Synthetic by default.** The shipped organisations are generated from a seed; names are random combinations.
* **Fully local.** Simulation, the optional decision model (Laya) and the language model (Apple on-device) run on this
  machine. No telemetry, no analytics, no cloud calls. The frontend talks only to `127.0.0.1`.
* **Browser version** (`npm run build:static`, see HOSTING.md): the simulation runs in the visitor's own browser. The
  only network requests are for the page itself and, on first visit, the Pyodide runtime from the jsDelivr CDN; no
  simulation data leaves the browser. Saved experiments are kept in that browser's IndexedDB.
* **Local storage only.** `data/windtunnel.sqlite` (git-ignored) holds experiments, runs, events, decisions.
* **Import (planned):** CSV/JSON with anonymised identifiers; names are never required. Imported data stays local.
* **No claims about real people.** Employee variables are simulation parameters. The tool must not be used for
  performance assessment, HR scoring or automated employment decisions — see LIMITATIONS.md.
