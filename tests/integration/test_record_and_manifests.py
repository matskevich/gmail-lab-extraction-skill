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


def test_google_auth_status_reports_missing_token(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    runner = CliRunner()

    result = runner.invoke(main, ["--root", str(root), "google-auth-status"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["exists"] is False
    assert payload["valid"] is False
    assert payload["token_path"].endswith("tokens/gmail-api-token.json")


def test_export_gmail_api_command_is_available() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["export-gmail-api", "--help"])

    assert result.exit_code == 0, result.output
    assert "TARGETS_TSV" in result.output
    assert "--client-secrets" in result.output


def test_diagnose_gmail_acquisition_reports_missing_auth_and_cdp_down(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    runner = CliRunner()

    result = runner.invoke(main, ["--root", str(root), "diagnose-gmail-acquisition", "--port", "9"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ready"] is False
    assert payload["preferred_lane"] == "auth_google"
    assert payload["gmail_api"]["valid"] is False
    assert payload["browser_cdp"]["state"] == "cdp_down"
    assert "auth-google" in "\n".join(payload["recommendations"])


def test_derive_claims_and_emit_manifests(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    runner = CliRunner()

    config_path = root / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                "identity:",
                "  canonical_name: \"Иванов Иван Иванович\"",
                "  aliases:",
                "    - \"Ivan Ivanov\"",
            ]
        ),
        encoding="utf-8",
    )

    evidence_file = _write(
        tmp_path / "report.txt",
        "\n".join(
            [
                "Пациент: Иванов Иван Иванович",
                "Дата взятия биоматериала: 05.02.2021",
                "Дата готовности результата: 06.02.2021",
                "Свободный тестостерон: 19.83",
            ]
        ),
    )

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
            "msg-2",
            "--thread-id",
            "thread-2",
            "--internal-date",
            "2026-04-18T10:00:00Z",
            "--subject",
            "CMD result",
            "--sender",
            "info@cmd-online.ru",
            "--snippet",
            "lab result",
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
            "msg-2",
            "--source-file",
            str(evidence_file),
            "--source-kind",
            "attachment",
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(main, ["--root", str(root), "derive-claims", "--mailbox", "primary"])
    assert result.exit_code == 0, result.output

    claims_manifest = tmp_path / "claims_manifest.tsv"
    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "emit-claims-manifest",
            "--mailbox",
            "primary",
            "--output",
            str(claims_manifest),
        ],
    )
    assert result.exit_code == 0, result.output
    claims_rows = list(csv.DictReader(claims_manifest.open(), delimiter="\t"))
    assert len(claims_rows) == 1
    assert claims_rows[0]["owner_status"] == "confirmed_owner"
    assert claims_rows[0]["analysis_date"] == "2021-02-06"
    assert claims_rows[0]["sample_draw_status"] == "inferred_date_only"

    analysis_manifest = tmp_path / "analysis_manifest.tsv"
    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "emit-analysis-manifest",
            "--mailbox",
            "primary",
            "--output",
            str(analysis_manifest),
        ],
    )
    assert result.exit_code == 0, result.output
    analysis_rows = list(csv.DictReader(analysis_manifest.open(), delimiter="\t"))
    assert len(analysis_rows) == 1
    assert analysis_rows[0]["provider"] == "cmd"
    assert analysis_rows[0]["status"] == "active"


def test_identity_status_redacts_plaintext_birth_date(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    runner = CliRunner()
    config_path = root / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                "identity:",
                "  canonical_name: \"Example Patient\"",
                "  birth_date: \"1970-01-31\"",
                "  birth_date_secret_id: \"identity:default\"",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(main, ["--root", str(root), "identity-status"])

    assert result.exit_code == 0, result.output
    assert "1970-01-31" not in result.output
    assert '"birth_date": "redacted"' in result.output
    assert '"birth_date_secret_id": "identity:default"' in result.output
