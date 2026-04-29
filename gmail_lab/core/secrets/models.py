from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SecretScope = Literal["attachment_sha256", "gmail_thread", "provider_identity", "identity"]
SecretPersistence = Literal[
    "never",
    "session",
    "keychain",
    "encrypted-file",
    "env",
    "message",
    "none",
]
RememberSecret = Literal["never", "session", "keychain", "encrypted-file"]


@dataclass(frozen=True)
class SecretMetadata:
    secret_id: str
    label: str = ""
    provider: str = ""
    identity_alias: str = ""
    hint_type: str = ""
    scope: SecretScope = "provider_identity"
    persistence: RememberSecret = "never"
    created_at: str = ""
    last_used_at: str = ""
    use_count: int = 0
    evidence_sha256: str = ""


@dataclass(frozen=True)
class SecretCandidate:
    value: str
    source: str
    scope: SecretScope | str = ""
    persistence: SecretPersistence = "never"
    secret_id: str = ""
    hint_type: str = ""


@dataclass(frozen=True)
class SecretContext:
    provider: str = ""
    identity_alias: str = ""
    attachment_sha256: str = ""
    gmail_thread_id: str = ""
    hint_text: str = ""
    thread_text: str = ""
    provider_text: str = ""
    source_file: str = ""

    def scoped_secret_ids(self) -> list[tuple[SecretScope, str]]:
        provider = self.provider.strip().lower() or "unknown-provider"
        identity = self.identity_alias.strip().lower() or "default"
        out: list[tuple[SecretScope, str]] = []
        if self.attachment_sha256:
            out.append(("attachment_sha256", f"attachment_sha256:{self.attachment_sha256}"))
        if self.gmail_thread_id:
            out.append(("gmail_thread", f"gmail_thread:{self.gmail_thread_id}"))
        out.append(("provider_identity", f"provider_identity:{provider}:{identity}"))
        out.append(("identity", f"identity:{identity}"))
        return out

    def suggested_scope(self) -> SecretScope:
        if self.attachment_sha256:
            return "attachment_sha256"
        if self.gmail_thread_id:
            return "gmail_thread"
        if self.provider:
            return "provider_identity"
        return "identity"

    def suggested_secret_id(self, scope: SecretScope | None = None) -> str:
        target_scope = scope or self.suggested_scope()
        for current_scope, secret_id in self.scoped_secret_ids():
            if current_scope == target_scope:
                return secret_id
        return self.scoped_secret_ids()[-1][1]
