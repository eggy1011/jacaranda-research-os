from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_MACOS_SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
_TIMEOUT_SECONDS = 300


class PdfExportError(RuntimeError):
    """PDF conversion failed; the message is safe to store and display."""


def find_soffice() -> str | None:
    """Resolve LibreOffice: SOFFICE_PATH env -> PATH -> macOS default -> None."""
    candidates = [
        os.environ.get("SOFFICE_PATH"),
        shutil.which("libreoffice"),
        shutil.which("soffice"),
        _MACOS_SOFFICE,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def convert_pptx_to_pdf(
    pptx_path: Path, output_dir: Path, *, soffice: str | None = None
) -> Path:
    """Convert an editable PPTX into the formal PDF edition via headless
    LibreOffice. Raises PdfExportError when LibreOffice is unavailable or the
    conversion fails — callers decide whether that is fatal for their flow."""
    binary = soffice or find_soffice()
    if binary is None:
        raise PdfExportError(
            "LibreOffice is not installed (set SOFFICE_PATH or install libreoffice)"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            binary,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(pptx_path),
        ],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
    )
    produced = output_dir / (pptx_path.stem + ".pdf")
    if result.returncode != 0 or not produced.is_file():
        raise PdfExportError(f"soffice conversion failed with code {result.returncode}")
    return produced
