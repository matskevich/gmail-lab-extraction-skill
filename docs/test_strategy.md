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

minimum corpus classes:

1. ready native attachment
- example class: old lab PDF already fully hydrated

2. partial-ready mail with attachment below the fold
- example class: old CMD partial result mail such as `DCKY28207`

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
