# Start Here For Agents

read this file first.

## current status

- green:
  - python substrate under `gmail_lab/`
  - `state.db`, message archive, evidence archive
  - `discovery_manifest.tsv`, `evidence_manifest.tsv`, `claims_manifest.tsv`, `analysis_manifest.tsv`
  - claims derivation for `owner`, `analysis_date`, `sample_draw_*`
  - invitro anonymous portal export
  - password-hinted pdf text lane
- yellow:
  - browser historical completeness is only proven on a narrow live smoke corpus
  - live collector regression stability across delayed attachment hydration
- red:
  - gmail api native discovery/acquisition is not implemented yet
  - generic provider login automation is not implemented

## read order

1. `README.md`
2. `AGENTS.md`
3. `docs/agent_install.md`
4. `docs/api_first_architecture.md`
5. `docs/self_hosted_product.md`
6. `docs/agent_first_roadmap.md`
7. `docs/completeness_framework.md`
8. `docs/test_strategy.md`
9. `docs/release_checklist.md`
10. `docs/release_verdict.md`
11. `PRIVACY.md`
12. `CONTRIBUTING.md`
13. `SUPPORT.md`
14. `ROADMAP.md`
15. `docs/community_intake.md`
16. `schemas/*.schema.json`

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

## immediate next work

1. implement gmail api native discovery/acquisition
2. replay current enrichment/promotion on api-native evidence
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
