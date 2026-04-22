from __future__ import annotations

import csv
import json

from gmail_lab.core.manifests.regression_summary import build_regression_summary_rows


def test_build_regression_summary_rows_reads_filter_and_thread_context(tmp_path) -> None:
    log_path = tmp_path / "case.extract.json"
    log_path.write_text(
        json.dumps(
            {
                "thread": {
                    "title": "example thread",
                    "href": "https://mail.google.com/mail/u/0/#example",
                },
                "filterSummary": {
                    "generic_webp_inline_with_attachments": 2,
                    "zero_byte_inline": 1,
                },
                "saved": [
                    {"filename": "result.pdf", "kind": "attachment", "size": 123},
                    {"filename": "result.sig", "kind": "attachment", "size": 45},
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest_path = tmp_path / "regression_manifest.tsv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "line_no",
                "slug",
                "status",
                "actual_attachments",
                "actual_inline",
                "query",
                "needle",
                "note",
                "json_log",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow(
            {
                "line_no": "1",
                "slug": "1-example",
                "status": "pass",
                "actual_attachments": "2",
                "actual_inline": "0",
                "query": "example query",
                "needle": "example needle",
                "note": "example note",
                "json_log": str(log_path),
            }
        )

    rows = build_regression_summary_rows(manifest_path)

    assert rows == [
        {
            "line_no": "1",
            "slug": "1-example",
            "status": "pass",
            "actual_attachments": "2",
            "actual_inline": "0",
            "filtered_count": "3",
            "filter_summary_json": '{"generic_webp_inline_with_attachments": 2, "zero_byte_inline": 1}',
            "saved_filenames": "result.pdf,result.sig",
            "thread_title": "example thread",
            "thread_href": "https://mail.google.com/mail/u/0/#example",
            "query": "example query",
            "needle": "example needle",
            "note": "example note",
            "json_log": str(log_path),
        }
    ]


def test_build_regression_summary_rows_handles_empty_failed_json(tmp_path) -> None:
    log_path = tmp_path / "failed.extract.json"
    log_path.write_text("", encoding="utf-8")

    manifest_path = tmp_path / "regression_manifest.tsv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "line_no",
                "slug",
                "status",
                "actual_attachments",
                "actual_inline",
                "query",
                "needle",
                "note",
                "json_log",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow(
            {
                "line_no": "1",
                "slug": "1-failed",
                "status": "extract_fail",
                "actual_attachments": "0",
                "actual_inline": "0",
                "query": "from:lab failed",
                "needle": "failed",
                "note": "failed target",
                "json_log": str(log_path),
            }
        )

    rows = build_regression_summary_rows(manifest_path)

    assert rows[0]["status"] == "extract_fail"
    assert rows[0]["thread_title"] == ""
    assert rows[0]["saved_filenames"] == ""
