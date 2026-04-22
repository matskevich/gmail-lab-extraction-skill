from __future__ import annotations

from scripts.derive_asset_metadata import (
    choose_analysis_date,
    choose_owner,
    is_non_result_asset,
    is_sidecar_asset,
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
