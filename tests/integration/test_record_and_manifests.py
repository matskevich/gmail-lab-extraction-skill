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


def test_acquire_gmail_help_exposes_persistent_cdp_start() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["acquire-gmail", "--help"])

    assert result.exit_code == 0, result.output
    assert "--start-persistent-cdp" in result.output
    assert "--allow-legacy-clone" in result.output


def test_setup_initializes_root_and_reports_next_auth_step(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    runner = CliRunner()

    result = runner.invoke(main, ["--root", str(root), "setup", "--skip-auth"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["initialized"] is True
    assert Path(payload["config"]).exists()
    assert Path(payload["state_db"]).exists()
    assert payload["gmail_api"]["status"]["valid"] is False
    assert any("client-secrets" in step for step in payload["next_steps"])


def test_setup_google_reports_missing_client_secret_plan(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    home = tmp_path / "home"
    home.mkdir()
    runner = CliRunner()

    result = runner.invoke(
        main,
        ["--root", str(root), "setup-google", "--check-only"],
        env={"HOME": str(home)},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ready"] is False
    assert payload["client_secrets"]["canonical_path"].endswith("oauth-client.json")
    assert payload["client_secrets"]["selected"] == {}
    assert payload["guide"]["scope"] == "https://www.googleapis.com/auth/gmail.readonly"
    assert "Desktop OAuth" in "\n".join(payload["next_steps"])


def test_setup_google_reports_missing_explicit_client_secret_as_json(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    missing_client_secret = tmp_path / "missing-oauth-client.json"
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "setup-google",
            "--client-secrets",
            str(missing_client_secret),
            "--check-only",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ready"] is False
    assert payload["client_secrets"]["selected"]["exists"] is False
    assert payload["client_secrets"]["selected"]["errors"] == ["file_not_found"]
    assert "correct `--client-secrets` path" in "\n".join(payload["next_steps"])


def test_setup_google_validates_desktop_client_secret_without_leaking_value(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    client_secret = tmp_path / "oauth-client.json"
    client_secret.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "abc.apps.googleusercontent.com",
                    "client_secret": "super-secret-value",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "setup-google",
            "--client-secrets",
            str(client_secret),
            "--check-only",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ready"] is False
    assert payload["client_secrets"]["selected"]["valid"] is True
    assert payload["client_secrets"]["selected"]["client_type"] == "installed"
    assert payload["client_secrets"]["value"] == "redacted"
    assert "super-secret-value" not in result.output
    assert "setup-google" in "\n".join(payload["next_steps"])


def test_unlock_pdf_run_help_exposes_secret_resolution_options() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["unlock-pdf-run", "--help"])

    assert result.exit_code == 0, result.output
    assert "--prompt-secrets" in result.output
    assert "--remember-secret" in result.output


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
    assert "setup-google" in "\n".join(payload["recommendations"])


def test_verify_gmail_paths_reports_missing_auth_and_cdp_down(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    runner = CliRunner()

    result = runner.invoke(main, ["--root", str(root), "verify-gmail-paths", "--port", "9"])

    assert result.exit_code != 0
    payload = json.loads(result.output.split("\nError:", maxsplit=1)[0])
    assert payload["ready"] is False
    assert payload["preferred_lane"] == "auth_google"
    assert payload["gmail_api"]["valid"] is False
    assert payload["browser_cdp"]["state"] == "cdp_down"
    assert payload["live_acquisition"]["ran"] is False
    assert "setup-google" in "\n".join(payload["next_steps"])


def test_verify_gmail_paths_does_not_run_targets_without_allow_live(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    targets = tmp_path / "targets.tsv"
    targets.write_text("from:lab@example.com newer_than:7d\tresult-1\tapi\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "verify-gmail-paths",
            "--port",
            "9",
            "--targets-tsv",
            str(targets),
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output.split("\nError:", maxsplit=1)[0])
    assert payload["live_acquisition"]["requested"] is True
    assert payload["live_acquisition"]["allowed"] is False
    assert payload["live_acquisition"]["ran"] is False
    assert "--allow-live" in "\n".join(payload["next_steps"])


def test_verify_gmail_paths_reports_missing_targets_path_as_json(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    missing_targets = tmp_path / "missing-targets.tsv"
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "verify-gmail-paths",
            "--port",
            "9",
            "--targets-tsv",
            str(missing_targets),
            "--allow-live",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output.split("\nError:", maxsplit=1)[0])
    assert payload["live_acquisition"]["targets_tsv"] == str(missing_targets.resolve())
    assert payload["live_acquisition"]["targets_tsv_exists"] is False
    assert "absolute targets file path" in "\n".join(payload["next_steps"])


def test_acquire_gmail_writes_typed_blocker_manifest_when_auth_missing(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    targets = tmp_path / "targets.tsv"
    targets.write_text("from:lab@example.com newer_than:7d\tresult-1\tapi\n", encoding="utf-8")
    run_dir = tmp_path / "blocked-run"
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "acquire-gmail",
            str(targets),
            str(run_dir),
            "--port",
            "9",
        ],
    )

    assert result.exit_code != 0
    assert "gmail acquisition blocked" in result.output
    run_manifest = run_dir / "run_manifest.tsv"
    assert run_manifest.exists()
    rows = list(csv.DictReader(run_manifest.open(), delimiter="\t"))
    assert len(rows) == 1
    assert rows[0]["mode"] == "router"
    assert rows[0]["status"] == "api_auth_missing"
    assert rows[0]["enrichment_status"] == "blocked_by_acquisition"
    assert (run_dir / "evidence_manifest.tsv").exists()
    assert (run_dir / "logs/acquisition_diagnostic.json").exists()


def test_explain_run_reports_acquisition_blocker_and_next_step(tmp_path) -> None:
    run_dir = tmp_path / "blocked-run"
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True)
    (run_dir / "run_manifest.tsv").write_text(
        "\t".join(
            [
                "line_no",
                "slug",
                "mode",
                "status",
                "extracted_count",
                "ocr_status",
                "pdf_text_status",
                "enrichment_status",
                "query",
                "needle",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "1",
                "1-result",
                "router",
                "api_auth_missing",
                "0",
                "not_applicable",
                "not_applicable",
                "blocked_by_acquisition",
                "from:lab@example.com",
                "result",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (logs_dir / "acquisition_diagnostic.json").write_text(
        json.dumps(
            {
                "selected_lane": "blocked",
                "blocker": "api_auth_missing",
                "gmail_api": {"exists": False, "valid": False},
                "browser_cdp": {"up": False, "authenticated_gmail": False, "state": "cdp_down"},
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(main, ["explain-run", str(run_dir)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["state"] == "acquisition_blocked"
    assert payload["counts"]["raw_acquired"] == 0
    assert payload["blockers"][0]["layer"] == "acquisition"
    assert payload["blockers"][0]["status"] == "api_auth_missing"
    assert "setup-google" in payload["next_steps"][0]


def test_status_alias_reports_password_enrichment_blocker(tmp_path) -> None:
    run_dir = tmp_path / "password-run"
    pdf_text_dir = run_dir / "pdf_text"
    pdf_text_dir.mkdir(parents=True)
    (run_dir / "run_manifest.tsv").write_text(
        "\t".join(
            [
                "line_no",
                "slug",
                "mode",
                "status",
                "extracted_count",
                "ocr_status",
                "pdf_text_status",
                "enrichment_status",
                "query",
                "needle",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "1",
                "1-result",
                "api",
                "ok",
                "1",
                "not_applicable",
                "needs_password_hint",
                "needs_password_hint",
                "from:lab@example.com",
                "result",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (pdf_text_dir / "pdf_text_manifest.tsv").write_text(
        "raw_file\tstatus\ttext_file\nreport.pdf\tneeds_password_hint\t-\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(main, ["status", str(run_dir)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["state"] == "enrichment_blocked"
    assert any(blocker["status"] == "needs_password_hint" for blocker in payload["blockers"])
    assert any("unlock-pdf-run" in step for step in payload["next_steps"])


def test_explain_run_reports_ready_promoted_assets(tmp_path) -> None:
    run_dir = tmp_path / "ready-run"
    run_dir.mkdir()
    (run_dir / "run_manifest.tsv").write_text(
        "\t".join(
            [
                "line_no",
                "slug",
                "mode",
                "status",
                "extracted_count",
                "ocr_status",
                "pdf_text_status",
                "enrichment_status",
                "query",
                "needle",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "1",
                "1-result",
                "api",
                "ok",
                "1",
                "not_applicable",
                "ok",
                "ok",
                "from:lab@example.com",
                "result",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "asset_manifest.tsv").write_text(
        "\t".join(
            [
                "raw_file",
                "final_file",
                "analysis_date",
                "analysis_date_source",
                "analysis_date_status",
                "owner_name",
                "owner_source",
                "owner_status",
                "provider",
                "provider_source",
                "confidence",
                "status",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "raw/report.pdf",
                "final/2026-05-01__lab__owner__report.pdf",
                "2026-05-01",
                "provider_page",
                "direct",
                "Owner",
                "provider_client",
                "confirmed_owner",
                "lab",
                "query_domain",
                "high",
                "ok",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(main, ["explain-run", str(run_dir)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["state"] == "ready"
    assert payload["counts"]["promoted"] == 1
    assert payload["blockers"] == []


def test_explain_run_counts_per_slug_enrichment_manifests(tmp_path) -> None:
    run_dir = tmp_path / "ready-run"
    pdf_text_dir = run_dir / "pdf_text" / "1-result"
    ocr_dir = run_dir / "ocr" / "1-result"
    pdf_text_dir.mkdir(parents=True)
    ocr_dir.mkdir(parents=True)
    (run_dir / "run_manifest.tsv").write_text(
        "\t".join(
            [
                "line_no",
                "slug",
                "mode",
                "status",
                "extracted_count",
                "ocr_status",
                "pdf_text_status",
                "enrichment_status",
                "query",
                "needle",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "1",
                "1-result",
                "auto",
                "ok",
                "2",
                "ok",
                "ok",
                "ok",
                "from:lab@example.com",
                "result",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "asset_manifest.tsv").write_text(
        "raw_file\tfinal_file\tstatus\nraw/a.pdf\tfinal/a.pdf\tok\nraw/b.pdf\tfinal/b.pdf\tok\n",
        encoding="utf-8",
    )
    (pdf_text_dir / "pdf_text_manifest.tsv").write_text(
        "source_file\ttext_txt\tstatus\nraw/a.pdf\ttext/a.txt\tok\nraw/b.pdf\ttext/b.txt\tok\n",
        encoding="utf-8",
    )
    (ocr_dir / "ocr_manifest.tsv").write_text(
        "source_file\ttext_file\tstatus\nraw/a.png\tocr/a.txt\tok_ocr\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(main, ["explain-run", str(run_dir)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["state"] == "ready"
    assert payload["counts"]["pdf_text_rows"] == 2
    assert payload["counts"]["ocr_rows"] == 1
    assert len(payload["manifests"]["pdf_text_manifests"]) == 1
    assert len(payload["manifests"]["ocr_manifests"]) == 1


def test_derive_claims_and_emit_manifests(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    runner = CliRunner()

    config_path = root / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                "identity:",
                '  canonical_name: "Иванов Иван Иванович"',
                "  aliases:",
                '    - "Ivan Ivanov"',
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
    secret_id = f"identity:pytest-unset-{tmp_path.name}".lower()
    config_path.write_text(
        "\n".join(
            [
                "identity:",
                '  canonical_name: "Example Patient"',
                '  birth_date: "1970-01-31"',
                f'  birth_date_secret_id: "{secret_id}"',
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(main, ["--root", str(root), "identity-status"])

    assert result.exit_code == 0, result.output
    assert "1970-01-31" not in result.output
    assert '"birth_date": "redacted"' in result.output
    assert f'"birth_date_secret_id": "{secret_id}"' in result.output
    payload = json.loads(result.output)
    assert payload["identity"]["birth_date_secret"] == {
        "secret_id": secret_id,
        "configured": True,
        "resolvable": False,
        "persistence": "none",
        "value": "",
        "legacy": True,
        "suggested_secret_id": f"pdf_unlock:{secret_id}",
        "migration_command": "gmail-lab migrate-pdf-secrets",
    }


def test_remember_pdf_secret_stores_redacted_identity_secret(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    runner = CliRunner()
    identity_alias = f"pytest-secret-{tmp_path.name}".lower()
    secret_id = f"pdf_unlock:identity:{identity_alias}"

    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "remember-pdf-secret",
            "--identity-alias",
            identity_alias,
            "--scope",
            "identity",
            "--hint-type",
            "birth_date_ddmmyyyy",
            "--persistence",
            "encrypted-file",
            "--value-env",
            "TEST_PDF_SECRET",
        ],
        env={
            "TEST_PDF_SECRET": "1970-01-31",
            "GMAIL_LAB_SECRETS_PASSPHRASE": "test-passphrase",
        },
    )

    assert result.exit_code == 0, result.output
    assert "1970-01-31" not in result.output
    payload = json.loads(result.output)
    assert payload["secret_id"] == secret_id
    assert payload["value"] == "redacted"
    assert payload["persistence"] == "encrypted-file"
    assert payload["config_birth_date_secret_id_updated"] is True

    result = runner.invoke(
        main,
        ["--root", str(root), "identity-status"],
        env={"GMAIL_LAB_SECRETS_PASSPHRASE": "test-passphrase"},
    )
    assert result.exit_code == 0, result.output
    assert "1970-01-31" not in result.output
    payload = json.loads(result.output)
    assert payload["identity"]["birth_date_secret_id"] == secret_id
    assert payload["identity"]["birth_date_secret"]["resolvable"] is True
    assert payload["identity"]["birth_date_secret"]["persistence"] == "encrypted-file"
    assert payload["identity"]["birth_date_secret"]["value"] == "redacted"
    assert payload["identity"]["birth_date_secret"]["legacy"] is False


def test_migrate_pdf_secrets_copies_legacy_identity_secret(tmp_path, monkeypatch) -> None:
    root = tmp_path / ".gmail-lab"
    runner = CliRunner()
    legacy_secret_id = f"identity:pytest-legacy-{tmp_path.name}".lower()
    target_secret_id = f"pdf_unlock:{legacy_secret_id}"

    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "remember-pdf-secret",
            "--identity-alias",
            legacy_secret_id.split(":", 1)[1],
            "--scope",
            "identity",
            "--hint-type",
            "birth_date_ddmmyyyy",
            "--persistence",
            "encrypted-file",
            "--value-env",
            "TEST_PDF_SECRET",
        ],
        env={
            "TEST_PDF_SECRET": "1970-01-31",
            "GMAIL_LAB_SECRETS_PASSPHRASE": "test-passphrase",
        },
    )
    assert result.exit_code == 0, result.output

    config_path = root / "config.yaml"
    config_text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        config_text.replace(target_secret_id, legacy_secret_id), encoding="utf-8"
    )

    result = runner.invoke(
        main,
        ["--root", str(root), "migrate-pdf-secrets"],
        env={"GMAIL_LAB_SECRETS_PASSPHRASE": "test-passphrase"},
    )

    assert result.exit_code == 0, result.output
    assert "1970-01-31" not in result.output
    payload = json.loads(result.output)
    assert payload["migrated"] is False
    assert payload["reason"] == "legacy_secret_not_resolvable"

    # Seed a real legacy value to prove migration reads old ids and writes the
    # purpose-namespaced replacement without exposing the secret.
    from gmail_lab.core.secrets.models import SecretMetadata
    from gmail_lab.core.secrets.store import SecretStore

    monkeypatch.setenv("GMAIL_LAB_SECRETS_PASSPHRASE", "test-passphrase")
    SecretStore(root).put(
        legacy_secret_id,
        "1970-01-31",
        SecretMetadata(
            secret_id=legacy_secret_id,
            label="birth_date_ddmmyyyy",
            identity_alias=legacy_secret_id.split(":", 1)[1],
            purpose="pdf_unlock",
            hint_type="birth_date_ddmmyyyy",
            scope="identity",
            persistence="encrypted-file",
        ),
    )
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(target_secret_id, legacy_secret_id),
        encoding="utf-8",
    )

    result = runner.invoke(
        main,
        ["--root", str(root), "migrate-pdf-secrets"],
        env={"GMAIL_LAB_SECRETS_PASSPHRASE": "test-passphrase"},
    )

    assert result.exit_code == 0, result.output
    assert "1970-01-31" not in result.output
    payload = json.loads(result.output)
    assert payload["migrated"] is True
    assert payload["source_secret_id"] == legacy_secret_id
    assert payload["target_secret_id"] == target_secret_id
    assert payload["value"] == "redacted"

    result = runner.invoke(
        main,
        ["--root", str(root), "identity-status"],
        env={"GMAIL_LAB_SECRETS_PASSPHRASE": "test-passphrase"},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["identity"]["birth_date_secret_id"] == target_secret_id
    assert payload["identity"]["birth_date_secret"]["legacy"] is False


def test_remember_portal_secret_is_separate_from_pdf_unlock(tmp_path) -> None:
    root = tmp_path / ".gmail-lab"
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--root",
            str(root),
            "remember-portal-secret",
            "--provider",
            "prodia",
            "--secret-type",
            "account_password",
            "--persistence",
            "encrypted-file",
            "--value-env",
            "TEST_PORTAL_SECRET",
        ],
        env={
            "TEST_PORTAL_SECRET": "portal-password-value",
            "GMAIL_LAB_SECRETS_PASSPHRASE": "test-passphrase",
        },
    )

    assert result.exit_code == 0, result.output
    assert "portal-password-value" not in result.output
    payload = json.loads(result.output)
    assert payload["secret_id"] == "portal_login:provider_identity:prodia:default"
    assert payload["purpose"] == "portal_login"
    assert payload["pdf_unlock_available"] is False
    assert payload["value"] == "redacted"

    result = runner.invoke(
        main,
        ["--root", str(root), "identity-status"],
        env={"GMAIL_LAB_SECRETS_PASSPHRASE": "test-passphrase"},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["identity"]["birth_date_secret"]["configured"] is False
