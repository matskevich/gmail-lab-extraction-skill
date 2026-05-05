# self-hosted product contract

this repo is being shaped as an agent-first self-hosted open-source toolkit.

the primary user is:
- another ai agent that needs a replayable, local filesystem + manifest contract
- an agent that should be able to inspect evidence and claims without hidden operator folklore

the secondary user is:
- a human operator who runs the tool locally against their own gmail
- a human who wants the raw evidence to stay on their own computer

## v1 promise

if the analysis artifact is reachable from the gmail surface, this toolkit should help the agent/operator pair:
- discover the relevant gmail thread
- land raw evidence locally in `raw/`
- keep logs and manifests for replayability
- derive metadata such as `analysis_date`, `owner`, and provider hints
- materialize canonical filenames in `final/`

for supported tokenized provider links, the toolkit may also land the result from the portal without manual browser clicks.

## local-first contract

the default operating model is:
- run on the operator's own machine
- store outputs on the operator's own disk
- do not require a hosted backend
- do not mutate mailbox state by default

current live extraction is still browser/cdp-first.

future direction:
- `gmail api first`
- browser/cdp fallback second

that future direction should improve reliability, but it does not change the local-first product boundary.

## what this repo should feel like

for the primary ai agent:
- read manifests first, raw files second, prose last
- consume explicit evidence + claims surfaces instead of reconstructing context from browser history
- keep weak or ambiguous metadata explicit

for the human operator:
- point the tool at a target corpus
- run extraction
- inspect `discovery_manifest.tsv`, `run_manifest.tsv`, `regression_summary.tsv`
- review `raw/`, `pdf_text/`, `ocr/`, and `final/`
- read manifests before trusting filenames in `final/`; `status=needs_review` means the raw file exists but the metadata is still too weak for downstream use

## explicit non-goals for v1

- hosted saas
- multi-tenant mailbox service
- arbitrary login-required portal automation
- silent mailbox mutation
- pretending every medical artifact in gmail is extractable

## truthful public label right now

- `agent-first self-hosted gmail lab export toolkit`
- `local-first evidence capture + metadata derivation`
- `gmail api native extraction first, browser/cdp fallback for rescue and UI-specific assets`

## release bar for open-source usefulness

before calling this repo broadly useful for self-hosting, it should be easy for a new agent/operator pair to:
1. install the tool on a local machine
2. run a small mailbox export without hidden setup folklore
3. understand what landed, what was filtered, and what is still uncertain from manifests alone
4. keep the outputs locally with reviewable metadata and provenance
