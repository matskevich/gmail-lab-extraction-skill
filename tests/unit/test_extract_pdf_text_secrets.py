from __future__ import annotations

from pathlib import Path

from gmail_lab.core.secrets.resolver import SecretResolver
from scripts import extract_pdf_text


def test_plain_pdf_does_not_prompt_for_secret(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "result.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    def fake_which(name: str) -> str | None:
        if name == "pdftotext":
            return "/usr/bin/pdftotext"
        return None

    def fail_prompt(prompt: str) -> str:
        raise AssertionError(f"unexpected prompt: {prompt}")

    monkeypatch.setattr(extract_pdf_text.shutil, "which", fake_which)
    monkeypatch.setattr(
        extract_pdf_text,
        "pdftotext_extract",
        lambda path, password="": (True, "plain pdf text", ""),
    )

    row = extract_pdf_text.try_extract(
        pdf_path,
        tmp_path / "out",
        {"bodySnippet": "for the password is your birth date DDMMYYYY"},
        {},
        SecretResolver(store=None, env={}, prompt_fn=fail_prompt),
        prompt_secrets=True,
    )

    assert row["status"] == "ok_text"
    assert row["method"] == "pdftotext"
    assert row["candidate_count"] == "0"


def test_encrypted_pdf_with_hint_and_no_candidate_returns_needs_password_hint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "result.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    def fake_which(name: str) -> str | None:
        if name == "pdftotext":
            return "/usr/bin/pdftotext"
        return None

    monkeypatch.setattr(extract_pdf_text.shutil, "which", fake_which)
    monkeypatch.setattr(
        extract_pdf_text,
        "pdftotext_extract",
        lambda path, password="": (
            False,
            "",
            "Command Line Error: Incorrect password",
        ),
    )

    row = extract_pdf_text.try_extract(
        pdf_path,
        tmp_path / "out",
        {"bodySnippet": "for the password is your birth date DDMMYYYY"},
        {},
        SecretResolver(store=None, env={}),
    )

    assert row["status"] == "needs_password_hint"
    assert row["candidate_count"] == "0"
    assert row["password_used"] == ""
    assert row["secret_scope"] == ""
    assert "next=rerun with --prompt-secrets" in row["notes"]
