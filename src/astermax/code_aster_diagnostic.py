from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re


class CodeAsterDiagnosticError(RuntimeError):
    pass


_OK_RE = re.compile(r"Code_Aster\s+run\s+ended\s*,?\s*diagnostic\s*:\s*OK", re.IGNORECASE)
_EXIT_RE = re.compile(r"EXECUTION_CODE_ASTER_EXIT_[0-9]+\s*=\s*(-?[0-9]+)")
_LOCAL_MESS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.mess$", re.IGNORECASE)
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


def bind_message_output(export_path: str | Path, *, message_filename: str = "astermax.mess") -> Path:
    """Add a durable Code_Aster message output binding to a prepared .export.

    The operation is deterministic and fail-closed: unit 6 may not already be
    bound to another output, and duplicate/ambiguous message declarations are
    rejected. This is preparation only; it never claims solver execution.
    """
    export = Path(export_path).expanduser().resolve()
    if not export.is_file() or export.stat().st_size <= 0:
        raise CodeAsterDiagnosticError("CODE_ASTER_EXPORT_MISSING")
    if Path(message_filename).name != message_filename or not _LOCAL_MESS_RE.fullmatch(message_filename):
        raise CodeAsterDiagnosticError("CODE_ASTER_MESSAGE_FILENAME_INVALID")

    text = export.read_text(encoding="utf-8", errors="strict")
    lines = [line.rstrip() for line in text.splitlines()]
    desired = f"F mess {message_filename} R 6"
    message_lines = [line.strip() for line in lines if line.strip().startswith("F mess ")]
    unit6_lines = [line.strip() for line in lines if re.search(r"\s[DRC]\s+6\s*$", line.strip())]

    if desired in message_lines:
        if len(message_lines) != 1 or any(line != desired for line in unit6_lines):
            raise CodeAsterDiagnosticError("CODE_ASTER_MESSAGE_BINDING_AMBIGUOUS")
        return export
    if message_lines or unit6_lines:
        raise CodeAsterDiagnosticError("CODE_ASTER_MESSAGE_UNIT6_ALREADY_BOUND")

    rendered = "\n".join(lines).rstrip("\n") + "\n" + desired + "\n"
    export.write_text(rendered, encoding="utf-8", newline="\n")
    return export


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
