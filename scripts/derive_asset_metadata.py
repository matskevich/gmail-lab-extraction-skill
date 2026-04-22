#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def json_load(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def slugify(value: str) -> str:
    text = re.sub(r"\s+", "_", value.strip().lower())
    text = re.sub(r"[^0-9a-zа-яё._-]+", "_", text, flags=re.IGNORECASE)
    text = re.sub(r"_+", "_", text).strip("._")
    return text or "unknown"


def tsv_cell(value: object) -> str:
    return re.sub(r"[\t\r\n]+", " ", str(value)).strip()


def parse_english_date(text: str) -> list[str]:
    out = []
    for m in re.finditer(r"(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})", text, re.I):
        mon = MONTHS[m.group("mon").lower()]
        day = int(m.group("day"))
        year = int(m.group("year"))
        out.append(f"{year:04d}-{mon:02d}-{day:02d}")
    return out


def parse_ru_date(text: str) -> list[str]:
    out = []
    for m in re.finditer(r"(?P<day>\d{1,2})\s+(?P<mon>[А-Яа-яЁё]+)\s+(?P<year>\d{4})", text):
        mon_name = m.group("mon").lower()
        if mon_name not in RU_MONTHS:
            continue
        day = int(m.group("day"))
        year = int(m.group("year"))
        mon = RU_MONTHS[mon_name]
        out.append(f"{year:04d}-{mon:02d}-{day:02d}")
    return out


def parse_numeric_dates(text: str) -> list[str]:
    out = []
    for m in re.finditer(r"\b(?P<a>\d{1,2})[./-](?P<b>\d{1,2})[./-](?P<year>\d{4})\b", text):
        a = int(m.group("a"))
        b = int(m.group("b"))
        year = int(m.group("year"))
        if a > 12:
            day, month = a, b
        elif b > 12:
            month, day = a, b
        else:
            day, month = a, b
        if 1 <= month <= 12 and 1 <= day <= 31:
            out.append(f"{year:04d}-{month:02d}-{day:02d}")
    return out


def unique_keep_order(items: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def extract_dates(text: str) -> list[str]:
    return unique_keep_order(parse_english_date(text) + parse_ru_date(text) + parse_numeric_dates(text))


def parse_received_dates_from_body(body: str) -> list[str]:
    dates = []
    for line in body.splitlines():
        if re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),", line):
            dates.extend(parse_english_date(line))
    return unique_keep_order(dates)


def provider_from_context(thread_json: dict, provider_json: dict, query: str) -> tuple[str, str]:
    hints = thread_json.get("providerHints", {}) if isinstance(thread_json, dict) else {}
    for provider in ("invitro", "cmd", "kdl", "hemotest", "dnkom", "prodia"):
        if hints.get(provider):
            return provider, "thread_provider_hint"
    domain_checks = [
        ("hemotest", r"gemotest\.ru|hemotest"),
        ("dnkom", r"dnkom\.ru|dnkom"),
        ("invitro", r"invitro"),
        ("cmd", r"\bcmd\b"),
        ("kdl", r"\bkdl\b"),
        ("prodia", r"prodia"),
    ]
    for provider, pattern in domain_checks:
        if re.search(pattern, query or "", re.I):
            return provider, "query_domain"

    provider_meta = provider_json.get("meta", {}) if isinstance(provider_json, dict) else {}
    provider_text = "\n".join(str(provider_meta.get(k, "")) for k in ("provider", "title", "text", "href"))
    thread_text = "\n".join(str(thread_json.get(k, "")) for k in ("title", "bodySnippet"))
    checks = [
        ("invitro", r"ИНВИТРО|INVITRO"),
        ("cmd", r"\bCMD\b"),
        ("kdl", r"\bKDL\b"),
        ("hemotest", r"Гемотест|Hemotest"),
        ("dnkom", r"ДНКОМ|DNKOM"),
        ("prodia", r"Prodia"),
    ]
    for provider, pattern in checks:
        if re.search(pattern, provider_text, re.I):
            return provider, "provider_page_text"
    for provider, pattern in checks:
        if re.search(pattern, thread_text, re.I):
            return provider, "thread_text"
    return "unknown-provider", "none"


def decode_text(value: str) -> str:
    try:
        return unquote(value)
    except Exception:
        return value


def extract_owner_candidates(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"Client:\s*([^\n]+)", text, re.I):
        out.append((m.group(1).strip(), "provider_client"))
    for m in re.finditer(r"Patient Name\s*:?\s*([^\n|]+?)(?:\s+Mobile Phone\b|$|\|)", text, re.I):
        out.append((m.group(1).strip(), "provider_client"))
    for m in re.finditer(r"Уважаемый\s+([А-ЯЁA-Z][^\n!,]{3,80})", text):
        out.append((m.group(1).strip(), "thread_salutation"))
    for m in re.finditer(r"для\s+([А-ЯЁA-Z][А-ЯЁA-Z\s.,-]{3,80})\s+по заявке", text, re.I):
        out.append((m.group(1).strip(" ,."), "thread_title"))
    for m in re.finditer(r"N заказа\s+\d+,\s*([^\n]+?)\s+-\s+[^@\s]+@gmail", text, re.I):
        out.append((m.group(1).strip(" ,."), "thread_title"))
    for m in re.finditer(r"\b(Mr|Mrs|Ms)\s+([A-Z][A-Za-z-]+\s+[A-Z][A-Za-z-]+(?:\s+[A-Z][A-Za-z-]+)?)", text):
        out.append((f"{m.group(1)} {m.group(2)}".strip(), "filename_or_text_name"))
    for m in re.finditer(r"_([A-Za-zА-Яа-яЁё-]{3,})\.(?:pdf|jpg|jpeg|png)\b", text, re.I):
        out.append((m.group(1).strip(), "filename_name"))
    for m in re.finditer(
        r"([А-ЯЁ][А-ЯЁа-яё-]+(?:\s+[А-ЯЁ][А-ЯЁа-яё-]+){1,2})(?=[\s._-]*(?:\d{7,}|\.pdf|$))",
        text,
    ):
        out.append((m.group(1).strip(), "filename_name"))
    return out


def choose_owner(*texts: str) -> tuple[str, str]:
    seen = []
    for text in texts:
        seen.extend(extract_owner_candidates(decode_text(text or "")))
    source_priority = {
        "provider_client": 0,
        "thread_salutation": 1,
        "thread_title": 2,
        "filename_or_text_name": 3,
        "filename_name": 4,
    }
    if seen:
        return sorted(seen, key=lambda item: source_priority.get(item[1], 99))[0]
    return "unknown-owner", "none"


def analysis_date_status(source: str) -> str:
    if source in {"provider_page", "artifact_contextual_date"}:
        return "direct"
    if source in {"gmail_received_or_thread", "filename"}:
        return "inferred"
    return "fallback"


def owner_status(source: str) -> str:
    if source in {"provider_client", "thread_salutation", "thread_title"}:
        return "likely_owner"
    if source in {"filename_or_text_name", "filename_name"}:
        return "weak_owner"
    return "unknown_owner"


def overall_confidence(date_status: str, owner_status_value: str, provider: str) -> str:
    provider_known = provider != "unknown-provider"
    if date_status == "direct" and owner_status_value == "likely_owner" and provider_known:
        return "high"
    if date_status in {"direct", "inferred"} and owner_status_value in {"likely_owner", "weak_owner"}:
        return "medium"
    if date_status == "inferred" and provider_known:
        return "medium"
    return "low"


def is_non_result_asset(filename: str) -> bool:
    decoded = decode_text(filename or "").lower()
    non_result_patterns = [
        r"\bпамятк",
        r"\binstruction\b",
        r"\bmemo\b",
        r"\bpromo\b",
        r"\badvert",
        r"\bnewsletter\b",
    ]
    return any(re.search(pattern, decoded, re.I) for pattern in non_result_patterns)


def is_sidecar_asset(filename: str) -> bool:
    decoded = decode_text(filename or "").lower()
    return decoded.endswith(".sig")


def choose_analysis_date(
    provider_json: dict,
    thread_json: dict,
    ocr_texts: list[str],
    pdf_texts: list[str],
    file_name: str,
    received_fallback: str,
) -> tuple[str, str]:
    provider_meta = provider_json.get("meta", {}) if isinstance(provider_json, dict) else {}
    explicit_analysis_date = extract_dates(str(provider_meta.get("analysisDate", "")))
    if explicit_analysis_date:
        return explicit_analysis_date[0], "provider_page"
    provider_text = "\n".join(
        str(provider_meta.get(k, "")) for k in ("text", "title", "href")
    )
    thread_text = "\n".join(str(thread_json.get(k, "")) for k in ("bodySnippet", "title", "href"))
    file_text = decode_text(file_name)

    provider_dates = [d for d in extract_dates(provider_text) if d not in extract_dates(str(provider_meta.get("birthDate", "")))]
    if provider_dates:
        return provider_dates[0], "provider_page"

    thread_visible_dates = unique_keep_order(
        [*thread_json.get("visibleDates", []), *parse_received_dates_from_body(thread_text), *extract_dates(thread_text)]
    )
    normalized_thread_dates = unique_keep_order([d for item in thread_visible_dates for d in extract_dates(item)])
    if normalized_thread_dates:
        return normalized_thread_dates[0], "gmail_received_or_thread"

    artifact_context_dates = []
    artifact_texts = [*ocr_texts, *pdf_texts]
    artifact_date_tokens = (
        "дата взят",
        "дата исслед",
        "date of collection",
        "specimen date",
        "analysis date",
        "дата анализа",
        "report date",
        "reg no / date",
        "reg no./date",
        "reg no./ date",
        "tanggal",
    )
    for text in artifact_texts:
        for line in text.splitlines():
            low = line.lower()
            if any(token in low for token in artifact_date_tokens):
                artifact_context_dates.extend(extract_dates(line))
    artifact_context_dates = unique_keep_order(artifact_context_dates)
    if artifact_context_dates:
        return artifact_context_dates[0], "artifact_contextual_date"

    filename_dates = extract_dates(file_text)
    if filename_dates:
        return filename_dates[0], "filename"

    return received_fallback, "run_fallback"


def load_ocr_texts(ocr_manifest_path: Path) -> list[str]:
    if not ocr_manifest_path.exists() or ocr_manifest_path.name == "-":
        return []
    rows = read_tsv(ocr_manifest_path)
    texts = []
    for row in rows:
        txt = row.get("ocr_txt", "")
        if not txt:
            continue
        p = Path(txt)
        if p.exists():
            texts.append(p.read_text(encoding="utf-8", errors="ignore"))
    return texts


def load_pdf_texts(pdf_text_manifest_path: Path) -> list[str]:
    if not pdf_text_manifest_path.exists() or pdf_text_manifest_path.name == "-":
        return []
    rows = read_tsv(pdf_text_manifest_path)
    texts = []
    for row in rows:
        txt = row.get("text_txt", "")
        if not txt:
            continue
        p = Path(txt)
        if p.exists():
            texts.append(p.read_text(encoding="utf-8", errors="ignore"))
    return texts


def link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except Exception:
        shutil.copy2(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive analysis date and owner metadata for extracted lab assets.")
    parser.add_argument("run_dir", help="Run directory created by run_gmail_lab_export.sh or run_portal_lab_export.sh")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    manifest_path = run_dir / "run_manifest.tsv"
    if not manifest_path.exists():
        raise SystemExit(f"missing manifest: {manifest_path}")

    rows = read_tsv(manifest_path)
    final_dir = run_dir / "final"
    asset_manifest_path = run_dir / "asset_manifest.tsv"
    out_lines = [
        "raw_file\tfinal_file\tanalysis_date\tanalysis_date_source\tanalysis_date_status\towner_name\towner_source\towner_status\tprovider\tprovider_source\tconfidence\tstatus\n"
    ]

    run_started = "1970-01-01"
    meta_path = run_dir / "run_meta.txt"
    if meta_path.exists():
        meta_text = meta_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"started_at=(\d{4}-\d{2}-\d{2})T", meta_text)
        if m:
            run_started = m.group(1)

    for row in rows:
        if "json_log" in row:
            extract_json = json_load(Path(row["json_log"]))
            query = extract_json.get("query", "") if isinstance(extract_json, dict) else ""
            thread_json = extract_json.get("thread", {}) if isinstance(extract_json, dict) else {}
            provider_json = {}
            saved_items = extract_json.get("saved", []) if isinstance(extract_json, dict) else []
            ocr_texts = load_ocr_texts(Path(row["ocr_manifest"])) if row.get("ocr_manifest", "-") != "-" else []
            pdf_texts = load_pdf_texts(Path(row["pdf_text_manifest"])) if row.get("pdf_text_manifest", "-") != "-" else []
        else:
            query = ""
            provider_json = json_load(Path(row.get("provider_json", "")))
            thread_json = json_load(Path(row.get("thread_json", "")))
            saved_items = []
            raw_dir = Path(row["raw_dir"])
            for file_path in sorted(p for p in raw_dir.glob("*") if p.is_file()):
                saved_items.append({"saved_to": str(file_path), "filename": file_path.name})
            ocr_texts = []
            pdf_texts = load_pdf_texts(Path(row["pdf_text_manifest"])) if row.get("pdf_text_manifest", "-") != "-" else []

        provider, provider_source = provider_from_context(thread_json, provider_json, query)
        owner_name, owner_source = choose_owner(
            str(thread_json.get("title", "")),
            str(thread_json.get("bodySnippet", "")),
            str(thread_json.get("href", "")),
            "\n".join(str(v) for v in (provider_json.get("meta", {}) or {}).values()),
            "\n".join(pdf_texts),
            "\n".join(ocr_texts),
            "\n".join(str(item.get("filename", "")) for item in saved_items),
            "\n".join(str(item.get("saved_to", "")) for item in saved_items),
        )

        for item in saved_items:
            raw_path = Path(item["saved_to"])
            raw_name = item.get("filename") or raw_path.name
            analysis_date, date_source = choose_analysis_date(
                provider_json, thread_json, ocr_texts, pdf_texts, raw_name, run_started
            )
            date_status = analysis_date_status(date_source)
            owner_status_value = owner_status(owner_source)
            confidence = overall_confidence(date_status, owner_status_value, provider)
            if is_sidecar_asset(raw_name):
                final_path = Path("-")
                status = "sidecar"
            elif is_non_result_asset(raw_name):
                final_path = Path("-")
                status = "non_result"
            else:
                canonical_name = f"{analysis_date}__{slugify(provider)}__{slugify(owner_name)}__{raw_path.name}"
                final_path = final_dir / canonical_name
                if raw_path.exists():
                    link_or_copy(raw_path, final_path)
                    status = "ok"
                else:
                    status = "missing_raw"
            out_lines.append(
                "\t".join(
                    tsv_cell(value)
                    for value in (
                        raw_path,
                        final_path,
                        analysis_date,
                        date_source,
                        date_status,
                        owner_name,
                        owner_source,
                        owner_status_value,
                        provider,
                        provider_source,
                        confidence,
                        status,
                    )
                )
                + "\n"
            )

    asset_manifest_path.write_text("".join(out_lines), encoding="utf-8")
    print(asset_manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
