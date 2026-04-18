from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_ROOT = Path.home() / ".gmail-lab"


class IdentityConfig(BaseModel):
    canonical_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    known_non_owner_names: list[str] = Field(default_factory=list)
    birth_date: str = ""
    emails: list[str] = Field(default_factory=list)


class ProviderHint(BaseModel):
    domain: str
    name: str


class ProvidersConfig(BaseModel):
    known: list[ProviderHint] = Field(default_factory=list)


class AppConfig(BaseModel):
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)


def resolve_root(root: Path | None = None) -> Path:
    if root is not None:
        return root.expanduser().resolve()
    env_root = os.environ.get("GMAIL_LAB_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return DEFAULT_ROOT


def config_path(root: Path) -> Path:
    return root / "config.yaml"


def load_config(root: Path) -> AppConfig:
    path = config_path(root)
    if not path.exists():
        return AppConfig()
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return AppConfig.model_validate(data)


def save_config(root: Path, config: AppConfig) -> Path:
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config.model_dump(mode="python"), handle, sort_keys=False, allow_unicode=True)
    return path
