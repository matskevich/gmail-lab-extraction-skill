#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

from gmail_lab.core.secrets.models import RememberSecret, SecretCandidate, SecretContext
from gmail_lab.core.secrets.resolver import SecretResolver
from gmail_lab.core.secrets.store import SecretStore


def read_json(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def normalize_thread_json(data: dict) -> dict:
    if not isinstance(data, dict):
        return {}
    thread = data.get("thread")
    if isinstance(thread, dict):
        return thread
    return data


def run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True)


def iter_pdfs(input_path: Path):
    if input_path.is_file():
        if input_path.suffix.lower() == ".pdf":
            yield input_path
        return
    for p in sorted(input_path.rglob("*.pdf")):
        if p.is_file():
            yield p


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pdftotext_extract(pdf_path: Path, password: str = "") -> tuple[bool, str, str]:
    args = ["pdftotext", "-layout"]
    if password:
        args += ["-upw", password]
    args += [str(pdf_path), "-"]
    proc = run_cmd(args)
    text = proc.stdout or ""
    ok = proc.returncode == 0
    return ok, text, (proc.stderr or "").strip()


def pdf_to_images(pdf_path: Path, output_prefix: Path, password: str = "") -> tuple[bool, str]:
    args = ["pdftoppm", "-r", "200", "-png"]
    if password:
        args += ["-upw", password]
    args += [str(pdf_path), str(output_prefix)]
    proc = run_cmd(args)
    return proc.returncode == 0, (proc.stderr or "").strip()


def ocr_image(image_path: Path) -> tuple[bool, str]:
    base = image_path.with_suffix("")
    proc = run_cmd(["tesseract", str(image_path), str(base), "-l", "eng", "--psm", "6"])
    txt_path = base.with_suffix(".txt")
    if proc.returncode != 0 or not txt_path.exists():
        return False, ""
    return True, txt_path.read_text(encoding="utf-8", errors="ignore")


def write_text_output(output_dir: Path, source_file: Path, text: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / f"{source_file.stem}.txt"
    txt_path.write_text(text, encoding="utf-8")
    return txt_path


def redact_password(password: str) -> str:
    if not password:
        return ""
    return "redacted"


def provider_name(thread_json: dict, provider_json: dict) -> str:
    hints = thread_json.get("providerHints", {}) if isinstance(thread_json, dict) else {}
    if isinstance(hints, dict):
        for key in ("provider", "name", "domain"):
            value = str(hints.get(key, "")).strip()
            if value:
                return value.lower()
    provider_meta = provider_json.get("meta", {}) if isinstance(provider_json, dict) else {}
    for key in ("provider", "name", "title"):
        value = str(provider_meta.get(key, "")).strip()
        if value:
            return value.lower()
    return ""


def thread_id(thread_json: dict) -> str:
    for key in ("threadId", "messageId", "id"):
        value = str(thread_json.get(key, "")).strip()
        if value:
            return value
    href = str(thread_json.get("href", "")).strip()
    if href:
        return sha256(href.encode("utf-8")).hexdigest()
    return ""


def joined_context(thread_json: dict, provider_json: dict, pdf_path: Path) -> str:
    provider_meta = provider_json.get("meta", {}) if isinstance(provider_json, dict) else {}
    bits = [
        str(thread_json.get("title", "")),
        str(thread_json.get("bodySnippet", "")),
        str(thread_json.get("href", "")),
        str(provider_meta.get("title", "")),
        str(provider_meta.get("text", "")),
        str(provider_meta.get("client", "")),
        pdf_path.name,
    ]
    return "\n".join(bit for bit in bits if bit)


def build_secret_context(thread_json: dict, provider_json: dict, pdf_path: Path) -> SecretContext:
    context_text = joined_context(thread_json, provider_json, pdf_path)
    return SecretContext(
        provider=provider_name(thread_json, provider_json),
        identity_alias="default",
        attachment_sha256=file_sha256(pdf_path) if pdf_path.exists() else "",
        gmail_thread_id=thread_id(thread_json),
        hint_text=context_text,
        thread_text=context_text,
        provider_text="\n".join(str(v) for v in (provider_json.get("meta", {}) or {}).values()),
        source_file=str(pdf_path),
    )


def is_password_error(stderr: str) -> bool:
    return bool(
        re.search(
            r"incorrect password|requires a password|encrypted|command line error.*password|invalid password",
            stderr,
            re.I,
        )
    )


def manifest_row(
    pdf_path: Path,
    *,
    text_txt: Path | str = "",
    method: str = "",
    password_source: str = "",
    password_used: str = "",
    secret_scope: str = "",
    secret_persistence: str = "none",
    candidate_count: int = 0,
    status: str,
    notes: str = "",
) -> dict[str, str]:
    return {
        "source_file": str(pdf_path),
        "text_txt": str(text_txt),
        "method": method,
        "password_source": password_source,
        "password_used": password_used,
        "secret_scope": secret_scope,
        "secret_persistence": secret_persistence,
        "candidate_count": str(candidate_count),
        "status": status,
        "notes": notes,
    }


def try_extract(
    pdf_path: Path,
    output_dir: Path,
    thread_json: dict,
    provider_json: dict,
    resolver: SecretResolver,
    *,
    prompt_secrets: bool = False,
    remember_secret: RememberSecret = "never",
) -> dict[str, str]:
    context = build_secret_context(thread_json, provider_json, pdf_path)
    candidates: list[SecretCandidate] = []
    candidates_loaded = False
    attempted = ["<empty>"]

    def load_secret_candidates() -> list[SecretCandidate]:
        nonlocal candidates_loaded, candidates, attempted
        if candidates_loaded:
            return candidates
        candidates_loaded = True
        candidates = resolver.candidates(
            context,
            prompt_secrets=prompt_secrets,
            remember_secret=remember_secret,
        )
        attempted = ["<empty>"] + [
            f"{redact_password(candidate.value)} ({candidate.source})" for candidate in candidates
        ]
        return candidates

    pdftotext_bin = shutil.which("pdftotext")
    pdftoppm_bin = shutil.which("pdftoppm")
    tesseract_bin = shutil.which("tesseract")
    missing_bins = [name for name, bin_path in (
        ("pdftotext", pdftotext_bin),
        ("pdftoppm", pdftoppm_bin),
        ("tesseract", tesseract_bin),
    ) if not bin_path]
    notes_parts: list[str] = []

    stderr = ""
    password_failure = False
    if pdftotext_bin:
        ok, text, stderr = pdftotext_extract(pdf_path)
        password_failure = is_password_error(stderr)
        if ok and text.strip():
            txt_path = write_text_output(output_dir, pdf_path, text)
            return manifest_row(
                pdf_path,
                text_txt=txt_path,
                method="pdftotext",
                password_source="none",
                candidate_count=0,
                status="ok_text",
            )
    else:
        notes_parts.append("missing=pdftotext")

    if password_failure:
        load_secret_candidates()

    attempts = [SecretCandidate(value="", source="none", persistence="none")]
    attempts.extend(candidates)
    if pdftotext_bin:
        for candidate in attempts[1:]:
            ok, text, stderr = pdftotext_extract(pdf_path, password=candidate.value)
            password_failure = password_failure or is_password_error(stderr)
            if ok and text.strip():
                txt_path = write_text_output(output_dir, pdf_path, text)
                return manifest_row(
                    pdf_path,
                    text_txt=txt_path,
                    method="pdftotext_password",
                    password_source=candidate.source,
                    password_used=redact_password(candidate.value),
                    secret_scope=str(candidate.scope),
                    secret_persistence=candidate.persistence,
                    candidate_count=len(candidates),
                    status="ok_text",
                )

    image_dir = output_dir / f"{pdf_path.stem}_pages"
    if pdftoppm_bin and tesseract_bin:
        for index, candidate in enumerate(attempts):
            image_dir.mkdir(parents=True, exist_ok=True)
            prefix = image_dir / "page"
            ok, pdfppm_stderr = pdf_to_images(pdf_path, prefix, password=candidate.value)
            if not ok:
                stderr = pdfppm_stderr or stderr
                password_failure = password_failure or is_password_error(stderr)
                if index == 0 and password_failure and not candidates_loaded:
                    attempts.extend(load_secret_candidates())
                continue
            texts: list[str] = []
            page_images = sorted(image_dir.glob("page-*.png"))
            for img in page_images:
                ocr_ok, ocr_text = ocr_image(img)
                if ocr_ok and ocr_text.strip():
                    texts.append(ocr_text)
            if texts:
                txt_path = write_text_output(output_dir, pdf_path, "\n\n".join(texts))
                return manifest_row(
                    pdf_path,
                    text_txt=txt_path,
                    method="pdf_ocr" if not candidate.value else "pdf_ocr_password",
                    password_source=candidate.source,
                    password_used=redact_password(candidate.value),
                    secret_scope=str(candidate.scope),
                    secret_persistence=candidate.persistence,
                    candidate_count=len(candidates),
                    status="ok_ocr",
                )
    else:
        if not pdftoppm_bin:
            notes_parts.append("missing=pdftoppm")
        if not tesseract_bin:
            notes_parts.append("missing=tesseract")

    missing_dependency_only = bool(missing_bins) and not pdftotext_bin and (not pdftoppm_bin or not tesseract_bin)
    if password_failure and resolver.hint_type(context) and not candidates:
        status = "needs_password_hint"
    elif missing_dependency_only:
        status = "missing_dependency"
    elif missing_bins and not (pdftoppm_bin and tesseract_bin):
        status = "missing_dependency"
    else:
        status = "fail"

    if status == "needs_password_hint":
        notes_parts.append("next=rerun with --prompt-secrets or set PDF_PASSWORD_CANDIDATES/PDF_BIRTH_DATE")

    return manifest_row(
        pdf_path,
        candidate_count=len(candidates),
        status=status,
        notes="; ".join(filter(None, [stderr, *notes_parts, "attempted=" + ", ".join(attempted[:12])]))[:2000],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract text from PDFs, including password-protected PDFs, using pdftotext or OCR.")
    parser.add_argument("input_path", help="PDF file or directory")
    parser.add_argument("output_dir", help="Directory for extracted text outputs")
    parser.add_argument("--thread-json", default="", help="Optional thread context JSON")
    parser.add_argument("--provider-json", default="", help="Optional provider context JSON")
    parser.add_argument("--prompt-secrets", action="store_true", help="Prompt locally for password/date secrets when needed")
    parser.add_argument(
        "--remember-secret",
        choices=["never", "session", "keychain", "encrypted-file"],
        default=os.environ.get("PDF_REMEMBER_SECRET", "never"),
        help="Persistence for secrets entered through --prompt-secrets",
    )
    args = parser.parse_args()
    if args.remember_secret not in {"never", "session", "keychain", "encrypted-file"}:
        parser.error("--remember-secret must be one of: never, session, keychain, encrypted-file")

    input_path = Path(args.input_path).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    thread_json = normalize_thread_json(read_json(Path(args.thread_json).expanduser())) if args.thread_json else {}
    provider_json = read_json(Path(args.provider_json).expanduser()) if args.provider_json else {}
    resolver = SecretResolver(store=SecretStore())

    rows: list[dict[str, str]] = []
    for pdf_path in iter_pdfs(input_path):
        rows.append(
            try_extract(
                pdf_path,
                output_dir,
                thread_json,
                provider_json,
                resolver,
                prompt_secrets=args.prompt_secrets,
                remember_secret=args.remember_secret,
            )
        )

    manifest = output_dir / "pdf_text_manifest.tsv"
    with manifest.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "source_file",
                "text_txt",
                "method",
                "password_source",
                "password_used",
                "secret_scope",
                "secret_persistence",
                "candidate_count",
                "status",
                "notes",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
