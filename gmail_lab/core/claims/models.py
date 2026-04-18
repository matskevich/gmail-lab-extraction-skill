from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NameSignal:
    name: str
    source: str
    evidence: str


@dataclass(frozen=True)
class SampleDrawClaim:
    sample_draw_date: str
    sample_draw_time: str
    sample_draw_datetime: str
    sample_draw_status: str
    sample_draw_source: str
    sample_draw_evidence: str
