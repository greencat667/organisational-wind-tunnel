# Apple Foundation Models

## Role
Interpret the user's natural-language intervention into a **validated, flat change plan**, and write short plain-English
summaries of *observed* results when asked. It never decides what happens in the organisation.

## Path used: Apple's `fm` CLI (macOS 27, `/usr/bin/fm`)
```bash
fm available                          # "System model available"
fm serve --port 17976                 # OpenAI-style Chat Completions server, loopback only
```
```json
POST /v1/chat/completions
{"model":"system","messages":[{"role":"system","content":"…"},{"role":"user","content":"Requested change: …"}],
 "response_format":{"type":"json_schema","json_schema":{"name":"ChangePlan","schema":{…flat JSON schema…}}}}
```
The backend starts `fm serve` on demand (`interventions/parser.py: FMServer`) and parses the streamed or unstreamed
reply. Guided generation guarantees well-formed JSON; `schema.validate_plan()` then enforces enums, ranges and
percent→fraction coercion with pydantic, and `_reconcile()` makes explicitly stated percentages and protected groups
in the text win over the model.

Alternatives evaluated: the official `apple-fm-sdk` Python package (needs Xcode to build its Swift bindings) and the
community Swift server `apple-fm-serve` (works, 8192-token context, but a second binary to build). `fm serve` needs nothing.

## Measured
* Flat schema (12 fields, enum operations): **1.1–1.5 s** per interpretation, 84→77 tokens.
* Context window 4096 tokens (8192 on macOS 27); our prompt is ~400 tokens.

## Pitfall: nested schemas hang
A schema with an **array of objects** (`changes: [{operation, target, amount…}]`) never returned — requests hung for
minutes and, because the on-device model service is a single machine-wide queue, blocked *every* caller (including
`fm respond`) until the queue drained (~8 minutes). The plan schema is therefore flat: two change slots
(`operation_1/target_1/amount_percent_1/detail_1`, `operation_2/…`) plus comma-separated `protected_groups`.
The parser probes the server with a tiny request (6 s timeout, cached 60 s) before asking for guided output and falls
back to the rule-based parser on any failure; the UI shows which source produced the plan.

## Explanations
`/api/explain` sends observed numbers/events and asks for ≤120 words, instructed not to add causes that are not listed
and to refer to "the simulation". Output is shown verbatim with its source.
