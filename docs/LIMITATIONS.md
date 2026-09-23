# Limitations

**This is an exploratory organisational simulation, not a prediction of employee behaviour or organisational outcomes.**

Use it for: hypothesis generation · second-order thinking · stress testing · scenario exploration · identifying
dependencies · surfacing unexpected possibilities.

Do not use it for: predicting specific employees · performance assessment · HR scoring · automated employment decisions.

## Known limitations
* Parameters are plausible, not estimated from data; nothing is validated against a real organisation.
* Frequencies from batch runs are frequencies *within this model*, not real-world probabilities.
* Small decision models are biased by question/tool wording (documented in LAYA.md); calibration and
  guards reduce but do not remove this. Compare engines rather than trusting one.
* Employees are one-dimensional agents with ~10 actions; real behaviour is richer and stranger.
* Outcomes depend far more on organisational physics than on individual choices: swapping the rules for Laya changed
  86% of decisions but hardly moved the results (see VALIDATION.md). Individual actions may be too weakly coupled.
* Work is modelled as hours; quality, creativity and relationships are only crudely represented.
* The Apple model can mis-read an intervention; always check the interpreted plan before running (RUN / EDIT / CANCEL).
  The rule-based parser handles one change per clause ("cut X and hire Y"), negations and protection clauses, and says
  what it couldn't read rather than guessing; outsourcing, relocation, hybrid working and start dates aren't modelled.
* Manager roles are sized once, for the team as designed. A merge therefore leaves one manager's time spread over both
  teams (realistic for a straight merge, harsh if the role would in practice be regraded); edit the plan or add capacity
  to model a resized role.
* AI supervision cost (12 h per agent-month, i.e. ~10% of agent output) is a plausible guess, not a measured figure; it
  decides how easily staff keep up. Sweep it (`--sweep ai_supervision_hours=12,24,36`) rather than trusting the default.
* AI engines are slow (~0.3 s per decision); the interactive cap of 24 decisions/month changes which agents get to decide.
* Projects, suppliers and resources exist only implicitly (as processes and budgets).
* Import of real organisations is not built yet.
