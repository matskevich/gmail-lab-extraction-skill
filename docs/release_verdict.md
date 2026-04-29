# release verdict

date: 2026-04-21

## verdict

`browser-first self-hosted alpha` is ready.

meaning:
- another ai agent can run the repo locally against a Gmail mailbox
- Gmail-native lab/result attachments can be discovered, acquired, enriched, and promoted into `final/`
- raw evidence remains preserved under `raw/`
- metadata is written into manifests instead of hidden in prose
- obvious non-result support attachments can remain in `raw/` without promotion to `final/`

## verified release gate

code gates:
- `.venv/bin/python -m pytest`
- `.venv/bin/python -m ruff check .`
- `.venv/bin/python -m mypy gmail_lab`
- `./scripts/doctor.sh`

live gates:
- discovery: `tmp/live-discovery-release-v3/discovery_manifest.tsv`
- regression: `tmp/live-regression-release-v3/regression_manifest.tsv`
- regression summary: `tmp/live-regression-release-v3/regression_summary.tsv`
- full export: `tmp/live-export-release-v3/run_manifest.tsv`
- asset manifest: `tmp/live-export-release-v3/asset_manifest.tsv`
- private health oracle audit: `tmp/health-full-validation-20260421-v2/coverage_report.md`

current live corpus:
- CMD ready historical attachment
- CMD old partial-ready thread
- Gemotest multi-attachment thread
- DNKOM long/unicode filename attachment
- CMD 2025 ready attachment
- KDL attachment

private health oracle result:
- `35` active health-inventory artifacts checked across `33` order/provider groups
- Gmail/password lane: `19/19` acquisition and enrichment ok
- tokenized Invitro portal lane: `14/14` acquisition and enrichment ok with operator last-name hint
- promoted result assets: `47`
- raw-only support assets: `1` `non_result`, `7` `sidecar`
- metadata: `15` direct-date rows, `32` inferred-date rows, `0` unknown-owner promoted rows

## what is not claimed

not ready as:
- Gmail API native product
- universal lab portal robot
- hosted SaaS
- login/password/2FA/captcha provider automation

portal status:
- generic non-tokenized Invitro links are now classified as `portal_link_missing_or_non_tokenized`
- tokenized Invitro anonymous result export is verified on the user's private health oracle with an operator-supplied last-name hint

## next product step

move from `browser-first alpha` to `api-first beta`:
1. implement Gmail API discovery/acquisition
2. replay the current enrichment/promotion layer on API-native evidence
3. add a live tokenized portal corpus case
4. expand metadata parsers for provider-direct analysis dates and owner confirmation

## post-release live smoke note

2026-04-28 Prodia freshness check showed a trust issue in the metadata lane: a passworded PDF whose text extraction failed could still receive `analysis_date=run_fallback` and appear in `final/` with a run-date prefix. The code now keeps fallback-dated assets in `raw/` as `needs_review` instead of promoting them.
