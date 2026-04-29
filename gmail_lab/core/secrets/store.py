from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import keyring
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from gmail_lab.core.config import resolve_root
from gmail_lab.core.secrets.models import SecretMetadata, SecretPersistence

SERVICE_NAME = "gmail-lab"


class SecretStoreUnavailable(RuntimeError):
    pass


class PersistentSecretStore(Protocol):
    def get(self, secret_id: str) -> str | None: ...
    def put(self, secret_id: str, value: str, metadata: SecretMetadata) -> None: ...


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _metadata_with_timestamp(metadata: SecretMetadata) -> SecretMetadata:
    created_at = metadata.created_at or _utc_now()
    return SecretMetadata(
        secret_id=metadata.secret_id,
        label=metadata.label,
        provider=metadata.provider,
        identity_alias=metadata.identity_alias,
        hint_type=metadata.hint_type,
        scope=metadata.scope,
        persistence=metadata.persistence,
        created_at=created_at,
        last_used_at=_utc_now(),
        use_count=metadata.use_count + 1,
        evidence_sha256=metadata.evidence_sha256,
    )


class MemorySecretStore:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._metadata: dict[str, SecretMetadata] = {}

    def get(self, secret_id: str) -> str | None:
        return self._values.get(secret_id)

    def put(self, secret_id: str, value: str, metadata: SecretMetadata) -> None:
        if not value:
            return
        self._values[secret_id] = value
        self._metadata[secret_id] = _metadata_with_timestamp(metadata)


class KeyringSecretStore:
    def get(self, secret_id: str) -> str | None:
        try:
            return keyring.get_password(SERVICE_NAME, secret_id)
        except Exception as exc:  # pragma: no cover - backend-dependent
            raise SecretStoreUnavailable(str(exc)) from exc

    def put(self, secret_id: str, value: str, metadata: SecretMetadata) -> None:
        del metadata
        try:
            keyring.set_password(SERVICE_NAME, secret_id, value)
        except Exception as exc:  # pragma: no cover - backend-dependent
            raise SecretStoreUnavailable(str(exc)) from exc


class EncryptedFileSecretStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or resolve_root(None)).expanduser().resolve()
        self.secret_dir = self.root / "secrets"
        self._fernet = self._build_fernet()

    def _build_fernet(self) -> Fernet:
        env_key = os.environ.get("GMAIL_LAB_SECRETS_KEY", "").strip()
        if env_key:
            return Fernet(env_key.encode("utf-8"))

        passphrase = os.environ.get("GMAIL_LAB_SECRETS_PASSPHRASE", "").strip()
        if not passphrase:
            raise SecretStoreUnavailable(
                "encrypted file store requires GMAIL_LAB_SECRETS_KEY or GMAIL_LAB_SECRETS_PASSPHRASE"
            )

        self.secret_dir.mkdir(parents=True, exist_ok=True)
        salt_path = self.secret_dir / "salt.bin"
        if salt_path.exists():
            salt = salt_path.read_bytes()
        else:
            salt = os.urandom(16)
            salt_path.write_bytes(salt)
            salt_path.chmod(0o600)

        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390000)
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
        return Fernet(key)

    def _path_for(self, secret_id: str) -> Path:
        digest = sha256(secret_id.encode("utf-8")).hexdigest()
        return self.secret_dir / f"{digest}.json"

    def get(self, secret_id: str) -> str | None:
        path = self._path_for(secret_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            token = str(payload.get("token", "")).encode("utf-8")
            return self._fernet.decrypt(token).decode("utf-8")
        except (InvalidToken, json.JSONDecodeError, OSError) as exc:
            raise SecretStoreUnavailable(str(exc)) from exc

    def put(self, secret_id: str, value: str, metadata: SecretMetadata) -> None:
        if not value:
            return
        self.secret_dir.mkdir(parents=True, exist_ok=True)
        metadata = _metadata_with_timestamp(metadata)
        token = self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        payload = {"secret_id_sha256": sha256(secret_id.encode("utf-8")).hexdigest(), "token": token, "metadata": asdict(metadata)}
        path = self._path_for(secret_id)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        path.chmod(0o600)


class SecretStore:
    def __init__(
        self,
        root: Path | None = None,
        keychain: PersistentSecretStore | None = None,
        encrypted_file: PersistentSecretStore | None = None,
    ) -> None:
        self.root = (root or resolve_root(None)).expanduser().resolve()
        self.keychain = keychain or KeyringSecretStore()
        self._encrypted_file = encrypted_file

    @property
    def encrypted_file(self) -> PersistentSecretStore:
        if self._encrypted_file is None:
            self._encrypted_file = EncryptedFileSecretStore(self.root)
        return self._encrypted_file

    def get(self, secret_id: str) -> tuple[str | None, SecretPersistence]:
        try:
            value = self.keychain.get(secret_id)
            if value:
                return value, "keychain"
        except SecretStoreUnavailable:
            pass

        try:
            value = self.encrypted_file.get(secret_id)
            if value:
                return value, "encrypted-file"
        except SecretStoreUnavailable:
            pass
        return None, "none"

    def put(self, secret_id: str, value: str, metadata: SecretMetadata) -> SecretPersistence:
        if metadata.persistence == "keychain":
            try:
                self.keychain.put(secret_id, value, metadata)
                return "keychain"
            except SecretStoreUnavailable:
                fallback_metadata = SecretMetadata(**{**asdict(metadata), "persistence": "encrypted-file"})
                self.encrypted_file.put(secret_id, value, fallback_metadata)
                return "encrypted-file"
        if metadata.persistence == "encrypted-file":
            self.encrypted_file.put(secret_id, value, metadata)
            return "encrypted-file"
        raise SecretStoreUnavailable(f"unsupported persistence for persistent store: {metadata.persistence}")
