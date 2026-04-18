from __future__ import annotations

import csv
from pathlib import Path

from gmail_lab.core.models import ClaimRecord

CLAIMS_HEADER = [
    "analysis_id",
    "mailbox",
    "message_id",
    "evidence_sha256",
    "evidence_path",
    "provider",
    "provider_source",
    "category",
    "owner_name",
    "owner_status",
    "owner_source",
    "owner_evidence",
    "analysis_date",
    "analysis_date_source",
    "sample_draw_date",
    "sample_draw_time",
    "sample_draw_datetime",
    "sample_draw_status",
    "sample_draw_source",
    "sample_draw_evidence",
    "confidence",
    "created_at",
]


def write_claims_manifest(output_path: Path, claims: list[ClaimRecord]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CLAIMS_HEADER, delimiter="\t")
        writer.writeheader()
        for claim in claims:
            writer.writerow({field: getattr(claim, field) for field in CLAIMS_HEADER})
    return output_path
