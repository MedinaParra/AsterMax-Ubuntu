from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
import subprocess
from pathlib import Path

from .code_aster_wsl_runtime import CodeAsterWslRuntime, CodeAsterWslError, probe_wsl_runtime


class CodeAsterRuntimeQualificationError(RuntimeError):
    pass


_LINUX_PATH_RE = re.compile(r"^/[A-Za-z0-9_./+\-]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSION_PATTERNS = (
    re.compile(r"(?i)code[_ -]?aster[^0-9]{0,20}(\d+(?:\.\d+){1,3})"),
    re.compile(r"(?i)version[^0-9]{0,10}(\d+(?:\.\d+){1,3})"),
)


@dataclass(frozen=True)
class QualifiedCodeAsterRuntime:
    engine_kind: str
    distribution: str
    run_aster_linux: str
    run_aster_sha256: str
    config_linux: str
    config_sha256: str
    kernel_release: str
    machine: str
    version_text_sha256: str
    detected_version: str | None
    identity_probe_sha256: str
    runtime_qualified: bool = True
    fea_solve_executed: bool = False
    results_verified: bool = False

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def _run(command: list[str], *, timeout_s: float = 30.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodeAsterRuntimeQualificationError("CODE_ASTER_RUNTIME_QUALIFICATION_EXECUTION_FAILED") from exc


def _wsl(runtime: CodeAsterWslRuntime, *args: str, timeout_s: float = 30.0) -> subprocess.CompletedProcess[str]:
    runtime.validate()
    return _run(["wsl.exe", "--distribution", runtime.distribution, "--", *args], timeout_s=timeout_s)


def _require_linux_path(value: str, *, label: str) -> str:
    if not _LINUX_PATH_RE.fullmatch(value):
        raise CodeAsterRuntimeQualificationError(f"CODE_ASTER_RUNTIME_{label}_PATH_INVALID")
    return value


def _sha256_linux_file(runtime: CodeAsterWslRuntime, path: str) -> str:
    completed = _wsl(runtime, "sha256sum", "--", path)
    if completed.returncode != 0:
        raise CodeAsterRuntimeQualificationError("CODE_ASTER_RUNTIME_HASH_FAILED")
    token = (completed.stdout or "").strip().split(maxsplit=1)[0].lower()
    if not _SHA256_RE.fullmatch(token):
        raise CodeAsterRuntimeQualificationError("CODE_ASTER_RUNTIME_HASH_INVALID")
    return token


def _require_regular_file(runtime: CodeAsterWslRuntime, path: str, *, label: str) -> None:
    completed = _wsl(runtime, "test", "-f", path)
    if completed.returncode != 0:
        raise CodeAsterRuntimeQualificationError(f"CODE_ASTER_RUNTIME_{label}_NOT_FOUND")


def _detect_version(text: str) -> str | None:
    for pattern in _VERSION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def qualify_wsl_code_aster_runtime(
    runtime: CodeAsterWslRuntime,
    *,
    config_linux: str,
    timeout_s: float = 30.0,
) -> QualifiedCodeAsterRuntime:
    """Create immutable evidence for the exact WSL2 Code_Aster runtime.

    Qualification is intentionally separate from FEA execution. It proves that a
    concrete launcher/configuration pair exists in the requested distribution,
    fingerprints both files, records the Linux kernel/machine, and fingerprints
    solver identity/version output. It never sets ``fea_solve_executed``.
    """
    runtime.validate()
    config = _require_linux_path(config_linux, label="CONFIG")
    launcher = _require_linux_path(runtime.run_aster_linux, label="LAUNCHER")

    try:
        probe = probe_wsl_runtime(runtime, timeout_s=timeout_s)
    except CodeAsterWslError as exc:
        raise CodeAsterRuntimeQualificationError("CODE_ASTER_RUNTIME_IDENTITY_PROBE_FAILED") from exc

    _require_regular_file(runtime, launcher, label="LAUNCHER")
    _require_regular_file(runtime, config, label="CONFIG")
    launcher_sha = _sha256_linux_file(runtime, launcher)
    config_sha = _sha256_linux_file(runtime, config)

    uname = _wsl(runtime, "uname", "-srmo", timeout_s=timeout_s)
    if uname.returncode != 0 or not (uname.stdout or "").strip():
        raise CodeAsterRuntimeQualificationError("CODE_ASTER_RUNTIME_UNAME_FAILED")
    uname_text = (uname.stdout or "").strip()
    parts = uname_text.split()
    kernel_release = parts[1] if len(parts) >= 2 else uname_text

    machine_call = _wsl(runtime, "uname", "-m", timeout_s=timeout_s)
    if machine_call.returncode != 0 or not (machine_call.stdout or "").strip():
        raise CodeAsterRuntimeQualificationError("CODE_ASTER_RUNTIME_MACHINE_FAILED")
    machine = (machine_call.stdout or "").strip()

    version_call = _wsl(runtime, launcher, "--version", timeout_s=timeout_s)
    version_text = ((version_call.stdout or "") + "\n" + (version_call.stderr or "")).strip()
    if version_call.returncode != 0 or not version_text:
        # Some run_aster releases do not expose --version. The already verified
        # --help identity remains valid evidence; record that text instead.
        help_call = _wsl(runtime, launcher, "--help", timeout_s=timeout_s)
        version_text = ((help_call.stdout or "") + "\n" + (help_call.stderr or "")).strip()
        if help_call.returncode != 0 or not version_text:
            raise CodeAsterRuntimeQualificationError("CODE_ASTER_RUNTIME_VERSION_EVIDENCE_FAILED")

    version_hash = sha256(version_text.encode("utf-8", errors="replace")).hexdigest()
    detected_version = _detect_version(version_text)
    identity_hash = str(probe.get("probe_sha256", ""))
    if not _SHA256_RE.fullmatch(identity_hash):
        raise CodeAsterRuntimeQualificationError("CODE_ASTER_RUNTIME_IDENTITY_HASH_INVALID")

    return QualifiedCodeAsterRuntime(
        engine_kind=runtime.engine_kind,
        distribution=runtime.distribution,
        run_aster_linux=launcher,
        run_aster_sha256=launcher_sha,
        config_linux=config,
        config_sha256=config_sha,
        kernel_release=kernel_release,
        machine=machine,
        version_text_sha256=version_hash,
        detected_version=detected_version,
        identity_probe_sha256=identity_hash,
    )


def write_runtime_qualification(evidence: QualifiedCodeAsterRuntime, destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path
