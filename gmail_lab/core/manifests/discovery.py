from __future__ import annotations

import csv
from pathlib import Path

from gmail_lab.core.models import MessageRecord

DISCOVERY_HEADER = [
    "line_no",
    "slug",
    "discovery_status",
    "discovery_class",
    "attachment_candidate_count",
    "download_url_count",
    "inline_candidate_count",
    "scanning_for_viruses",
    "json_log",
    "stderr_log",
    "query",
    "needle",
]


def build_discovery_rows(messages: list[MessageRecord]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, message in enumerate(messages, start=1):
        slug = f"{index}-{message.message_id}"
        rows.append(
            {
                "line_no": str(index),
                "slug": slug,
                "discovery_status": message.discovery_status,
                "discovery_class": message.discovery_class,
                "attachment_candidate_count": str(message.attachment_candidate_count),
                "download_url_count": str(message.download_url_count),
                "inline_candidate_count": str(message.inline_candidate_count),
                "scanning_for_viruses": "true" if message.scanning_for_viruses else "false",
                "json_log": message.json_log,
                "stderr_log": message.stderr_log,
                "query": message.query,
                "needle": message.needle,
            }
        )
    return rows


def write_discovery_manifest(output_path: Path, messages: list[MessageRecord]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = build_discovery_rows(messages)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DISCOVERY_HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return output_path
