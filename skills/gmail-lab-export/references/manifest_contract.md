# Manifest Contract

Truth hierarchy:

1. `discovery_manifest.tsv` proves candidate mailbox threads.
2. `run_manifest.tsv` records acquisition and enrichment status per target.
3. `raw/` contains provenance-safe extracted files.
4. `ocr/` and `pdf_text/` contain derivative text.
5. `asset_manifest.tsv` records date, owner, provider, confidence, promotion status.
6. `final/` contains promoted convenience filenames only.

Important statuses:

- `run_manifest.tsv/status=ok`: acquisition succeeded.
- `ocr_status=missing_dependency`: OCR binary is missing; raw evidence can still be valid.
- `pdf_text_status=needs_password_hint`: encrypted PDF had a hint but no local secret candidate.
- `enrichment_status=partial`: at least one derivative lane succeeded and another was blocked.
- `asset_manifest.tsv/status=needs_review`: raw file landed, metadata is too weak for promotion.
- `analysis_date_status=fallback`: run date fallback; do not treat as clinical date.
- `final_file=-`: intentionally not promoted.

Do not claim completeness from `final/` alone.
