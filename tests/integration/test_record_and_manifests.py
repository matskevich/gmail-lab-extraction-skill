from __future__ import annotations

import csv
import json
from pathlib import Path

from click.testing import CliRunner

from gmail_lab.transports.cli import main


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_record_message_and_emit_manifests(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    runner = CliRunner()

    raw_file = _write(tmp_path / "message.raw.eml", "Subject: Test\n\nhello")
    full_json = _write(tmp_path / "message.full.json", json.dumps({"id": "msg-1"}))
    headers_json = _write(tmp_path / "headers.json", json.dumps({"Subject": "Test"}))
    mime_summary = _write(tmp_path / "mime_summary.json", json.dumps({"parts": 1}))
    json_log = _write(tmp_path / "extract.json", "{}")
    stderr_log = _write(tmp_path / "extract.stderr.log", "")
    evidence_file = _write(tmp_path / "report.pdf", "fake pdf bytes")

    result = runner.invoke(main, ["--root", str(root), "init"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "record-mailbox",
            "--mailbox",
            "primary",
            "--gmail-address",
            "user@example.com",
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "record-message",
            "--mailbox",
            "primary",
            "--message-id",
            "msg-1",
            "--thread-id",
            "thread-1",
            "--internal-date",
            "2026-04-18T10:00:00Z",
            "--subject",
            "Lab result",
            "--sender",
            "lab@example.com",
            "--snippet",
            "important result",
            "--raw-file",
            str(raw_file),
            "--full-json-file",
            str(full_json),
            "--headers-json-file",
            str(headers_json),
            "--mime-summary-json-file",
            str(mime_summary),
            "--discovery-status",
            "ok",
            "--discovery-class",
            "candidate_attachment",
            "--attachment-candidate-count",
            "1",
            "--download-url-count",
            "1",
            "--inline-candidate-count",
            "0",
            "--query",
            "from:lab@example.com result",
            "--needle",
            "Lab result",
            "--json-log",
            str(json_log),
            "--stderr-log",
            str(stderr_log),
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "record-evidence",
            "--mailbox",
            "primary",
            "--message-id",
            "msg-1",
            "--source-file",
            str(evidence_file),
            "--source-kind",
            "attachment",
        ],
    )
    assert result.exit_code == 0, result.output

    discovery_manifest = tmp_path / "discovery_manifest.tsv"
    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "emit-discovery-manifest",
            "--mailbox",
            "primary",
            "--output",
            str(discovery_manifest),
        ],
    )
    assert result.exit_code == 0, result.output
    assert discovery_manifest.exists()

    rows = list(csv.DictReader(discovery_manifest.open(), delimiter="\t"))
    assert len(rows) == 1
    assert rows[0]["discovery_class"] == "candidate_attachment"
    assert rows[0]["json_log"] == str(json_log.resolve())

    evidence_manifest = tmp_path / "evidence_manifest.tsv"
    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "emit-evidence-manifest",
            "--mailbox",
            "primary",
            "--output",
            str(evidence_manifest),
        ],
    )
    assert result.exit_code == 0, result.output
    assert evidence_manifest.exists()

    evidence_rows = list(csv.DictReader(evidence_manifest.open(), delimiter="\t"))
    assert len(evidence_rows) == 1
    assert evidence_rows[0]["message_id"] == "msg-1"
    assert evidence_rows[0]["source_kind"] == "attachment"
    assert evidence_rows[0]["original_filename"] == "report.pdf"
