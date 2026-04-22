from __future__ import annotations

from gmail_lab.core.claims.ownership import resolve_owner
from gmail_lab.core.claims.sample_date import derive_sample_draw_claim
from gmail_lab.core.config import IdentityConfig


def test_resolve_owner_confirmed_owner() -> None:
    identity = IdentityConfig(
        canonical_name="Иванов Иван Иванович",
        aliases=["Ivan Ivanov", "John Example"],
    )
    owner_name, owner_status, owner_source = resolve_owner(
        identity=identity,
        text_sources=[
            ("artifact_text", "Пациент: Иванов Иван Иванович"),
        ],
    )
    assert owner_name == "Иванов Иван Иванович"
    assert owner_status == "confirmed_owner"
    assert owner_source == "artifact_text:patient_label"


def test_derive_sample_draw_claim_direct_datetime() -> None:
    claim = derive_sample_draw_claim(
        artifact_text="Взятие биоматериала: 27.08.2021 10:42",
        analysis_date="2021-09-02",
    )
    assert claim.sample_draw_date == "2021-08-27"
    assert claim.sample_draw_time == "10:42:00"
    assert claim.sample_draw_datetime == "2021-08-27T10:42:00"
    assert claim.sample_draw_status == "direct"
