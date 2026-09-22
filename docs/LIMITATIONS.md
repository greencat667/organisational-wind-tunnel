# Limitations

**This is an exploratory organisational simulation, not a prediction of employee behaviour or organisational outcomes.**

Use it for: hypothesis generation · second-order thinking · stress testing · scenario exploration · identifying
dependencies · surfacing unexpected possibilities.

Do not use it for: predicting specific employees · performance assessment · HR scoring · automated employment decisions.

## Known limitations
* Parameters are plausible, not estimated from data; nothing is validated against a real organisation.
* Frequencies from batch runs are frequencies *within this model*, not real-world probabilities.
* Small decision models are biased by question/tool wording (documented in LAYA.md and NEEDLE.md); calibration and
  guards reduce but do not remove this. Compare engines rather than trusting one.
* Employees are one-dimensional agents with ~10 actions; real behaviour is richer and stranger.
* Work is modelled as hours; quality, creativity and relationships are only crudely represented.
* The Apple model can mis-read an intervention; always check the interpreted plan before running (RUN / EDIT / CANCEL).
  The rule-based parser handles one change per clause ("cut X and hire Y"), negations and protection clauses, and says
  what it couldn't read rather than guessing; outsourcing, relocation, hybrid working and start dates aren't modelled.
* Known modelling gaps (found in the September 2026 review, not yet changed): management load carries a flat +0.5 offset
  and approval hours share the manager's line-management time, so cutting officers also cuts approval capacity; with the
  default settings AI supervision never runs short, so the supervision-gap paths are rarely exercised; vacancies blocked
  during a hiring freeze aren't reopened when it lifts.
* AI engines are slow (~0.3 s per decision); the interactive cap of 24 decisions/month changes which agents get to decide.
* Projects, suppliers and resources exist only implicitly (as processes and budgets).
* Import of real organisations is not built yet.
