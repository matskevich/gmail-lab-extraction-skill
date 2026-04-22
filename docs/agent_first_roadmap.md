# agent-first roadmap

this file tracks what is still missing before the repo can honestly be described as a broadly useful self-hosted open-source toolkit for other ai agents.

## product contour

- primary user: another ai agent
- secondary user: a human operator running the tool locally against their own gmail
- product boundary: self-hosted, local-first, evidence-preserving

## what is already green

- browser/cdp extraction for gmail-native attachments
- browser/cdp extraction for gmail inline image assets
- OCR lane for image assets
- password-hinted PDF text extraction
- claims layer for `analysis_date`, `owner`, `sample_draw_*`
- manifests for discovery, evidence, claims, analyses
- live smoke corpus with correct thread routing on real mailbox cases
- regression operator summary via `regression_summary.tsv`

## what is still missing

### 1. broader live corpus

the current live proof is still narrow.

missing corpus classes to keep locally in `tmp/private_regression_targets.tsv`:
- inline-only medical thread
- portal-only thread
- mixed noisy thread from more than one provider
- at least one more non-cmd provider beyond the current smoke set
- long-filename or unicode-heavy edge cases
- a case where gmail search is only stable with a broader order-id query

### 2. first-run onboarding

a new agent/operator should not need repo folklore to do the first useful run.

still missing:
- one obvious first-run path with the minimum setup ritual
- one small private target template beyond the sanitized examples
- one explicit explanation of how to read `run_manifest.tsv`, `asset_manifest.tsv`, and `regression_summary.tsv` together

### 3. api-native lane

current live extraction is still browser/cdp-first.

still missing:
- gmail api discovery
- gmail api acquisition of MIME parts and `attachmentId` payloads
- replay of existing enrichment/claims layers on api-native evidence

### 4. stronger metadata quality

still missing:
- more provider-specific date parsers
- stronger owner confirmation beyond thread/title heuristics
- clearer handling of ambiguous non-owner/context-only cases

## what to test next

## a. live regression expansion

run:

```bash
./scripts/run_gmail_discovery.sh ./tmp/private_regression_targets.tsv ./tmp/live-discovery
./scripts/run_regression_suite.sh ./tmp/private_regression_targets.tsv ./tmp/live-regression
```

review:
- `./tmp/live-discovery/discovery_manifest.tsv`
- `./tmp/live-regression/regression_manifest.tsv`
- `./tmp/live-regression/regression_summary.tsv`

look for:
- wrong-thread routing
- missing medically relevant artifact
- filtered noise hiding the real artifact
- discovery green but acquisition misleading

## b. first-run operator path

test with a fresh small target file:
- can a new agent follow only README + `docs/self_hosted_product.md`?
- can it reach a green first run without tribal knowledge?
- can it explain the outputs from manifests alone?

## c. enrichment truth

after live runs, inspect:
- `raw/`
- `ocr/`
- `pdf_text/`
- `final/`
- `asset_manifest.tsv`

look for:
- wrong `analysis_date` source
- weak owner presented as strong owner
- medically relevant artifact lost among duplicates or noise

## what to build next

1. expand the private live corpus and keep it green
2. add a first-run onboarding artifact for new agents/operators
3. implement gmail api native discovery/acquisition
4. replay current claims/manifests on top of api-native evidence

## truthful status right now

this repo is ready as `browser-first self-hosted alpha` for agent-operated gmail-native lab export.

it is not yet `api-first beta`, universal portal automation, or a hosted product.
