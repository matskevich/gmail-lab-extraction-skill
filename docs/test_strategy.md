# test strategy

this repo needs 3 test layers. one layer is not enough.

## layer 1: static contract checks

run on every code change:

```bash
./scripts/doctor.sh
```

goal:
- syntax ok
- required local binaries visible
- chrome cdp lane reachable when a live session is expected

## layer 2: live regression corpus

run against a real mailbox with known historical cases:

```bash
./scripts/run_gmail_discovery.sh ./examples/regression_targets.tsv
./scripts/run_regression_suite.sh ./examples/regression_targets.tsv
```

for real operator validation, keep the actual mailbox corpus in a gitignored local file such as `tmp/private_regression_targets.tsv`; `examples/regression_targets.tsv` should stay sanitized.

the regression run writes:
- `regression_manifest.tsv` for threshold pass/fail
- `regression_summary.tsv` for one-line per-case operator truth: opened thread, landed files, and filtered inline noise

regression target columns:
- `query`
- `needle`
- `mode`
- `min_attachments`
- `min_inline`
- `note`

goal:
- first assert that the thread is discovered with the correct class
- assert that known historical cases still land the minimum expected raw assets
- assert that the runner does not silently open the wrong gmail thread

minimum corpus classes:

1. ready native attachment
- example class: old lab PDF already fully hydrated

2. partial-ready mail with attachment below the fold
- example class: old partial result mail where attachment controls hydrate late

3. virus-scan delayed attachment
- example class: Gmail shows `Scanning for viruses...` before `download_url` appears

4. inline-only medical image thread
- example class: body-rendered JPG results with no real PDF attachment

5. mixed thread
- both a real PDF attachment and inline noise/banners are present

6. portal-only provider mail
- discovery hit exists, but gmail-only collector should not pretend success

## layer 3: truth-layer reconciliation

after live regression passes, check:
- is the artifact in `raw/`?
- is enrichment status truthful?
- was the medically relevant artifact promoted or intentionally left as superseded/context-only?

goal:
- avoid the class of bug where the mailbox contains the evidence but downstream truth says it does not exist

private health oracle validation:

```bash
./scripts/build_health_validation_corpus.py --inventory /path/to/private_inventory.tsv --out-dir ./tmp/health-full-validation-YYYYmmdd
./scripts/run_gmail_discovery.sh ./tmp/health-full-validation-YYYYmmdd/gmail_targets.tsv ./tmp/health-full-validation-YYYYmmdd/discovery
./scripts/run_regression_suite.sh ./tmp/health-full-validation-YYYYmmdd/regression_targets.tsv ./tmp/health-full-validation-YYYYmmdd/regression
./scripts/run_gmail_lab_export.sh ./tmp/health-full-validation-YYYYmmdd/gmail_targets.tsv ./tmp/health-full-validation-YYYYmmdd/export
PORTAL_PATIENT_HINT='<last-name>' ./scripts/run_portal_lab_export.sh ./tmp/health-full-validation-YYYYmmdd/portal_targets.tsv ./tmp/health-full-validation-YYYYmmdd/portal
./scripts/audit_health_validation.py --oracle ./tmp/health-full-validation-YYYYmmdd/oracle.tsv --export-run ./tmp/health-full-validation-YYYYmmdd/export --portal-run ./tmp/health-full-validation-YYYYmmdd/portal --out ./tmp/health-full-validation-YYYYmmdd/coverage_report.md
```

this validates agent-consumable layout, not only browser acquisition:
- `oracle.tsv` states expected artifacts from the health truth layer
- `asset_manifest.tsv` states raw/final promotion and metadata evidence
- `coverage_report.md` states pass/debt by provider, lane, and order group

portal operator-hint rule:
- ask for a repeated patient gate value once per run, not once per provider tab
- prefer `PORTAL_PATIENT_HINT` or the one-time tty prompt over duplicating the same value into every target row
- close provider tabs after each row; a batch runner should leave Gmail usable after completion

## failure interpretation

- `extract_fail`
  - acquisition problem

- `assert_fail`
  - regression corpus says the extractor found too little

- `missing_dependency`
  - environment problem in OCR/PDF-text lane

- `pass`
  - minimum expected raw assets landed

## pragmatic rule

do not trust one happy-path smoke run.

historical recovery needs at least one regression target from each failure class above.

query authoring rule:
- if a sender-constrained query hides an old thread, prefer a broader order-id query over a flaky false negative
- but do not broaden so far that the needle becomes ambiguous across multiple conversations
