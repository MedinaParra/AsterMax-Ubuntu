from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re


class CodeAsterDiagnosticError(RuntimeError):
    pass


_OK_RE = re.compile(r"Code_Aster\s+run\s+ended\s*,?\s*diagnostic\s*:\s*OK", re.IGNORECASE)
_EXIT_RE = re.compile(r"EXECUTION_CODE_ASTER_EXIT_[0-9]+\s*=\s*(-?[0-9]+)")
_FATAL_MARKERS = (
    "<F>",
    "_ERROR Code_Aster run ended",
    "FATAL ERROR",
    "Traceback (most recent call last)",
)


@dataclass(frozen=True)
class CodeAsterDiagnosticEvidence:
    path: Path
    sha256: str
    size_bytes: int
    diagnostic_ok: bool
    execution_exit_code: int | None
    fatal_marker_detected: bool


def verify_code_aster_message(path: str | Path) -> CodeAsterDiagnosticEvidence:
    """Fail closed unless the solver message contains a positive Code_Aster diagnostic.

    A process exit status alone is not sufficient provenance for AsterMax. The
    message file must be fresh/non-empty and explicitly contain Code_Aster's
    successful diagnostic. If an EXECUTION_CODE_ASTER_EXIT_* token is present it
    must be zero. Known fatal markers always invalidate the evidence.
    """
    message = Path(path).expanduser().resolve()
    if not message.is_file() or message.stat().st_size <= 0:
        raise CodeAsterDiagnosticError("CODE_ASTER_MESSAGE_MISSING")
    try:
        text = message.read_text(encoding="utf-8", errors="strict")
    except UnicodeError as exc:
        raise CodeAsterDiagnosticError("CODE_ASTER_MESSAGE_ENCODING_INVALID") from exc

    fatal = any(marker.lower() in text.lower() for marker in _FATAL_MARKERS)
    exits = [int(value) for value in _EXIT_RE.findall(text)]
    if len(set(exits)) > 1:
        raise CodeAsterDiagnosticError("CODE_ASTER_MESSAGE_EXIT_CODE_AMBIGUOUS")
    exit_code = exits[0] if exits else None
    ok = bool(_OK_RE.search(text))

    if fatal:
        raise CodeAsterDiagnosticError("CODE_ASTER_MESSAGE_FATAL_DIAGNOSTIC")
    if exit_code is not None and exit_code != 0:
        raise CodeAsterDiagnosticError(f"CODE_ASTER_MESSAGE_NONZERO_EXIT:{exit_code}")
    if not ok:
        raise CodeAsterDiagnosticError("CODE_ASTER_MESSAGE_OK_DIAGNOSTIC_MISSING")

    return CodeAsterDiagnosticEvidence(
        path=message,
        sha256=sha256(message.read_bytes()).hexdigest(),
        size_bytes=message.stat().st_size,
        diagnostic_ok=True,
        execution_exit_code=exit_code,
        fatal_marker_detected=False,
    )
