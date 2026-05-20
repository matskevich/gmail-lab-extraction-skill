# Learning loop

This repo improves through live evidence, not through chat memory.

Every real mailbox run should leave one durable learning packet:

```text
live symptom -> classified failure class -> promoted artifact -> verification command
```

## Failure classes

Classify the first real blocker. Do not collapse layers.

| Class | Layer | Typical symptom | Promotion artifact |
| --- | --- | --- | --- |
| `auth/acquisition` | before raw bytes | `gmail_not_authenticated`, missing OAuth token, connector sees names but no bytes | auth router doc, CLI diagnostic, live acceptance target |
| `query/selection` | discovery | wrong thread, old result selected, duplicate subject/order id | private regression target plus query rule |
| `asset/hydration` | acquisition | Gmail UI shows attachment but `download_url_count=0` | browser collector fixture or live regression case |
| `connector/bytes` | acquisition | connector metadata works, attachment read fails | Gmail API lane or explicit connector boundary |
| `secret/pdf` | enrichment | encrypted PDF lands but text is blocked | `needs_password_hint` test or secret-resolution doc |
| `metadata/claims` | derivation | owner/date/provider plausible but weak | parser test plus manifest/schema update |
| `promotion/final` | materialization | stale or fallback-dated file appears final | promotion policy test |
| `operator/confusion` | agent workflow | agent asks for manual download too early or interprets before raw bytes | skill/doc/router patch |

## Promotion ladder

For every incident, promote exactly one primary artifact first:

1. **Run artifact**: keep the run directory with `run_manifest.tsv`, `asset_manifest.tsv`, logs, and raw evidence if available.
2. **Private regression target**: add a sanitized row to a gitignored file such as `tmp/private_regression_targets.tsv`.
3. **Code test**: add a fixture/unit/integration test when the behavior is reproducible without private mailbox access.
4. **Doc/skill rule**: update `START_HERE_FOR_AGENTS.md`, `skills/*/SKILL.md`, or a focused doc when the failure was agent routing.
5. **Schema/status**: add a typed manifest status when agents need a new machine-readable state.
6. **Public intake**: open a sanitized issue/discussion only after removing names, file contents, tokens, cookies, and raw medical data.

Private live corpus is for proof. Public docs are for patterns.

## Incident packet template

Keep private packets in `tmp/learning/` or a run-local note. Do not commit private packets.

```markdown
# live learning packet

date:
provider:
case id: redacted/stable local alias

## observed

- command:
- run dir:
- first blocker:
- exact status:

## layer

- discovery/acquisition/enrichment/claims/promotion/operator:

## why it happened

- verified:
- inferred:
- unresolved:

## promotion

- private regression target:
- code test:
- doc/skill patch:
- schema/status change:

## verification

- static:
- live:
- residual risk:
```

## Weekly operating rhythm

Run this after a cluster of live work, or at least before claiming the repo is more reliable:

```bash
./scripts/doctor.sh
gmail-lab diagnose-gmail-acquisition
python -m pytest
python -m ruff check .
python -m mypy gmail_lab
```

If mailbox auth is available:

```bash
./scripts/run_gmail_discovery.sh ./tmp/private_regression_targets.tsv ./tmp/live-discovery
./scripts/run_regression_suite.sh ./tmp/private_regression_targets.tsv ./tmp/live-regression
```

Then inspect:

- `tmp/live-regression/regression_manifest.tsv`
- `tmp/live-regression/regression_summary.tsv`
- new `extract_fail`, `needs_review`, `needs_password_hint`, or `missing_dependency` rows

## Rule for repeated failures

If the same failure class appears twice, do not only patch the local case.

Escalate one level:

- repeated operator confusion -> skill/router update
- repeated private live failure -> regression corpus expansion
- repeated parser miss -> fixture test and parser rule
- repeated untyped manifest state -> new status/column and schema docs
- repeated auth failure -> first-class onboarding/diagnostic command

## Current lesson from the repeated Prodia-style flow

The important recurring pattern is not the provider name. It is:

```text
new email can reuse an old filename/order id
and old final text can become stale
while browser fallback can fail before raw bytes
```

Therefore agents must:

1. compare message date and raw file hash before trusting an older final artifact;
2. prove raw bytes landed before interpreting a result;
3. treat `gmail_not_authenticated` as auth/acquisition, not PDF extraction;
4. promote duplicate-name/addendum cases into private regression targets.
