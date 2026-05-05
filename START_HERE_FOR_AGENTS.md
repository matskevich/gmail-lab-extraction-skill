# Start Here For Agents

read this file first.

## current status

- green:
  - python substrate under `gmail_lab/`
  - `state.db`, message archive, evidence archive
  - `discovery_manifest.tsv`, `evidence_manifest.tsv`, `claims_manifest.tsv`, `analysis_manifest.tsv`
  - gmail api native attachment acquisition via `scripts/run_gmail_api_export.py`
  - claims derivation for `owner`, `analysis_date`, `sample_draw_*`
  - invitro anonymous portal export
  - password-hinted pdf text lane
- yellow:
  - gmail api discovery/acquisition needs more live corpus coverage
  - browser historical completeness is only proven on a narrow live smoke corpus
  - live collector regression stability across delayed attachment hydration
- red:
  - generic provider login automation is not implemented

## read order

1. `README.md`
2. `AGENTS.md`
3. `docs/agent_install.md`
4. `docs/google_api_setup.md`
5. `docs/acquisition_auth_router.md`
6. `docs/api_first_architecture.md`
7. `docs/self_hosted_product.md`
8. `docs/agent_first_roadmap.md`
9. `docs/completeness_framework.md`
10. `docs/test_strategy.md`
11. `docs/release_checklist.md`
12. `docs/release_verdict.md`
13. `PRIVACY.md`
14. `CONTRIBUTING.md`
15. `SUPPORT.md`
16. `ROADMAP.md`
17. `docs/community_intake.md`
18. `schemas/*.schema.json`

## canonical truths

- product boundary first:
  - primary user is another ai agent
  - self-hosted
  - local-first
  - operator owns raw evidence on disk
- evidence first:
  - `raw/`
  - message archive
  - evidence archive
- claims second:
  - `claims_manifest.tsv`
  - `analysis_manifest.tsv`
- do not infer product state from prose only

## primary commands

```bash
./scripts/doctor.sh
python -m gmail_lab --help
gmail-lab diagnose-gmail-acquisition
python -m pytest
python -m ruff check .
python -m mypy gmail_lab
```

## agent packaging

- Codex workflow skill: `skills/gmail-lab-export`
- Codex CDP helper skill: `skills/gmail-browser-attachments`
- Claude Code project skill: `.claude/skills/gmail-lab-export`
- install/use map: `docs/agent_install.md`

for live browser runs:

```bash
./scripts/run_gmail_discovery.sh ./examples/targets.tsv
./scripts/run_regression_suite.sh ./examples/regression_targets.tsv
```

after a live regression run, inspect `regression_summary.tsv` before claiming the suite was both green and clean.

for Gmail API native attachment acquisition:

```bash
gmail-lab auth-google --client-secrets /path/to/oauth-client.json
gmail-lab google-auth-status
gmail-lab export-gmail-api ./tmp/private_targets.tsv ./runs/gmail-api-run
```

this uses `gmail.readonly`, writes native attachments to `raw/`, writes `evidence_manifest.tsv`, and reuses the existing pdf text/password lane. browser/CDP remains fallback for auth-broken rescue and ui-specific bugs.

do not pass Gmail web UI URLs like `https://mail.google.com/.../#inbox/FMfc...` as API locators. use a Gmail search query or a real Gmail API `message:<id>` / `thread:<id>`.

if browser/CDP returns `gmail_not_authenticated`, the fallback has no authenticated mailbox surface. use Gmail API, or start `skills/gmail-browser-attachments/scripts/start_chrome_cdp_profile.sh` and log into Gmail in that persistent profile once.

for the private end-to-end health oracle check, generate gitignored targets from the local health inventory and audit coverage:

```bash
./scripts/build_health_validation_corpus.py --inventory /path/to/private_inventory.tsv --out-dir ./tmp/health-full-validation-YYYYmmdd
PORTAL_PATIENT_HINT='<last-name>' ./scripts/run_portal_lab_export.sh ./tmp/health-full-validation-YYYYmmdd/portal_targets.tsv ./tmp/health-full-validation-YYYYmmdd/portal
./scripts/audit_health_validation.py --oracle ./tmp/health-full-validation-YYYYmmdd/oracle.tsv --export-run ./tmp/health-full-validation-YYYYmmdd/export --portal-run ./tmp/health-full-validation-YYYYmmdd/portal --out ./tmp/health-full-validation-YYYYmmdd/coverage_report.md
```

for substrate / claims:

```bash
gmail-lab init
gmail-lab identity-status
gmail-lab derive-claims
gmail-lab emit-claims-manifest --output ./claims_manifest.tsv
gmail-lab emit-analysis-manifest --output ./analysis_manifest.tsv
```

## known sharp edge

historical cmd threads can still regress into inline-only extraction when gmail attachment controls hydrate late. do not claim completeness from one happy-path smoke run.

when reconciling staged result emails from the same provider/order, do not rely on a broad query plus one `final/` artifact. split by email date/subject, compare attachment hashes, and preserve superseded partials as provenance. if multiple source PDFs share the same filename, retrying `extract_pdf_text.py` into one output directory can overwrite text outputs; use per-slug output directories before diffing.

## immediate next work

1. validate gmail api native acquisition on live private corpus
2. promote api-native discovery into the packaged agent workflow
3. add a live tokenized portal corpus case
4. keep browser lane as fallback and regression oracle

## release rule

- public examples stay sanitized
- real mailbox regression targets stay in a gitignored local file such as `tmp/private_regression_targets.tsv`
- before claiming public-alpha readiness, run [docs/release_checklist.md](docs/release_checklist.md)

## community intake rule

- issues are actionable work
- discussions are open-ended questions, ideas, and success/failure patterns
- never ask users to upload raw medical files, portal keys, cookies, tokens, or unredacted manifests
- map every issue to one lane: discovery, acquisition, enrichment, metadata, promotion, portal adapter, or docs/onboarding
- use `docs/community_intake.md` as the label and triage contract
