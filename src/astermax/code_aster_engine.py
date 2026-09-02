from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from typing import Iterable


ENGINE_KIND = "CODE_ASTER_NATIVE_WINDOWS"
DEFAULT_ENV_VAR = "ASTERMAX_CODE_ASTER_HOME"
CONFIG_RELATIVE_PATH = Path("share") / "aster" / "config.yaml"


class CodeAsterEngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodeAsterRuntime:
    root: Path
    run_aster: Path
    config: Path
    launcher_sha256: str
    engine_kind: str = ENGINE_KIND

    def as_evidence(self) -> dict[str, str]:
        return {
            "engine_kind": self.engine_kind,
            "root": str(self.root),
            "run_aster": str(self.run_aster),
            "config": str(self.config),
            "launcher_sha256": self.launcher_sha256,
        }


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _launcher_candidates(root: Path) -> tuple[Path, ...]:
    bin_dir = root / "bin"
    return (
        bin_dir / "run_aster.exe",
        bin_dir / "run_aster.bat",
        bin_dir / "run_aster.cmd",
        bin_dir / "run_aster",
        root / "run_aster.exe",
        root / "run_aster.bat",
        root / "run_aster.cmd",
        root / "run_aster",
    )


def validate_runtime_root(root: str | os.PathLike[str]) -> CodeAsterRuntime:
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise CodeAsterEngineError("CODE_ASTER_RUNTIME_ROOT_NOT_FOUND")

    launcher = next((candidate for candidate in _launcher_candidates(root_path) if candidate.is_file()), None)
    if launcher is None:
        raise CodeAsterEngineError("CODE_ASTER_RUN_ASTER_NOT_FOUND")

    config = root_path / CONFIG_RELATIVE_PATH
    if not config.is_file():
        raise CodeAsterEngineError("CODE_ASTER_CONFIG_NOT_FOUND")

    return CodeAsterRuntime(
        root=root_path,
        run_aster=launcher,
        config=config,
        launcher_sha256=_sha256_file(launcher),
    )


def default_runtime_roots(
    *,
    program_files: str | None = None,
    local_app_data: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[Path, ...]:
    source = os.environ if env is None else env
    roots: list[Path] = []
    explicit = source.get(DEFAULT_ENV_VAR)
    if explicit:
        roots.append(Path(explicit))

    pf = program_files if program_files is not None else source.get("ProgramFiles")
    if pf:
        roots.extend(
            (
                Path(pf) / "AsterMax" / "engine" / "code_aster",
                Path(pf) / "AsterMax" / "CodeAster",
            )
        )

    lad = local_app_data if local_app_data is not None else source.get("LOCALAPPDATA")
    if lad:
        roots.append(Path(lad) / "AsterMax" / "engine" / "code_aster")

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = os.path.normcase(str(root))
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return tuple(unique)


def discover_runtime(candidates: Iterable[str | os.PathLike[str]] | None = None) -> CodeAsterRuntime:
    roots = tuple(Path(path) for path in candidates) if candidates is not None else default_runtime_roots()
    failures: list[str] = []
    for root in roots:
        try:
            return validate_runtime_root(root)
        except CodeAsterEngineError as exc:
            failures.append(f"{root}: {exc}")
    detail = "; ".join(failures) if failures else "no candidate roots configured"
    raise CodeAsterEngineError(f"CODE_ASTER_RUNTIME_NOT_FOUND: {detail}")


def _windows_launcher_command(runtime: CodeAsterRuntime, args: Iterable[str]) -> list[str]:
    suffix = runtime.run_aster.suffix.lower()
    if suffix in {".bat", ".cmd"}:
        return ["cmd.exe", "/d", "/s", "/c", str(runtime.run_aster), *args]
    return [str(runtime.run_aster), *args]


def probe_runtime(runtime: CodeAsterRuntime, *, timeout_s: float = 20.0) -> dict[str, object]:
    """Probe the real launcher only; this does not claim a successful FEA solve."""
    command = _windows_launcher_command(runtime, ["--help"])
    try:
        completed = subprocess.run(
            command,
            cwd=runtime.root,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodeAsterEngineError("CODE_ASTER_PROBE_EXECUTION_FAILED") from exc

    combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0:
        raise CodeAsterEngineError(f"CODE_ASTER_PROBE_NONZERO_EXIT:{completed.returncode}")
    if "run_aster" not in combined.lower() and "code_aster" not in combined.lower():
        raise CodeAsterEngineError("CODE_ASTER_PROBE_IDENTITY_UNCONFIRMED")

    evidence = runtime.as_evidence()
    evidence.update(
        {
            "probe": "run_aster --help",
            "returncode": completed.returncode,
            "identity_confirmed": True,
            "fea_solve_executed": False,
        }
    )
    return evidence


def write_runtime_evidence(runtime: CodeAsterRuntime, destination: str | os.PathLike[str]) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = runtime.as_evidence()
    payload["fea_solve_executed"] = False
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
