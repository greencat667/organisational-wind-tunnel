# Privacy

* **Synthetic by default.** The shipped organisations are generated from a seed; names are random combinations.
* **Fully local.** Simulation, decision models (Laya, Needle) and the language model (Apple on-device) run on this
  machine. No telemetry, no analytics, no cloud calls. The frontend talks only to `127.0.0.1`.
* **Local storage only.** `data/windtunnel.sqlite` (git-ignored) holds experiments, runs, events, decisions.
* **Import (planned):** CSV/JSON with anonymised identifiers; names are never required. Imported data stays local.
* **No claims about real people.** Employee variables are simulation parameters. The tool must not be used for
  performance assessment, HR scoring or automated employment decisions — see LIMITATIONS.md.
