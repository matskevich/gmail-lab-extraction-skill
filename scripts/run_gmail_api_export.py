#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmail_lab.core.google_auth import build_gmail_service, load_google_credentials
from gmail_lab.core.manifests.evidence import write_evidence_manifest
from gmail_lab.core.models import EvidenceRecord

RUN_HEADER = [
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


def ensure_runtime_python() -> None:
    venv_python = REPO_ROOT / ".venv/bin/python"
    venv_root = REPO_ROOT / ".venv"
    if not venv_python.exists() or Path(sys.prefix).resolve() == venv_root.resolve():
        return
    os.execv(str(venv_python), [str(venv_python), *sys.argv])


@dataclass(frozen=True)
class Target:
    line_no: int
    locator: str
    needle: str
    mode: str


@dataclass(frozen=True)
class AttachmentAsset:
    message_id: str
    thread_id: str
    part_id: str
    filename: str
    mime_type: str
    attachment_id: str
    inline_data: str


def slugify(value: str) -> str:
    text = re.sub(r"\s+", "-", value.strip().lower())
    text = re.sub(r"[^a-z0-9_.-]+", "-", text, flags=re.IGNORECASE)
    text = re.sub(r"-{2,}", "-", text).strip("-.")
    return text[:80] or "target"


def sanitize_filename(value: str) -> str:
    name = Path(value).name.replace("\x00", "").replace(":", "_").strip()
    return name or "attachment.bin"


def decode_gmail_base64(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def header_value(message: dict[str, Any], name: str) -> str:
    headers = message.get("payload", {}).get("headers", [])
    for item in headers:
        if str(item.get("name", "")).lower() == name.lower():
            return str(item.get("value", ""))
    return ""


def message_internal_date(message: dict[str, Any]) -> str:
    raw = str(message.get("internalDate", "")).strip()
    if raw.isdigit():
        return datetime.fromtimestamp(int(raw) / 1000, tz=UTC).isoformat()
    date_header = header_value(message, "Date")
    if date_header:
        try:
            return parsedate_to_datetime(date_header).astimezone(UTC).isoformat()
        except Exception:
            return date_header
    return ""


def iter_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out = [payload]
    for part in payload.get("parts", []) or []:
        if isinstance(part, dict):
            out.extend(iter_parts(part))
    return out


def attachment_assets(message: dict[str, Any]) -> list[AttachmentAsset]:
    assets: list[AttachmentAsset] = []
    for part in iter_parts(message.get("payload", {})):
        filename = str(part.get("filename", "")).strip()
        body = part.get("body", {}) if isinstance(part.get("body", {}), dict) else {}
        attachment_id = str(body.get("attachmentId", "")).strip()
        inline_data = str(body.get("data", "")).strip()
        if not filename or (not attachment_id and not inline_data):
            continue
        assets.append(
            AttachmentAsset(
                message_id=str(message.get("id", "")),
                thread_id=str(message.get("threadId", "")),
                part_id=str(part.get("partId", "")),
                filename=filename,
                mime_type=str(part.get("mimeType", "")) or "application/octet-stream",
                attachment_id=attachment_id,
                inline_data=inline_data,
            )
        )
    return assets


def text_parts(message: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for part in iter_parts(message.get("payload", {})):
        mime_type = str(part.get("mimeType", ""))
        body = part.get("body", {}) if isinstance(part.get("body", {}), dict) else {}
        data = str(body.get("data", "")).strip()
        if data and mime_type.startswith("text/"):
            try:
                texts.append(decode_gmail_base64(data).decode("utf-8", errors="ignore"))
            except Exception:
                continue
    return texts


def message_haystack(message: dict[str, Any]) -> str:
    assets = attachment_assets(message)
    bits = [
        str(message.get("id", "")),
        str(message.get("threadId", "")),
        str(message.get("snippet", "")),
        header_value(message, "Subject"),
        header_value(message, "From"),
        header_value(message, "Date"),
        "\n".join(asset.filename for asset in assets),
        "\n".join(text_parts(message)),
    ]
    return "\n".join(bits)


def provider_hints(text: str) -> dict[str, bool]:
    return {
        "invitro": bool(re.search(r"ИНВИТРО|INVITRO", text, re.I)),
        "cmd": bool(re.search(r"\bCMD\b", text, re.I)),
        "kdl": bool(re.search(r"\bKDL\b", text, re.I)),
        "hemotest": bool(re.search(r"Гемотест|Hemotest", text, re.I)),
        "dnkom": bool(re.search(r"ДНКОМ|DNKOM", text, re.I)),
        "prodia": bool(re.search(r"Prodia", text, re.I)),
    }


def choose_message(messages: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    if not messages:
        return None
    if not needle:
        return messages[0]
    needle_lower = needle.lower()
    for message in messages:
        if needle_lower in message_haystack(message).lower():
            return message
    return None


def read_targets(path: Path) -> list[Target]:
    targets: list[Target] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for index, row in enumerate(csv.reader(fh, delimiter="\t"), start=1):
            if not row or not "".join(row).strip():
                continue
            locator = row[0].strip()
            if not locator or locator.startswith("#"):
                continue
            needle = row[1].strip() if len(row) > 1 else ""
            mode = row[2].strip() if len(row) > 2 and row[2].strip() else "api"
            targets.append(Target(index, locator, needle, mode))
    return targets


def list_full_messages(service: Any, query: str, max_results: int) -> list[dict[str, Any]]:
    response = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    refs = response.get("messages", []) or []
    out = []
    for ref in refs:
        message_id = ref.get("id")
        if not message_id:
            continue
        out.append(
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
    return out


def api_id_from_locator(locator: str, *prefixes: str) -> str:
    value = locator.strip()
    for prefix in prefixes:
        if value.lower().startswith(prefix):
            return value[len(prefix) :].strip()
    return ""


def is_probable_api_id(locator: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{12,32}", locator.strip(), re.I))


def is_gmail_ui_url(locator: str) -> bool:
    return "mail.google.com/" in locator and "/#" in locator


def resolve_full_messages(service: Any, locator: str, max_results: int) -> list[dict[str, Any]]:
    message_id = api_id_from_locator(locator, "message:", "msg:", "gmail-api-message:")
    thread_id = api_id_from_locator(locator, "thread:", "gmail-api-thread:")
    if message_id or (is_probable_api_id(locator) and not thread_id):
        resolved_id = message_id or locator.strip()
        return [
            service.users()
            .messages()
            .get(userId="me", id=resolved_id, format="full")
            .execute()
        ]
    if thread_id:
        thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
        return list(thread.get("messages", []) or [])
    if is_gmail_ui_url(locator):
        raise RuntimeError(
            "gmail_ui_url_not_api_locator: Gmail web URLs use UI-local ids that are not Gmail API message ids. "
            "Use a Gmail search query, message:<api_message_id>, or thread:<api_thread_id>."
        )
    return list_full_messages(service, locator, max_results)


def download_asset(service: Any, asset: AttachmentAsset) -> bytes:
    if asset.inline_data:
        return decode_gmail_base64(asset.inline_data)
    response = (
        service.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=asset.message_id, id=asset.attachment_id)
        .execute()
    )
    return decode_gmail_base64(str(response.get("data", "")))


def write_unique_file(output_dir: Path, filename: str, content: bytes) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = sanitize_filename(filename)
    target = output_dir / base
    parsed = target.with_suffix("").name
    suffix = target.suffix
    index = 2
    while target.exists():
        target = output_dir / f"{parsed} ({index}){suffix}"
        index += 1
    target.write_bytes(content)
    return target


def run_cmd(args: list[str], stdout_path: Path, stderr_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO_ROOT}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(REPO_ROOT)
    with stdout_path.open("w", encoding="utf-8") as stdout_fh, stderr_path.open("w", encoding="utf-8") as stderr_fh:
        subprocess.run(args, check=False, stdout=stdout_fh, stderr=stderr_fh, text=True, env=env)


def read_tsv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def summarize_pdf_text_manifest(path: Path) -> str:
    rows = read_tsv_rows(path)
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
    if statuses & ok_statuses:
        return "partial"
    if "fail" in statuses:
        return "fail"
    if "needs_password_hint" in statuses:
        return "needs_password_hint"
    if "missing_dependency" in statuses:
        return "missing_dependency"
    return "unknown"


def combine_enrichment_status(status: str, pdf_text_status: str) -> str:
    if status != "ok":
        return "blocked_by_extract_fail"
    if pdf_text_status == "not_applicable":
        return "not_applicable"
    return pdf_text_status


def write_run_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RUN_HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def process_target(service: Any, target: Target, run_dir: Path, max_results: int) -> tuple[dict[str, str], list[EvidenceRecord]]:
    slug = slugify(f"{target.line_no}-{target.needle or target.locator}")
    raw_dir = run_dir / "raw" / slug
    pdf_text_dir = run_dir / "pdf_text" / slug
    log_dir = run_dir / "logs"
    json_log = log_dir / f"{slug}.extract.json"
    stderr_log = log_dir / f"{slug}.extract.stderr.log"
    pdf_text_manifest = pdf_text_dir / "pdf_text_manifest.tsv"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pdf_text_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    stderr_log.write_text("", encoding="utf-8")

    status = "ok"
    saved: list[dict[str, Any]] = []
    evidence_rows: list[EvidenceRecord] = []
    message: dict[str, Any] | None = None
    try:
        messages = resolve_full_messages(service, target.locator, max_results)
        message = choose_message(messages, target.needle)
        if not message:
            raise RuntimeError(f"no gmail api message matched needle: {target.needle}")
        assets = attachment_assets(message)
        if not assets:
            raise RuntimeError("matched message has no gmail-native attachments")
        for asset in assets:
            content = download_asset(service, asset)
            out_path = write_unique_file(raw_dir, asset.filename, content)
            saved.append(
                {
                    "kind": "attachment",
                    "filename": asset.filename,
                    "size": len(content),
                    "saved_to": str(out_path),
                    "message_id": asset.message_id,
                    "part_id": asset.part_id,
                    "mimeType": asset.mime_type,
                }
            )
            evidence_rows.append(
                EvidenceRecord(
                    mailbox="gmail-api",
                    message_id=asset.message_id,
                    source_kind="attachment",
                    original_filename=asset.filename,
                    stored_path=str(out_path.resolve()),
                    mime_type=asset.mime_type,
                    size_bytes=len(content),
                    sha256=sha256(content).hexdigest(),
                    created_at=datetime.now(UTC).isoformat(),
                )
            )
    except Exception as exc:
        status = "extract_fail"
        stderr_log.write_text(str(exc), encoding="utf-8")

    thread_text = message_haystack(message) if message else ""
    thread = {
        "title": header_value(message or {}, "Subject"),
        "href": f"gmail-api://message/{message.get('id', '')}" if message else "",
        "bodySnippet": thread_text[:5000],
        "visibleDates": [message_internal_date(message)] if message else [],
        "providerHints": provider_hints(thread_text),
        "attachmentNames": [item["filename"] for item in saved],
        "attachmentCandidateCount": len(attachment_assets(message)) if message else 0,
        "downloadUrlCount": len(saved),
        "inlineCandidateCount": 0,
        "scanningForViruses": False,
    }
    json_log.write_text(
        json.dumps(
            {
                "query": target.locator,
                "rowNeedle": target.needle,
                "transport": "gmail_api",
                "thread": thread,
                "savedCounts": {"attachment": len(saved)},
                "saved": saved,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    pdf_text_status = "not_applicable"
    if status == "ok":
        run_cmd(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/extract_pdf_text.py"),
                str(raw_dir),
                str(pdf_text_dir),
                "--thread-json",
                str(json_log),
            ],
            log_dir / f"{slug}.pdf_text.stdout.log",
            log_dir / f"{slug}.pdf_text.stderr.log",
        )
        pdf_text_status = summarize_pdf_text_manifest(pdf_text_manifest)

    row = {
        "line_no": str(target.line_no),
        "slug": slug,
        "mode": target.mode,
        "status": status,
        "extracted_count": str(len(saved)),
        "ocr_status": "not_applicable",
        "pdf_text_status": pdf_text_status,
        "enrichment_status": combine_enrichment_status(status, pdf_text_status),
        "raw_dir": str(raw_dir.resolve()),
        "ocr_manifest": "-",
        "pdf_text_manifest": str(pdf_text_manifest.resolve()) if pdf_text_manifest.exists() else "-",
        "json_log": str(json_log.resolve()),
        "stderr_log": str(stderr_log.resolve()),
        "query": target.locator,
        "needle": target.needle,
    }
    return row, evidence_rows


def main() -> int:
    ensure_runtime_python()
    parser = argparse.ArgumentParser(description="Export Gmail-native attachments through the Gmail API.")
    parser.add_argument("targets_tsv", help="TSV rows: <gmail query|message:<api_id>|thread:<api_id>><TAB><needle><TAB><mode?>")
    parser.add_argument("run_dir", nargs="?", default=f"runs/api-run-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    parser.add_argument("--token", default=os.environ.get("GMAIL_LAB_GOOGLE_TOKEN", "~/.gmail-lab/tokens/gmail-api-token.json"))
    parser.add_argument("--client-secrets", default=os.environ.get("GMAIL_LAB_GOOGLE_CLIENT_SECRET", ""))
    parser.add_argument("--no-browser", action="store_true", help="Print OAuth URL and ask for code instead of opening a browser")
    parser.add_argument("--max-results", type=int, default=10)
    args = parser.parse_args()

    targets_path = Path(args.targets_tsv).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "raw").mkdir(exist_ok=True)
    (run_dir / "pdf_text").mkdir(exist_ok=True)
    (run_dir / "logs").mkdir(exist_ok=True)

    token_path = Path(args.token).expanduser().resolve()
    client_secrets_path = Path(args.client_secrets).expanduser().resolve() if args.client_secrets else None
    try:
        creds = load_google_credentials(
            token_path=token_path,
            client_secrets_path=client_secrets_path,
            no_browser=args.no_browser,
        )
        service = build_gmail_service(creds)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    rows: list[dict[str, str]] = []
    evidence_rows: list[EvidenceRecord] = []
    for target in read_targets(targets_path):
        row, target_evidence = process_target(service, target, run_dir, args.max_results)
        rows.append(row)
        evidence_rows.extend(target_evidence)

    write_run_manifest(run_dir / "run_manifest.tsv", rows)
    write_evidence_manifest(run_dir / "evidence_manifest.tsv", evidence_rows)
    run_cmd(
        [sys.executable, str(REPO_ROOT / "scripts/derive_asset_metadata.py"), str(run_dir)],
        run_dir / "logs/asset_metadata.stdout.log",
        run_dir / "logs/asset_metadata.stderr.log",
    )
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
