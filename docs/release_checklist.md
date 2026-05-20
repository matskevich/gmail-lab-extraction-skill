# release checklist

this repo is only ready for public alpha when all layers below are explicitly green.

## 1. local code gates

run inside the repo venv:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy gmail_lab
.venv/bin/python -m gmail_lab --help
```

required result:
- all commands pass

## 2. operator environment

run:

```bash
./scripts/doctor.sh
```

required result:
- required binaries are present
- chrome cdp is reachable when a live mailbox run is intended

important rule:
- `cdp down` with no clone running is operator state, not a product regression by itself

## 3. live mailbox regression

do not commit real mailbox targets.

keep the real corpus in a gitignored path such as:

```bash
tmp/private_regression_targets.tsv
```

run:

```bash
./scripts/run_gmail_discovery.sh ./tmp/private_regression_targets.tsv ./tmp/live-discovery
./scripts/run_regression_suite.sh ./tmp/private_regression_targets.tsv ./tmp/live-regression
```

required result:
- discovery finds every intended case
- regression lands the minimum expected raw assets
- the runner does not silently open the wrong gmail thread
- `regression_summary.tsv` stays reviewable by one agent without digging through every raw json log
- inline noise filtering does not hide the medically relevant artifact

query authoring rule:
- prefer the narrowest query that still reliably surfaces the correct row
- if a strict `from:` filter hides an old thread, prefer a broader order-id query over a false negative
- do not broaden so far that the needle becomes ambiguous across multiple threads
- treat an order id as a retrieval key, not freshness proof; a different hash can still be an alternate-language copy of an old result
- decide freshness from thread/provider/artifact dates plus `pdf_text_status`, then read `asset_manifest.tsv` before trusting `final/`

minimum real corpus before public alpha:
- old ready attachment
- old partial-ready attachment
- mixed attachment + inline noise
- at least one non-cmd provider
- at least one unicode or long-filename case

## 4. truth-layer reconciliation

after a live run, verify:
- `raw/` contains the landed evidence
- enrichment status is truthful
- the medically relevant artifact is identifiable without guessing from prose

required result:
- no case where discovery is green but downstream truth still looks absent or misleading

## truthful public label

if this checklist passes, the current honest label is:
- `agent-first self-hosted gmail lab export toolkit`
- `local-first evidence capture + metadata derivation`
- `browser/cdp live extraction today, gmail api first later`

unless `gmail api first` is implemented and separately verified, do not label the project as api-native production-ready.
