from pathlib import Path

import pytest

from astermax.code_aster_diagnostic import (
    CodeAsterDiagnosticError,
    bind_message_output,
    verify_code_aster_message,
)


def test_bind_message_output_is_deterministic(tmp_path: Path):
    export = tmp_path / "astermax.export"
    export.write_text("F comm astermax.comm D 1\nF rmed astermax_result.med R 80\n", encoding="utf-8")
    bind_message_output(export)
    first = export.read_text(encoding="utf-8")
    assert "F mess astermax.mess R 6\n" in first
    bind_message_output(export)
    assert export.read_text(encoding="utf-8") == first


def test_bind_message_output_rejects_existing_unit6(tmp_path: Path):
    export = tmp_path / "astermax.export"
    export.write_text("F libr something.txt R 6\n", encoding="utf-8")
    with pytest.raises(CodeAsterDiagnosticError, match="UNIT6_ALREADY_BOUND"):
        bind_message_output(export)


def test_positive_code_aster_message_is_verified(tmp_path: Path):
    message = tmp_path / "astermax.mess"
    message.write_text(
        "FIN();\nEXECUTION_CODE_ASTER_EXIT_12349=0\n<INFO> Code_Aster run ended, diagnostic : OK\n",
        encoding="utf-8",
    )
    ev = verify_code_aster_message(message)
    assert ev.diagnostic_ok is True
    assert ev.execution_exit_code == 0
    assert len(ev.sha256) == 64


def test_missing_positive_diagnostic_fails_closed(tmp_path: Path):
    message = tmp_path / "astermax.mess"
    message.write_text("FIN();\n", encoding="utf-8")
    with pytest.raises(CodeAsterDiagnosticError, match="OK_DIAGNOSTIC_MISSING"):
        verify_code_aster_message(message)


def test_nonzero_embedded_exit_fails_closed(tmp_path: Path):
    message = tmp_path / "astermax.mess"
    message.write_text(
        "EXECUTION_CODE_ASTER_EXIT_100=2\n<INFO> Code_Aster run ended, diagnostic : OK\n",
        encoding="utf-8",
    )
    with pytest.raises(CodeAsterDiagnosticError, match="NONZERO_EXIT:2"):
        verify_code_aster_message(message)


def test_fatal_marker_overrides_ok_string(tmp_path: Path):
    message = tmp_path / "astermax.mess"
    message.write_text(
        "<F> solver failure\n<INFO> Code_Aster run ended, diagnostic : OK\n",
        encoding="utf-8",
    )
    with pytest.raises(CodeAsterDiagnosticError, match="FATAL_DIAGNOSTIC"):
        verify_code_aster_message(message)
