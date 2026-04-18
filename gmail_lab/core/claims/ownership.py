from __future__ import annotations

import re
from collections.abc import Iterable

from gmail_lab.core.claims.models import NameSignal
from gmail_lab.core.config import IdentityConfig


def _normalize_name(value: str) -> str:
    text = value.lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9]+", " ", text)
    return " ".join(text.split())


def _token_set(value: str) -> set[str]:
    return set(_normalize_name(value).split())


def _is_same_person(candidate: str, reference: str) -> bool:
    candidate_tokens = _token_set(candidate)
    reference_tokens = _token_set(reference)
    if not candidate_tokens or not reference_tokens:
        return False
    return candidate_tokens == reference_tokens or candidate_tokens.issuperset(reference_tokens) or reference_tokens.issuperset(candidate_tokens)


def _match_any(candidate: str, values: Iterable[str]) -> bool:
    return any(_is_same_person(candidate, value) for value in values if value.strip())


def _clean_name_value(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip(" ,.;:|")
    trailing_markers = [
        r"\bЗаказ\b.*$",
        r"\bЗая\s*вка\b.*$",
        r"\bЗаявка\b.*$",
        r"\bMobile Phone\b.*$",
        r"\bDOB\b.*$",
        r"\bПол\b.*$",
        r"\bВозраст\b.*$",
        r"\bИНЗ\b.*$",
    ]
    for marker in trailing_markers:
        text = re.sub(marker, "", text, flags=re.IGNORECASE).strip(" ,.;:|")
    return text


def extract_name_signals(text: str) -> list[NameSignal]:
    signals: list[NameSignal] = []
    patterns = [
        (r"Пациент:\s*([^\n]+)", "patient_label"),
        (r"Ф\.И\.О\.\s*:\s*([^\n]+)", "fio_label"),
        (r"Patient Name\s*:\s*([^\n]+)", "patient_name_label"),
        (r"Dear\s+(Mr|Mrs|Ms)\s+([A-Za-z][^\n,]+)", "salutation"),
        (r"Уважаемый\s+([А-ЯЁA-Z][^\n!,]+)", "salutation"),
        (r"^\s*([А-ЯЁ-]+\s+[А-ЯЁ-]+\s+[А-ЯЁ-]+)\s+(?:ООО|Пол:|Возраст:)", "header_name"),
        (r"\b(Mr|Mrs|Ms)\.?\s+([A-Z][A-Za-z-]+\s+[A-Z][A-Za-z-]+(?:\s+[A-Z][A-Za-z-]+)?)", "header_name"),
    ]
    for pattern, source in patterns:
        for match in re.finditer(pattern, text, re.MULTILINE):
            if source in {"salutation", "header_name"} and match.lastindex and match.lastindex > 1:
                value = " ".join(group.strip() for group in match.groups() if group)
            else:
                value = (match.group(1) if match.lastindex else match.group(0)).strip()
            value = _clean_name_value(value)
            if not value:
                continue
            signals.append(NameSignal(name=value, source=source, evidence=value))
    return signals


def resolve_owner(
    *,
    identity: IdentityConfig,
    text_sources: list[tuple[str, str]],
) -> tuple[str, str, str]:
    all_signals: list[NameSignal] = []
    for source_name, text in text_sources:
        for signal in extract_name_signals(text):
            all_signals.append(
                NameSignal(
                    name=signal.name,
                    source=f"{source_name}:{signal.source}",
                    evidence=signal.evidence,
                )
            )

    if not identity.canonical_name.strip():
        if all_signals:
            first = all_signals[0]
            return first.name, "unknown_owner", first.source
        return "unknown-owner", "unknown_owner", "none"

    allowed_names = [identity.canonical_name, *identity.aliases]
    for signal in all_signals:
        if _match_any(signal.name, identity.known_non_owner_names):
            return signal.name, "non_owner", signal.source

    strong_sources = {"artifact_text:patient_label", "artifact_text:fio_label", "artifact_text:patient_name_label", "artifact_text:header_name"}
    weak_sources = {"message_context:salutation", "message_context:header_name", "artifact_text:salutation"}

    for signal in all_signals:
        if _match_any(signal.name, allowed_names):
            if signal.source in strong_sources:
                return signal.name, "confirmed_owner", signal.source
            if signal.source in weak_sources:
                return signal.name, "likely_owner", signal.source
            return signal.name, "weak_owner", signal.source

    if all_signals:
        first = all_signals[0]
        return first.name, "non_owner", first.source
    return "unknown-owner", "unknown_owner", "none"
