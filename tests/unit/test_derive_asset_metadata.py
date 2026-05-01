from __future__ import annotations

import csv
import sys

from scripts.derive_asset_metadata import (
    choose_analysis_date,
    choose_owner,
    is_non_result_asset,
    is_sidecar_asset,
    main,
    tsv_cell,
)


def test_is_non_result_asset_detects_support_pamphlet() -> None:
    assert is_non_result_asset("Памятка_грипп.pdf")
    assert not is_non_result_asset("ORDER123.pdf")


def test_is_sidecar_asset_detects_signature_sidecar() -> None:
    assert is_sidecar_asset("result.pdf.sig")
    assert not is_sidecar_asset("result.pdf")


def test_tsv_cell_flattens_manifest_breaking_whitespace() -> None:
    assert tsv_cell("Mr Example\nThis\tValue") == "Mr Example This Value"


def test_provider_pdf_text_owner_and_reg_no_date_are_direct_evidence() -> None:
    text = "Reg No./Date :123456789/ 10-04-2026 Gender : Male\nPatient Name: Mr. Example Patient Mobile Phone: +10000000000"

    assert choose_owner(text) == ("Mr. Example Patient", "provider_client")
    assert choose_analysis_date({}, {}, [], [text], "123456789.pdf", "2026-04-21") == (
        "2026-04-10",
        "artifact_contextual_date",
    )


def test_russian_owner_can_be_derived_from_filename() -> None:
    assert choose_owner("123456789-Иванов Иван Иванович.pdf") == (
        "Иванов Иван Иванович",
        "filename_name",
    )


def test_fallback_dated_asset_is_not_promoted_to_final(tmp_path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    raw_dir = run_dir / "raw" / "target"
    logs_dir = run_dir / "logs"
    raw_dir.mkdir(parents=True)
    logs_dir.mkdir()
    (raw_dir / "result.pdf").write_bytes(b"%PDF-1.4\n")
    (run_dir / "run_meta.txt").write_text("started_at=2026-04-28T10:00:00Z\n", encoding="utf-8")
    thread_json = logs_dir / "thread.json"
    provider_json = logs_dir / "provider.json"
    thread_json.write_text("{}", encoding="utf-8")
    provider_json.write_text("{}", encoding="utf-8")
    (run_dir / "run_manifest.tsv").write_text(
        "\t".join(["line_no", "raw_dir", "pdf_text_manifest", "thread_json", "provider_json"])
        + "\n"
        + "\t".join(["1", str(raw_dir), "-", str(thread_json), str(provider_json)])
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["derive_asset_metadata.py", str(run_dir)])

    assert main() == 0

    with (run_dir / "asset_manifest.tsv").open(encoding="utf-8") as manifest:
        rows = list(csv.DictReader(manifest, delimiter="\t"))
    assert rows == [
        {
            "raw_file": str(raw_dir / "result.pdf"),
            "final_file": "-",
            "analysis_date": "2026-04-28",
            "analysis_date_source": "run_fallback",
            "analysis_date_status": "fallback",
            "owner_name": "unknown-owner",
            "owner_source": "none",
            "owner_status": "unknown_owner",
            "provider": "unknown-provider",
            "provider_source": "none",
            "confidence": "low",
            "status": "needs_review",
        }
    ]
    assert not (run_dir / "final").exists()
