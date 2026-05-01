from __future__ import annotations

from gmail_lab.core.secrets.models import SecretContext, SecretMetadata
from gmail_lab.core.secrets.resolver import SecretResolver
from gmail_lab.core.secrets.store import MemorySecretStore


def test_provider_hint_without_local_secret_does_not_create_candidate() -> None:
    resolver = SecretResolver(store=None, env={})
    context = SecretContext(
        provider="prodia",
        hint_text="for the password is your birth date DDMMYYYY",
    )

    assert resolver.hint_type(context) == "birth_date_ddmmyyyy"
    assert resolver.candidates(context) == []


def test_env_birth_date_remains_v0_automation_source() -> None:
    resolver = SecretResolver(store=None, env={"PDF_BIRTH_DATE": "1970-01-31"})
    context = SecretContext(
        provider="prodia",
        hint_text="for the password is your birth date DDMMYYYY",
    )

    candidates = resolver.candidates(context)

    assert {candidate.value for candidate in candidates} >= {"31011970", "19700131"}
    assert {candidate.source for candidate in candidates} == {"env_birth_date"}
    assert {candidate.persistence for candidate in candidates} == {"env"}


def test_session_secret_expands_birth_date_hint_without_plaintext_manifest_source() -> None:
    session_store = MemorySecretStore()
    context = SecretContext(
        provider="prodia",
        identity_alias="default",
        hint_text="for the password is your birth date DDMMYYYY",
    )
    secret_id = context.suggested_secret_id("provider_identity")
    session_store.put(
        secret_id,
        "1970-01-31",
        SecretMetadata(
            secret_id=secret_id,
            provider="prodia",
            hint_type="birth_date_ddmmyyyy",
            scope="provider_identity",
            persistence="session",
        ),
    )
    resolver = SecretResolver(store=None, session_store=session_store, env={})

    candidates = resolver.candidates(context)

    assert {candidate.value for candidate in candidates} >= {"31011970", "19700131"}
    assert {candidate.source for candidate in candidates} == {"session_cache"}
    assert {candidate.scope for candidate in candidates} == {"provider_identity"}
    assert {candidate.persistence for candidate in candidates} == {"session"}
