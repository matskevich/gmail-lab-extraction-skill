#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import mimetypes
import shutil
import subprocess
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff"}


def sha256sum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sanitize_name(name: str) -> str:
    safe = name.replace("/", "_").replace(":", "_").strip()
    return safe or "asset"


def logical_output_stem(src: Path) -> str:
    name = src.name
    lower_name = name.lower()
    for ext in sorted(IMAGE_EXTS, key=len, reverse=True):
        if lower_name.endswith(ext):
            return sanitize_name(name[: -len(ext)])
    return sanitize_name(src.stem)


def normalize_input(src: Path, normalized_dir: Path) -> Path:
    ext = src.suffix.lower()
    mime_type = detect_mime_type(src)
    if ext in {".heic", ".heif", ".webp"} or mime_type in {"image/heic", "image/heif", "image/webp"}:
        out = normalized_dir / f"{sanitize_name(src.stem)}.png"
        subprocess.run(
            ["/usr/bin/sips", "-s", "format", "png", str(src), "--out", str(out)],
            check=True,
            capture_output=True,
        )
        return out
    return src


def detect_mime_type(path: Path) -> str:
    guessed = mimetypes.guess_type(str(path))[0]
    if guessed:
        return guessed
    try:
        proc = subprocess.run(
            ["file", "-b", "--mime-type", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip() or "application/octet-stream"
    except Exception:
        return "application/octet-stream"


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS or detect_mime_type(path).startswith("image/")


def iter_images(input_path: Path):
    if input_path.is_file():
        if is_image_path(input_path):
            yield input_path
        return
    for p in sorted(input_path.rglob("*")):
        if p.is_file() and is_image_path(p):
            yield p


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OCR over image assets extracted from Gmail.")
    parser.add_argument("input_path", help="Input image file or directory")
    parser.add_argument("output_dir", help="Directory for OCR text outputs")
    parser.add_argument("--language", default="eng", help="Tesseract language, default: eng")
    parser.add_argument("--psm", default="6", help="Tesseract page segmentation mode, default: 6")
    args = parser.parse_args()

    input_path = Path(args.input_path).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    normalized_dir = output_dir / "_normalized"
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)

    manifest = output_dir / "ocr_manifest.tsv"
    lines = ["source_file\tnormalized_file\tocr_txt\tmime_type\tsha256\tstatus\tnotes\n"]
    tesseract_bin = shutil.which("tesseract")
    images = list(iter_images(input_path))

    if not tesseract_bin:
        for src in images:
            mime_type = detect_mime_type(src)
            lines.append(
                f"{src}\t\t\t{mime_type}\t{sha256sum(src)}\tmissing_dependency\ttesseract not found\n"
            )
        manifest.write_text("".join(lines), encoding="utf-8")
        print(manifest)
        return 0

    for src in images:
        try:
            normalized = normalize_input(src, normalized_dir)
            stem = logical_output_stem(src)
            txt_base = output_dir / stem
            subprocess.run(
                [tesseract_bin, str(normalized), str(txt_base), "-l", args.language, "--psm", args.psm],
                check=True,
                capture_output=True,
            )
            txt_path = Path(f"{txt_base}.txt")
            mime_type = detect_mime_type(src)
            lines.append(
                f"{src}\t{normalized}\t{txt_path}\t{mime_type}\t{sha256sum(src)}\tok\t\n"
            )
        except FileNotFoundError as exc:
            mime_type = detect_mime_type(src)
            missing_bin = Path(str(exc.filename or "")).name or "unknown"
            lines.append(
                f"{src}\t\t\t{mime_type}\t{sha256sum(src)}\tmissing_dependency\t{missing_bin} not found\n"
            )
        except subprocess.CalledProcessError as exc:
            mime_type = detect_mime_type(src)
            lines.append(
                f"{src}\t\t\t{mime_type}\t{sha256sum(src)}\tfail\treturncode={exc.returncode}\n"
            )

    manifest.write_text("".join(lines), encoding="utf-8")
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
