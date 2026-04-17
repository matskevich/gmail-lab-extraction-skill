#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


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


def normalize_date(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y", "%Y%m%d", "%d%m%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def password_candidates_from_datetime(dt: datetime) -> list[str]:
    return [
        dt.strftime("%d%m%Y"),
        dt.strftime("%Y%m%d"),
        dt.strftime("%d-%m-%Y"),
        dt.strftime("%d.%m.%Y"),
        dt.strftime("%d/%m/%Y"),
    ]


def extract_dates(text: str) -> list[datetime]:
    found: list[datetime] = []
    patterns = [
        r"\b\d{2}[./-]\d{2}[./-]\d{4}\b",
        r"\b\d{4}[./-]\d{2}[./-]\d{2}\b",
        r"\b\d{8}\b",
    ]
    seen = set()
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            raw = m.group(0)
            dt = normalize_date(raw)
            if not dt:
                continue
            key = dt.strftime("%Y-%m-%d")
            if key in seen:
                continue
            seen.add(key)
            found.append(dt)
    return found


def extract_explicit_passwords(text: str) -> list[str]:
    out: list[str] = []
    patterns = [
        r"password[^0-9A-Za-z]{0,20}([0-9]{4,12})",
        r"passcode[^0-9A-Za-z]{0,20}([0-9]{4,12})",
        r"kata sandi[^0-9A-Za-z]{0,20}([0-9]{4,12})",
    ]
    seen = set()
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.I):
            pwd = m.group(1)
            if pwd not in seen:
                seen.add(pwd)
                out.append(pwd)
    return out


def build_password_candidates(context_text: str, provider_json: dict) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen = set()

    def add(password: str, source: str):
        pwd = (password or "").strip()
        if not pwd or pwd in seen:
            return
        seen.add(pwd)
        candidates.append((pwd, source))

    for raw in os.environ.get("PDF_PASSWORD_CANDIDATES", "").split(","):
        add(raw, "env_password_candidates")

    birth_date_env = os.environ.get("PDF_BIRTH_DATE", "")
    dt = normalize_date(birth_date_env)
    if dt:
        for pwd in password_candidates_from_datetime(dt):
            add(pwd, "env_birth_date")

    provider_birth_date = str((provider_json.get("meta", {}) or {}).get("birthDate", ""))
    dt = normalize_date(provider_birth_date)
    if dt:
        for pwd in password_candidates_from_datetime(dt):
            add(pwd, "provider_birth_date")

    for pwd in extract_explicit_passwords(context_text):
        add(pwd, "thread_explicit_password")

    if re.search(r"birth date|date of birth|dob|ddmmyyyy", context_text, re.I):
        for dt in extract_dates(context_text):
            for pwd in password_candidates_from_datetime(dt):
                add(pwd, "thread_birth_date_hint")

    return candidates


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


def joined_context(thread_json: dict, provider_json: dict, pdf_path: Path) -> str:
    provider_meta = provider_json.get("meta", {}) if isinstance(provider_json, dict) else {}
    bits = [
        str(thread_json.get("title", "")),
        str(thread_json.get("bodySnippet", "")),
        str(thread_json.get("href", "")),
        str(provider_meta.get("title", "")),
        str(provider_meta.get("text", "")),
        str(provider_meta.get("birthDate", "")),
        str(provider_meta.get("client", "")),
        pdf_path.name,
    ]
    return "\n".join(bit for bit in bits if bit)


def try_extract(pdf_path: Path, output_dir: Path, thread_json: dict, provider_json: dict) -> dict[str, str]:
    context = joined_context(thread_json, provider_json, pdf_path)
    candidates = build_password_candidates(context, provider_json)
    attempted = ["<empty>"] + [f"{redact_password(pwd)} ({source})" for pwd, source in candidates]
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
    if pdftotext_bin:
        ok, text, stderr = pdftotext_extract(pdf_path)
        if ok and text.strip():
            txt_path = write_text_output(output_dir, pdf_path, text)
            return {
                "source_file": str(pdf_path),
                "text_txt": str(txt_path),
                "method": "pdftotext",
                "password_source": "none",
                "password_used": "",
                "candidate_count": str(len(candidates)),
                "status": "ok_text",
                "notes": "",
            }
    else:
        notes_parts.append("missing=pdftotext")

    attempts = [("", "none")]
    attempts.extend(candidates)
    if pdftotext_bin:
        for password, source in attempts[1:]:
            ok, text, stderr = pdftotext_extract(pdf_path, password=password)
            if ok and text.strip():
                txt_path = write_text_output(output_dir, pdf_path, text)
                return {
                    "source_file": str(pdf_path),
                    "text_txt": str(txt_path),
                    "method": "pdftotext_password",
                    "password_source": source,
                    "password_used": redact_password(password),
                    "candidate_count": str(len(candidates)),
                    "status": "ok_text",
                    "notes": "",
                }

    image_dir = output_dir / f"{pdf_path.stem}_pages"
    if pdftoppm_bin and tesseract_bin:
        for password, source in attempts:
            image_dir.mkdir(parents=True, exist_ok=True)
            prefix = image_dir / "page"
            ok, pdfppm_stderr = pdf_to_images(pdf_path, prefix, password=password)
            if not ok:
                stderr = pdfppm_stderr or stderr
                continue
            texts: list[str] = []
            page_images = sorted(image_dir.glob("page-*.png"))
            for img in page_images:
                ocr_ok, ocr_text = ocr_image(img)
                if ocr_ok and ocr_text.strip():
                    texts.append(ocr_text)
            if texts:
                txt_path = write_text_output(output_dir, pdf_path, "\n\n".join(texts))
                return {
                    "source_file": str(pdf_path),
                    "text_txt": str(txt_path),
                    "method": "pdf_ocr" if not password else "pdf_ocr_password",
                    "password_source": source,
                    "password_used": redact_password(password),
                    "candidate_count": str(len(candidates)),
                    "status": "ok_ocr",
                    "notes": "",
                }
    else:
        if not pdftoppm_bin:
            notes_parts.append("missing=pdftoppm")
        if not tesseract_bin:
            notes_parts.append("missing=tesseract")

    missing_dependency_only = bool(missing_bins) and not pdftotext_bin and (not pdftoppm_bin or not tesseract_bin)
    if missing_dependency_only:
        status = "missing_dependency"
    elif missing_bins and not (pdftoppm_bin and tesseract_bin):
        status = "missing_dependency"
    else:
        status = "fail"

    return {
        "source_file": str(pdf_path),
        "text_txt": "",
        "method": "",
        "password_source": "",
        "password_used": "",
        "candidate_count": str(len(candidates)),
        "status": status,
        "notes": "; ".join(filter(None, [stderr, *notes_parts, "attempted=" + ", ".join(attempted[:12])]))[:2000],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract text from PDFs, including password-protected PDFs, using pdftotext or OCR.")
    parser.add_argument("input_path", help="PDF file or directory")
    parser.add_argument("output_dir", help="Directory for extracted text outputs")
    parser.add_argument("--thread-json", default="", help="Optional thread context JSON")
    parser.add_argument("--provider-json", default="", help="Optional provider context JSON")
    args = parser.parse_args()

    input_path = Path(args.input_path).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    thread_json = normalize_thread_json(read_json(Path(args.thread_json).expanduser())) if args.thread_json else {}
    provider_json = read_json(Path(args.provider_json).expanduser()) if args.provider_json else {}

    rows: list[dict[str, str]] = []
    for pdf_path in iter_pdfs(input_path):
        rows.append(try_extract(pdf_path, output_dir, thread_json, provider_json))

    manifest = output_dir / "pdf_text_manifest.tsv"
    with manifest.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["source_file", "text_txt", "method", "password_source", "password_used", "candidate_count", "status", "notes"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
