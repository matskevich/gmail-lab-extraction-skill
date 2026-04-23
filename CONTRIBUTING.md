# contributing

thanks for helping improve the extractor. the fastest useful contribution is a small, redacted, reproducible case.

## before opening an issue

1. run `./scripts/doctor.sh`
2. run the failing command again with a fresh output directory under `tmp/`
3. inspect the relevant manifest:
   - `discovery_manifest.tsv`
   - `regression_manifest.tsv`
   - `run_manifest.tsv`
   - `asset_manifest.tsv`
   - `coverage_report.md`
4. redact personal data before sharing anything

## useful issue types

- bug report: a command failed, opened the wrong thread, missed assets, or wrote misleading manifests
- provider request: a lab/provider needs an adapter or parser
- help request: setup or run confusion
- feature request: a workflow improvement with a concrete output
- success case: provider/language/file type worked and can become a regression signal

## pull request rules

- keep collectors, provider adapters, enrichment, and metadata derivation separated
- preserve `raw/`; never rename raw evidence in place
- prefer new manifest statuses or fields over hidden behavior
- update schemas and docs when adding a status or column
- add tests for parser/status changes
- do not commit real mailbox targets, medical artifacts, cookies, tokens, or screenshots

## validation

run before opening a PR:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy gmail_lab
./scripts/doctor.sh
```

`doctor.sh` may report `cdp down` when no live Chrome clone is running. that is operator state, not a code failure by itself.

## adapter contributions

provider adapters should be small and explicit:

- input: provider page or artifact text
- output: raw file and manifest metadata
- failure: explicit status such as `needs_login`, `needs_patient_hint`, `needs_password_hint`, or `provider_fail`

do not add provider login or captcha automation to gmail-native collectors.
