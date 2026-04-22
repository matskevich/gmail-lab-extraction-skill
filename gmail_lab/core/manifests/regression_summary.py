from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import cast

REGRESSION_SUMMARY_HEADER = [
    "line_no",
    "slug",
    "status",
    "actual_attachments",
    "actual_inline",
    "filtered_count",
    "filter_summary_json",
    "saved_filenames",
    "thread_title",
    "thread_href",
    "query",
    "needle",
    "note",
    "json_log",
]


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return cast(dict[str, object], data)


def build_regression_summary_rows(manifest_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in _read_tsv(manifest_path):
        json_log_value = row.get("json_log", "")
        json_log = Path(json_log_value) if json_log_value else None
        data = _load_json(json_log) if json_log else {}
        thread = data.get("thread") if isinstance(data, dict) else {}
        if not isinstance(thread, dict):
            thread = {}
        filter_summary = data.get("filterSummary") if isinstance(data, dict) else {}
        if not isinstance(filter_summary, dict):
            filter_summary = {}
        saved = data.get("saved") if isinstance(data, dict) else []
        if not isinstance(saved, list):
            saved = []

        filtered_count = sum(
            int(value)
            for value in filter_summary.values()
            if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
        )
        saved_filenames = ",".join(
            str(item.get("filename", ""))
            for item in saved
            if isinstance(item, dict) and item.get("filename")
        )

        rows.append(
            {
                "line_no": row.get("line_no", ""),
                "slug": row.get("slug", ""),
                "status": row.get("status", ""),
                "actual_attachments": row.get("actual_attachments", "0"),
                "actual_inline": row.get("actual_inline", "0"),
                "filtered_count": str(filtered_count),
                "filter_summary_json": json.dumps(filter_summary, ensure_ascii=False, sort_keys=True),
                "saved_filenames": saved_filenames,
                "thread_title": str(thread.get("title", "")),
                "thread_href": str(thread.get("href", "")),
                "query": row.get("query", ""),
                "needle": row.get("needle", ""),
                "note": row.get("note", ""),
                "json_log": json_log_value,
            }
        )
    return rows


def write_regression_summary(output_path: Path, rows: list[dict[str, str]]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGRESSION_SUMMARY_HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return output_path
