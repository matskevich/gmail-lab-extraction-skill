from __future__ import annotations

import getpass
import os
import re
import sys
from collections.abc import Callable, Mapping
from datetime import datetime

from gmail_lab.core.secrets.models import (
    RememberSecret,
    SecretCandidate,
    SecretContext,
    SecretMetadata,
    SecretPersistence,
    SecretScope,
)
from gmail_lab.core.secrets.store import MemorySecretStore, SecretStore, SecretStoreUnavailable

PromptFn = Callable[[str], str]


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
    seen: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            dt = normalize_date(match.group(0))
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
    seen: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            password = match.group(1)
            if password in seen:
                continue
            seen.add(password)
            out.append(password)
    return out


def detect_hint_type(text: str) -> str:
    if re.search(r"birth date|date of birth|dob|ddmmyyyy|tanggal lahir", text, re.I):
        return "birth_date_ddmmyyyy"
    if re.search(r"password|passcode|kata sandi", text, re.I):
        return "password_hint"
    return ""


def _expand_secret_value(value: str, source: str, scope: SecretScope | str, persistence: SecretPersistence, hint_type: str, secret_id: str = "") -> list[SecretCandidate]:
    dt = normalize_date(value)
    if dt and hint_type == "birth_date_ddmmyyyy":
        return [
            SecretCandidate(
                value=password,
                source=source,
                scope=scope,
                persistence=persistence,
                secret_id=secret_id,
                hint_type=hint_type,
            )
            for password in password_candidates_from_datetime(dt)
        ]
    return [
        SecretCandidate(
            value=value,
            source=source,
            scope=scope,
            persistence=persistence,
            secret_id=secret_id,
            hint_type=hint_type,
        )
    ]


class SecretResolver:
    def __init__(
        self,
        store: SecretStore | None = None,
        session_store: MemorySecretStore | None = None,
        env: Mapping[str, str] | None = None,
        prompt_fn: PromptFn | None = None,
    ) -> None:
        self.store = store
        self.session_store = session_store or MemorySecretStore()
        self.env = env or os.environ
        self.prompt_fn = prompt_fn or getpass.getpass

    def hint_type(self, context: SecretContext) -> str:
        return detect_hint_type("\n".join([context.hint_text, context.thread_text, context.provider_text]))

    def candidates(
        self,
        context: SecretContext,
        *,
        prompt_secrets: bool = False,
        remember_secret: RememberSecret = "never",
    ) -> list[SecretCandidate]:
        hint_type = self.hint_type(context)
        out: list[SecretCandidate] = []
        seen: set[str] = set()

        def add_many(candidates: list[SecretCandidate]) -> None:
            for candidate in candidates:
                key = candidate.value
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(candidate)

        for raw in self.env.get("PDF_PASSWORD_CANDIDATES", "").split(","):
            value = raw.strip()
            if value:
                add_many(_expand_secret_value(value, "env_password_candidates", context.suggested_scope(), "env", hint_type))

        birth_date_env = self.env.get("PDF_BIRTH_DATE", "")
        if birth_date_env.strip():
            add_many(_expand_secret_value(birth_date_env, "env_birth_date", "identity", "env", "birth_date_ddmmyyyy"))

        for scope, secret_id in context.scoped_secret_ids():
            session_value = self.session_store.get(secret_id)
            if session_value:
                add_many(_expand_secret_value(session_value, "session_cache", scope, "session", hint_type, secret_id))

        if self.store:
            for scope, secret_id in context.scoped_secret_ids():
                stored_value, persistence = self.store.get(secret_id)
                if stored_value:
                    source = "keychain" if persistence == "keychain" else "encrypted_file"
                    add_many(_expand_secret_value(stored_value, source, scope, persistence, hint_type, secret_id))

        for password in extract_explicit_passwords(context.thread_text):
            add_many(_expand_secret_value(password, "thread_explicit_password", "gmail_thread", "message", hint_type))

        env_prompt = self.env.get("PDF_PASSWORD_PROMPT", "").lower() in {"1", "true", "yes"}
        if prompt_secrets or env_prompt:
            add_many(self._prompt_candidates(context, hint_type, remember_secret))

        return out

    def _prompt_candidates(
        self,
        context: SecretContext,
        hint_type: str,
        remember_secret: RememberSecret,
    ) -> list[SecretCandidate]:
        if not sys.stdin.isatty():
            return []
        try:
            raw = self.prompt_fn("PDF password/date hint for this run (blank to skip, comma-separated ok): ")
        except (EOFError, KeyboardInterrupt):
            return []

        candidates: list[SecretCandidate] = []
        for token in re.split(r"[,\s;]+", raw.strip()):
            if not token:
                continue
            source = "prompt_birth_date" if normalize_date(token) else "prompt_password_candidates"
            persistence: SecretPersistence = remember_secret if remember_secret != "never" else "never"
            scope = context.suggested_scope()
            secret_id = context.suggested_secret_id(scope)
            candidates.extend(_expand_secret_value(token, source, scope, persistence, hint_type, secret_id))
            self._remember(secret_id, token, context, hint_type, scope, remember_secret)
        return candidates

    def _remember(
        self,
        secret_id: str,
        value: str,
        context: SecretContext,
        hint_type: str,
        scope: SecretScope,
        remember_secret: RememberSecret,
    ) -> None:
        if remember_secret == "never":
            return
        metadata = SecretMetadata(
            secret_id=secret_id,
            label=hint_type or "pdf_password",
            provider=context.provider,
            identity_alias=context.identity_alias,
            hint_type=hint_type,
            scope=scope,
            persistence=remember_secret,
            evidence_sha256=context.attachment_sha256,
        )
        if remember_secret == "session":
            self.session_store.put(secret_id, value, metadata)
            return
        if self.store is None:
            self.store = SecretStore()
        try:
            self.store.put(secret_id, value, metadata)
        except SecretStoreUnavailable:
            return
