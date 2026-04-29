#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import subprocess
from pathlib import Path


GMAIL_HEADER = [
    "line_no",
    "slug",
    "mode",
    "status",
    "extracted_count",
    "ocr_status",
    "pdf_text_status",
    "enrichment_status",
    "raw_dir",
    "ocr_manifest",
    "pdf_text_manifest",
    "json_log",
    "stderr_log",
    "query",
    "needle",
]

PORTAL_HEADER = [
    "line_no",
    "provider",
    "locator",
    "row_needle",
    "patient_hint",
    "portal_url",
    "status",
    "pdf_text_status",
    "enrichment_status",
    "raw_dir",
    "pdf_text_manifest",
    "thread_json",
    "provider_json",
    "stderr_log",
]


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return list(reader.fieldnames or []), list(reader)


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def summarize_ocr_manifest(path: Path) -> str:
    if not path.exists():
        return "not_applicable"
    _, rows = read_tsv(path)
    if not rows:
        return "not_applicable"
    statuses = {row.get("status", "") for row in rows}
    if statuses == {"ok"}:
        return "ok"
    if "missing_dependency" in statuses and statuses <= {"ok", "missing_dependency"}:
        return "partial" if "ok" in statuses else "missing_dependency"
    if "fail" in statuses and statuses <= {"ok", "fail"}:
        return "partial" if "ok" in statuses else "fail"
    if "missing_dependency" in statuses or "fail" in statuses:
        return "partial" if "ok" in statuses else ("missing_dependency" if "missing_dependency" in statuses and "fail" not in statuses else "fail")
    return "unknown"


def summarize_pdf_text_manifest(path: Path) -> str:
    if not path.exists():
        return "not_applicable"
    _, rows = read_tsv(path)
    if not rows:
        return "not_applicable"
    statuses = {row.get("status", "") for row in rows}
    ok_statuses = {"ok_text", "ok_ocr"}
    if statuses and statuses <= ok_statuses:
        return "ok"
    if "needs_password_hint" in statuses and statuses <= (ok_statuses | {"needs_password_hint"}):
        return "partial" if statuses & ok_statuses else "needs_password_hint"
    if "missing_dependency" in statuses and statuses <= (ok_statuses | {"missing_dependency"}):
        return "partial" if statuses & ok_statuses else "missing_dependency"
    if "fail" in statuses and statuses <= (ok_statuses | {"fail"}):
        return "partial" if statuses & ok_statuses else "fail"
    if "needs_password_hint" in statuses or "missing_dependency" in statuses or "fail" in statuses:
        if statuses & ok_statuses:
            return "partial"
        if "fail" in statuses:
            return "fail"
        if "needs_password_hint" in statuses:
            return "needs_password_hint"
        return "missing_dependency"
    return "unknown"


def combine_status(acquisition_status: str, *statuses: str) -> str:
    if acquisition_status != "ok":
        return "blocked_by_extract_fail"
    effective = [item for item in statuses if item != "not_applicable"]
    if not effective:
        return "not_applicable"
    if all(item == "ok" for item in effective):
        return "ok"
    if any(item == "partial" for item in effective):
        return "partial"
    if any(item == "ok" for item in effective) and any(item in {"missing_dependency", "needs_password_hint", "fail", "unknown"} for item in effective):
        return "partial"
    if any(item == "needs_password_hint" for item in effective) and not any(item in {"missing_dependency", "fail", "unknown"} for item in effective):
        return "needs_password_hint"
    if any(item == "missing_dependency" for item in effective) and not any(item in {"fail", "unknown"} for item in effective):
        return "missing_dependency"
    if any(item == "fail" for item in effective):
        return "fail"
    return "unknown"


def run_cmd(args: list[str], stdout_path: Path, stderr_path: Path) -> None:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("w", encoding="utf-8") as stdout_fh, stderr_path.open("w", encoding="utf-8") as stderr_fh:
        subprocess.run(args, check=False, stdout=stdout_fh, stderr=stderr_fh, text=True)


def maybe_rerun_gmail_row(repo_root: Path, row: dict[str, str], rerun_all: bool) -> dict[str, str]:
    if row.get("status") != "ok":
        row["ocr_status"] = row.get("ocr_status", "not_applicable") or "not_applicable"
        row["pdf_text_status"] = row.get("pdf_text_status", "not_applicable") or "not_applicable"
        row["enrichment_status"] = "blocked_by_extract_fail"
        return row

    if not rerun_all and row.get("enrichment_status") == "ok":
        return row

    raw_dir = Path(row["raw_dir"])
    run_dir = raw_dir.parent.parent
    log_dir = run_dir / "logs"
    ocr_dir = run_dir / "ocr" / raw_dir.name
    pdf_text_dir = run_dir / "pdf_text" / raw_dir.name
    ocr_manifest = ocr_dir / "ocr_manifest.tsv"
    pdf_text_manifest = pdf_text_dir / "pdf_text_manifest.tsv"
    json_log = Path(row["json_log"])

    run_cmd(
        ["python3", str(repo_root / "skills/gmail-browser-attachments/scripts/ocr_image_assets.py"), str(raw_dir), str(ocr_dir)],
        log_dir / f"{raw_dir.name}.ocr.stdout.log",
        log_dir / f"{raw_dir.name}.ocr.stderr.log",
    )
    run_cmd(
        ["python3", str(repo_root / "scripts/extract_pdf_text.py"), str(raw_dir), str(pdf_text_dir), "--thread-json", str(json_log)],
        log_dir / f"{raw_dir.name}.pdf_text.stdout.log",
        log_dir / f"{raw_dir.name}.pdf_text.stderr.log",
    )

    row["ocr_manifest"] = str(ocr_manifest) if ocr_manifest.exists() else "-"
    row["pdf_text_manifest"] = str(pdf_text_manifest) if pdf_text_manifest.exists() else "-"
    row["ocr_status"] = summarize_ocr_manifest(ocr_manifest) if ocr_manifest.exists() else "not_applicable"
    row["pdf_text_status"] = summarize_pdf_text_manifest(pdf_text_manifest) if pdf_text_manifest.exists() else "not_applicable"
    row["enrichment_status"] = combine_status(row["status"], row["ocr_status"], row["pdf_text_status"])
    return row


def maybe_rerun_portal_row(repo_root: Path, row: dict[str, str], rerun_all: bool) -> dict[str, str]:
    if row.get("status") != "ok":
        row["pdf_text_status"] = row.get("pdf_text_status", "not_applicable") or "not_applicable"
        row["enrichment_status"] = "blocked_by_extract_fail"
        return row

    if not rerun_all and row.get("enrichment_status") == "ok":
        return row

    raw_dir = Path(row["raw_dir"])
    run_dir = raw_dir.parent.parent
    log_dir = run_dir / "logs"
    pdf_text_dir = run_dir / "pdf_text" / raw_dir.name
    pdf_text_manifest = pdf_text_dir / "pdf_text_manifest.tsv"
    thread_json = Path(row["thread_json"])
    provider_json = Path(row["provider_json"])

    run_cmd(
        [
            "python3",
            str(repo_root / "scripts/extract_pdf_text.py"),
            str(raw_dir),
            str(pdf_text_dir),
            "--thread-json",
            str(thread_json),
            "--provider-json",
            str(provider_json),
        ],
        log_dir / f"{raw_dir.name}.pdf_text.stdout.log",
        log_dir / f"{raw_dir.name}.pdf_text.stderr.log",
    )

    row["pdf_text_manifest"] = str(pdf_text_manifest) if pdf_text_manifest.exists() else "-"
    row["pdf_text_status"] = summarize_pdf_text_manifest(pdf_text_manifest) if pdf_text_manifest.exists() else "not_applicable"
    row["enrichment_status"] = combine_status(row["status"], row["pdf_text_status"])
    return row


def ensure_columns(fieldnames: list[str], required: list[str]) -> list[str]:
    extras = [name for name in fieldnames if name not in required]
    return [*required, *extras]


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-run OCR/PDF-text enrichment for an existing run directory.")
    parser.add_argument("run_dir", help="Existing run directory with run_manifest.tsv")
    parser.add_argument("--all", action="store_true", help="Re-run enrichment for all successful rows, not only non-ok rows")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = run_dir / "run_manifest.tsv"
    if not manifest_path.exists():
      raise SystemExit(f"missing run manifest: {manifest_path}")

    fieldnames, rows = read_tsv(manifest_path)
    if not rows:
        print(run_dir)
        return 0

    is_gmail = "ocr_manifest" in fieldnames or "mode" in fieldnames
    if is_gmail:
        fieldnames = ensure_columns(fieldnames, GMAIL_HEADER)
        rows = [maybe_rerun_gmail_row(repo_root, row, args.all) for row in rows]
    else:
        fieldnames = ensure_columns(fieldnames, PORTAL_HEADER)
        rows = [maybe_rerun_portal_row(repo_root, row, args.all) for row in rows]

    write_tsv(manifest_path, fieldnames, rows)
    run_cmd(
        ["python3", str(repo_root / "scripts/derive_asset_metadata.py"), str(run_dir)],
        run_dir / "logs/asset_metadata.stdout.log",
        run_dir / "logs/asset_metadata.stderr.log",
    )
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
