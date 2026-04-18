from __future__ import annotations

import csv
from pathlib import Path

ANALYSES_HEADER = [
    "analysis_id",
    "provider",
    "category",
    "canonical_file",
    "owner_name",
    "owner_status",
    "sample_draw_datetime",
    "analysis_date",
    "confidence",
    "status",
]


def write_analysis_manifest(output_path: Path, rows: list[dict[str, str]]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ANALYSES_HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return output_path
