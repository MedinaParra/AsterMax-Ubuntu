"""Windows-oriented one-click runner for the verified AsterMax technical demo.

The runner separates four responsibilities:
1) generate the deterministic evidence bundle,
2) verify every SHA-256 entry in the manifest before presentation,
3) open the self-contained AsterMax HTML viewer by default,
4) optionally fall back to ParaView for independent VTK inspection.

CI never requires a GUI. Presentation is optional; solver evidence remains valid and
independently verifiable without any viewer.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Mapping
import webbrowser

from .demo_bundle import generate_demo_bundle


class WindowsDemoRunnerError(RuntimeError):
    """Raised when demo generation, evidence verification, or viewer launch fails."""


@dataclass(frozen=True)
class DemoRunResult:
    output_dir: Path
    vtk_path: Path
    manifest_path: Path
    evidence_fingerprint_sha256: str
    evidence_verified: bool
    viewer_executable: str | None
    viewer_launched: bool
    astermax_viewer_path: Path | None = None
    astermax_viewer_launched: bool = False


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_evidence_bundle(output_dir: str | Path) -> dict:
    """Fail closed unless manifest hashes exactly match generated artifacts."""
    root = Path(output_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise WindowsDemoRunnerError("manifest.json is missing from demo evidence")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WindowsDemoRunnerError("manifest.json is unreadable or invalid") from exc
    artifacts = manifest.get("artifacts")
    fingerprint = manifest.get("evidence_fingerprint_sha256")
    if not isinstance(artifacts, Mapping) or not artifacts or not isinstance(fingerprint, str):
        raise WindowsDemoRunnerError("manifest does not contain auditable artifact metadata")

    canonical_artifacts = {}
    for name in sorted(artifacts):
        metadata = artifacts[name]
        if not isinstance(name, str) or Path(name).name != name:
            raise WindowsDemoRunnerError("manifest artifact names must be local filenames")
        if not isinstance(metadata, Mapping):
            raise WindowsDemoRunnerError("manifest artifact metadata is invalid")
        expected_hash = metadata.get("sha256")
        expected_bytes = metadata.get("bytes")
        if not isinstance(expected_hash, str) or not isinstance(expected_bytes, int):
            raise WindowsDemoRunnerError("manifest hash/size metadata is invalid")
        path = root / name
        if not path.is_file():
            raise WindowsDemoRunnerError(f"evidence artifact is missing: {name}")
        actual_hash = _sha256_file(path)
        actual_bytes = path.stat().st_size
        if actual_hash != expected_hash or actual_bytes != expected_bytes:
            raise WindowsDemoRunnerError(f"evidence artifact failed SHA-256/size verification: {name}")
        canonical_artifacts[name] = {"sha256": expected_hash, "bytes": expected_bytes}

    canonical = json.dumps(
        canonical_artifacts, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    actual_fingerprint = sha256(canonical).hexdigest()
    if actual_fingerprint != fingerprint:
        raise WindowsDemoRunnerError("evidence fingerprint does not match manifest artifacts")
    return manifest


def find_paraview(explicit: str | None = None) -> str | None:
    """Locate ParaView without making it a mandatory runtime dependency."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    env = os.environ.get("PARAVIEW_EXE")
    if env:
        candidates.append(env)
    path_hit = shutil.which("paraview") or shutil.which("paraview.exe")
    if path_hit:
        candidates.append(path_hit)
    candidates.extend((
        r"C:\Program Files\ParaView 5.13.3\bin\paraview.exe",
        r"C:\Program Files\ParaView 5.13.2\bin\paraview.exe",
        r"C:\Program Files\ParaView 5.12.1\bin\paraview.exe",
    ))
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return str(path)
    return None


def launch_paraview(viewer_executable: str, vtk_path: str | Path) -> None:
    viewer = Path(viewer_executable)
    vtk = Path(vtk_path)
    if not viewer.is_file():
        raise WindowsDemoRunnerError("viewer executable does not exist")
    if not vtk.is_file():
        raise WindowsDemoRunnerError("VTK evidence file does not exist")
    try:
        subprocess.Popen([str(viewer), str(vtk)], close_fds=(os.name != "nt"))
    except OSError as exc:
        raise WindowsDemoRunnerError("failed to launch ParaView") from exc


def launch_astermax_viewer(viewer_path: str | Path) -> bool:
    """Open the fingerprinted self-contained viewer using the OS default browser."""
    path = Path(viewer_path).resolve()
    if not path.is_file():
        raise WindowsDemoRunnerError("AsterMax viewer artifact does not exist")
    try:
        return bool(webbrowser.open(path.as_uri(), new=1))
    except (OSError, webbrowser.Error) as exc:
        raise WindowsDemoRunnerError("failed to open the AsterMax self-contained viewer") from exc


def run_verified_demo(
    output_dir: str | Path = "astermax_demo_evidence",
    *,
    open_viewer: bool = True,
    paraview_executable: str | None = None,
    prefer_paraview: bool = False,
) -> DemoRunResult:
    """Generate, verify, then optionally present the professional demo bundle."""
    root = Path(output_dir)
    generate_demo_bundle(root)
    manifest = verify_evidence_bundle(root)
    vtk = root / "verified_multigap_joint.vtk"
    html = root / str(manifest.get("viewer", "astermax_viewer.html"))
    if not html.is_file():
        raise WindowsDemoRunnerError("verified manifest does not resolve an AsterMax viewer")

    paraview = find_paraview(paraview_executable) if (open_viewer and prefer_paraview) else None
    paraview_launched = False
    astermax_launched = False
    if open_viewer:
        if prefer_paraview and paraview is not None:
            launch_paraview(paraview, vtk)
            paraview_launched = True
        else:
            astermax_launched = launch_astermax_viewer(html)

    return DemoRunResult(
        output_dir=root.resolve(),
        vtk_path=vtk.resolve(),
        manifest_path=(root / "manifest.json").resolve(),
        evidence_fingerprint_sha256=str(manifest["evidence_fingerprint_sha256"]),
        evidence_verified=True,
        viewer_executable=paraview,
        viewer_launched=paraview_launched or astermax_launched,
        astermax_viewer_path=html.resolve(),
        astermax_viewer_launched=astermax_launched,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the verified AsterMax Windows technical demo")
    parser.add_argument("--output", default="astermax_demo_evidence")
    parser.add_argument("--no-viewer", action="store_true", help="generate/verify evidence without opening a viewer")
    parser.add_argument("--paraview", default=None, help="explicit path to paraview.exe")
    parser.add_argument("--prefer-paraview", action="store_true", help="use ParaView instead of the integrated viewer when available")
    args = parser.parse_args(argv)
    result = run_verified_demo(
        args.output,
        open_viewer=not args.no_viewer,
        paraview_executable=args.paraview,
        prefer_paraview=args.prefer_paraview,
    )
    print("AsterMax Windows Technical Demo")
    print(f"evidence: {result.output_dir}")
    print(f"verified: {result.evidence_verified}")
    print(f"fingerprint: {result.evidence_fingerprint_sha256}")
    print(f"AsterMax viewer: {result.astermax_viewer_path}")
    if result.astermax_viewer_launched:
        print("presentation: integrated AsterMax viewer launched")
    elif result.viewer_executable and result.viewer_launched:
        print(f"presentation: ParaView launched ({result.viewer_executable})")
    else:
        print("presentation: not launched; evidence remains valid and can be opened manually")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
