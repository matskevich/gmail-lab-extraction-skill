from __future__ import annotations

import csv
from pathlib import Path

from gmail_lab.core.models import EvidenceRecord

EVIDENCE_HEADER = [
    "line_no",
    "mailbox",
    "message_id",
    "source_kind",
    "original_filename",
    "stored_path",
    "mime_type",
    "size_bytes",
    "sha256",
    "created_at",
]


def build_evidence_rows(evidence_rows: list[EvidenceRecord]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, evidence in enumerate(evidence_rows, start=1):
        rows.append(
            {
                "line_no": str(index),
                "mailbox": evidence.mailbox,
                "message_id": evidence.message_id,
                "source_kind": evidence.source_kind,
                "original_filename": evidence.original_filename,
                "stored_path": evidence.stored_path,
                "mime_type": evidence.mime_type,
                "size_bytes": str(evidence.size_bytes),
                "sha256": evidence.sha256,
                "created_at": evidence.created_at,
            }
        )
    return rows


def write_evidence_manifest(output_path: Path, evidence_rows: list[EvidenceRecord]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = build_evidence_rows(evidence_rows)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVIDENCE_HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return output_path
