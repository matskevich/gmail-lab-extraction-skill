from __future__ import annotations

from scripts.rerun_enrichment import derivative_dir, derivative_layout


def test_derivative_layout_for_slugged_raw_dir(tmp_path) -> None:
    raw_dir = tmp_path / "run" / "raw" / "1-prodia"
    raw_dir.mkdir(parents=True)

    run_dir, slug = derivative_layout(raw_dir)

    assert run_dir == tmp_path / "run"
    assert slug == "1-prodia"
    assert derivative_dir(run_dir, "pdf_text", slug) == tmp_path / "run" / "pdf_text" / "1-prodia"


def test_derivative_layout_for_direct_raw_dir(tmp_path) -> None:
    run_dir = tmp_path / "run"
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True)
    (run_dir / "run_manifest.tsv").write_text("", encoding="utf-8")

    resolved_run_dir, slug = derivative_layout(raw_dir)

    assert resolved_run_dir == run_dir
    assert slug is None
    assert derivative_dir(resolved_run_dir, "pdf_text", slug) == run_dir / "pdf_text"
