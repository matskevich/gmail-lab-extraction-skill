from __future__ import annotations

import re

from gmail_lab.core.claims.models import SampleDrawClaim

DATE_PATTERNS = [
    r"(?P<date>\d{2}[./-]\d{2}[./-]\d{4})(?:\s+(?P<time>\d{2}:\d{2}(?::\d{2})?))?",
    r"(?P<date>\d{4}-\d{2}-\d{2})(?:[ T](?P<time>\d{2}:\d{2}(?::\d{2})?))?",
]


def _normalize_date(raw: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    day, month, year = re.split(r"[./-]", raw)
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _normalize_time(raw: str) -> str:
    if not raw:
        return ""
    parts = raw.split(":")
    if len(parts) == 2:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
    return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"


def _extract_labeled_datetime(text: str, labels: list[str]) -> tuple[str, str, str]:
    for line in text.splitlines():
        lower = line.lower()
        if not any(label in lower for label in labels):
            continue
        for pattern in DATE_PATTERNS:
            match = re.search(pattern, line)
            if not match:
                continue
            date_value = _normalize_date(match.group("date"))
            time_value = _normalize_time(match.group("time") or "")
            return date_value, time_value, line.strip()
    return "", "", ""


def derive_sample_draw_claim(
    *,
    artifact_text: str,
    analysis_date: str,
) -> SampleDrawClaim:
    date_value, time_value, evidence = _extract_labeled_datetime(
        artifact_text,
        [
            "дата взятия биоматериала",
            "дата взятия образца",
            "взятие биоматериала",
            "дата забора",
            "дата отбора",
            "sample collection",
            "collection date",
            "specimen date",
            "date of collection",
        ],
    )
    if date_value and time_value:
        return SampleDrawClaim(
            sample_draw_date=date_value,
            sample_draw_time=time_value,
            sample_draw_datetime=f"{date_value}T{time_value}",
            sample_draw_status="direct",
            sample_draw_source="artifact_text",
            sample_draw_evidence=evidence,
        )
    if date_value:
        return SampleDrawClaim(
            sample_draw_date=date_value,
            sample_draw_time="",
            sample_draw_datetime="",
            sample_draw_status="inferred_date_only",
            sample_draw_source="artifact_text",
            sample_draw_evidence=evidence,
        )
    if analysis_date:
        return SampleDrawClaim(
            sample_draw_date=analysis_date,
            sample_draw_time="",
            sample_draw_datetime="",
            sample_draw_status="proxy_analysis_date",
            sample_draw_source="analysis_date",
            sample_draw_evidence=analysis_date,
        )
    return SampleDrawClaim(
        sample_draw_date="",
        sample_draw_time="",
        sample_draw_datetime="",
        sample_draw_status="missing",
        sample_draw_source="none",
        sample_draw_evidence="",
    )
