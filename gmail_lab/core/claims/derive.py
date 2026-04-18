from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from gmail_lab.core.claims.ownership import resolve_owner
from gmail_lab.core.claims.sample_date import derive_sample_draw_claim
from gmail_lab.core.config import AppConfig
from gmail_lab.core.models import ClaimRecord, EvidenceRecord, MessageRecord

PROVIDER_PATTERNS = [
    ("cmd", r"cmd-online\.ru|\bcmd\b|центр молекулярной диагностики"),
    ("invitro", r"invitro|инвитро"),
    ("dnkom", r"dnkom|днком"),
    ("gemotest", r"gemotest|гемотест|hemotest"),
    ("kdl", r"\bkdl\b"),
    ("prodia", r"prodia"),
]

CATEGORY_PATTERNS = [
    ("minerals_toxicology", r"\bтоксиолог"),
    ("infection_screen", r"\b(?:hiv|hbsag|hcv)\b|(?:\bсифилис\b|\bвич\b)"),
    ("sti_screen", r"\b(?:chlamydia|ureaplasma|mycoplasma|hpv)\b|(?:\bуретр|\bвпч\b)"),
    ("combined_panel", r"тестостерон|эстрадиол|dhea|кортизол|tsh|ft4|витамин d|homocysteine|calprotectin"),
]

ANALYSIS_DATE_PATTERNS = [
    ("artifact_text:analysis_complete", r"Дата выполнения исследования\s*:\s*(\d{2}[./-]\d{2}[./-]\d{4})(?:\s+\d{2}:\d{2}(?::\d{2})?)?"),
    ("artifact_text:report_ready", r"Дата готовности результата\s*:\s*(\d{2}[./-]\d{2}[./-]\d{4})"),
    ("artifact_text:report_printed", r"Дата печати результата\s*:\s*(\d{2}[./-]\d{2}[./-]\d{4})"),
    ("artifact_text:report_generated", r"Дата формирования результата\s*:\s*(\d{2}[./-]\d{2}[./-]\d{4})"),
    ("artifact_text:prodia_reg_date", r"Reg No\./Date\s*:\s*\d+\s*/\s*(\d{2}[./-]\d{2}[./-]\d{4})"),
]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_date(raw: str) -> str:
    raw = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    day, month, year = re.split(r"[./-]", raw)
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def _extract_pdf_text(path: Path) -> str:
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return proc.stdout


def _load_artifact_text(path: Path) -> str:
    sidecars = [
        path.with_suffix(".ocr.txt"),
        path.with_suffix(".txt"),
    ]
    texts = [_safe_read_text(sidecar) for sidecar in sidecars if sidecar.exists()]
    if path.suffix.lower() == ".pdf":
        pdf_text = _extract_pdf_text(path)
        if pdf_text:
            texts.insert(0, pdf_text)
    elif path.suffix.lower() in {".txt", ".md"}:
        texts.insert(0, _safe_read_text(path))
    return "\n".join(part for part in texts if part)


def _load_message_context(message: MessageRecord | None) -> str:
    if message is None:
        return ""
    parts = [message.subject, message.sender, message.snippet]
    for candidate in [message.headers_path, message.full_path, message.raw_path]:
        if candidate:
            parts.append(_safe_read_text(Path(candidate)))
    return "\n".join(part for part in parts if part)


def _detect_provider(message: MessageRecord | None, artifact_text: str, evidence: EvidenceRecord) -> tuple[str, str]:
    context = "\n".join(
        part for part in [
            message.sender if message else "",
            message.subject if message else "",
            evidence.original_filename,
            artifact_text,
        ] if part
    )
    for provider, pattern in PROVIDER_PATTERNS:
        if re.search(pattern, context, re.IGNORECASE):
            return provider, "text_or_sender"
    return "unknown-provider", "none"


def _detect_category(path: Path, artifact_text: str) -> str:
    lowered_path = str(path).lower()
    path_categories = {
        "combined_panels": "combined_panel",
        "minerals_toxicology": "minerals_toxicology",
        "infection_screen": "infection_screen",
        "sti_screen": "sti_screen",
    }
    for path_token, category in path_categories.items():
        if path_token in lowered_path:
            return category
    for category, pattern in CATEGORY_PATTERNS:
        if re.search(pattern, artifact_text, re.IGNORECASE):
            return category
    return "unknown"


def _detect_analysis_date(message: MessageRecord | None, artifact_text: str) -> tuple[str, str]:
    for source, pattern in ANALYSIS_DATE_PATTERNS:
        match = re.search(pattern, artifact_text, re.IGNORECASE)
        if match:
            return _normalize_date(match.group(1)), source
    if message and re.match(r"\d{4}-\d{2}-\d{2}", message.internal_date):
        return message.internal_date[:10], "message_internal_date"
    return "", "missing"


def _owner_confidence(owner_status: str, sample_status: str, analysis_date_source: str, provider: str) -> str:
    if owner_status == "confirmed_owner" and sample_status in {"direct", "inferred_date_only"} and provider != "unknown-provider":
        return "high"
    if owner_status in {"confirmed_owner", "likely_owner"} and analysis_date_source != "missing":
        return "medium"
    if owner_status == "non_owner":
        return "high"
    return "low"


def build_claim_record(
    *,
    config: AppConfig,
    message: MessageRecord | None,
    evidence: EvidenceRecord,
) -> ClaimRecord:
    evidence_path = Path(evidence.stored_path)
    artifact_text = _load_artifact_text(evidence_path)
    message_context = _load_message_context(message)

    provider, provider_source = _detect_provider(message, artifact_text, evidence)
    category = _detect_category(evidence_path, artifact_text)
    owner_name, owner_status, owner_source = resolve_owner(
        identity=config.identity,
        text_sources=[
            ("artifact_text", artifact_text),
            ("message_context", message_context),
        ],
    )
    analysis_date, analysis_date_source = _detect_analysis_date(message, artifact_text)
    sample_claim = derive_sample_draw_claim(
        artifact_text=artifact_text,
        analysis_date=analysis_date,
    )
    confidence = _owner_confidence(owner_status, sample_claim.sample_draw_status, analysis_date_source, provider)
    analysis_id = f"{evidence.message_id}:{evidence.sha256[:16]}"

    owner_evidence = owner_name if owner_name != "unknown-owner" else ""
    return ClaimRecord(
        analysis_id=analysis_id,
        mailbox=evidence.mailbox,
        message_id=evidence.message_id,
        evidence_sha256=evidence.sha256,
        evidence_path=evidence.stored_path,
        provider=provider,
        provider_source=provider_source,
        category=category,
        owner_name=owner_name,
        owner_status=owner_status,
        owner_source=owner_source,
        owner_evidence=owner_evidence,
        analysis_date=analysis_date,
        analysis_date_source=analysis_date_source,
        sample_draw_date=sample_claim.sample_draw_date,
        sample_draw_time=sample_claim.sample_draw_time,
        sample_draw_datetime=sample_claim.sample_draw_datetime,
        sample_draw_status=sample_claim.sample_draw_status,
        sample_draw_source=sample_claim.sample_draw_source,
        sample_draw_evidence=sample_claim.sample_draw_evidence,
        confidence=confidence,
        created_at=_utc_now(),
    )


def claim_to_analysis_row(claim: ClaimRecord) -> dict[str, str]:
    if claim.owner_status == "non_owner":
        status = "context_only"
    elif claim.owner_status == "unknown_owner":
        status = "ambiguous"
    else:
        status = "active"
    return {
        "analysis_id": claim.analysis_id,
        "provider": claim.provider,
        "category": claim.category,
        "canonical_file": claim.evidence_path,
        "owner_name": claim.owner_name,
        "owner_status": claim.owner_status,
        "sample_draw_datetime": claim.sample_draw_datetime,
        "analysis_date": claim.analysis_date,
        "confidence": claim.confidence,
        "status": status,
    }
