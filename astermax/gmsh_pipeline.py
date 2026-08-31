"""Executable STEP -> Gmsh -> AsterMax bridge for verification cases.

The PMV numerical kernel is intentionally locked to mm-N-MPa. This module refuses
STEP geometry unless :func:`require_step_mm` can prove the Part 21 file declares
millimetres, then asks an installed Gmsh CLI to import the STEP with OpenCASCADE,
create named physical surface groups from explicit engineering bounding boxes, and
emit a deterministic Gmsh v2 ASCII TET4 mesh consumed by :mod:`astermax.gmsh_ascii`.

It is a verification bridge, not a production CAD repair/healing layer. Surface
selection remains explicit and auditable; failed/empty selections are rejected by
Gmsh rather than silently remapped. Imported TET4 meshes pass a dimensionless shape
quality gate before they can enter the verified solve chain.
"""

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile

from .gmsh_ascii import TetraMesh, read_gmsh_v2_ascii
from .mesh_quality import MeshQualityError, require_tet4_mesh_quality
from .step_units import require_step_mm


class GmshPipelineError(RuntimeError):
    """Raised when the external CAD/meshing stage cannot be verified."""


@dataclass(frozen=True)
class SurfaceBox:
    """Explicit axis-aligned surface selector in model millimetres."""

    name: str
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]

    def __post_init__(self) -> None:
        if not self.name or '"' in self.name or "\n" in self.name:
            raise ValueError("surface group name must be a non-empty simple string")
        if len(self.minimum) != 3 or len(self.maximum) != 3:
            raise ValueError("surface bounds must be three-dimensional")
        if any(lo > hi for lo, hi in zip(self.minimum, self.maximum)):
            raise ValueError("surface bounding-box minimum cannot exceed maximum")


def _gmsh_path(executable: str) -> str:
    resolved = shutil.which(executable)
    if resolved is None:
        raise GmshPipelineError(f"Gmsh executable not found: {executable}")
    return resolved


def _geo_quote(path: Path) -> str:
    # Gmsh accepts forward slashes on Windows too. Escaping quotes prevents a path
    # from changing the generated .geo program.
    return str(path.resolve()).replace("\\", "/").replace('"', '\\"')


def build_step_meshing_geo(
    step_path: str | Path,
    *,
    surface_boxes: tuple[SurfaceBox, ...] | list[SurfaceBox],
    mesh_size_mm: float,
) -> str:
    """Create the auditable Gmsh program used to mesh one STEP solid."""
    source = Path(step_path)
    if mesh_size_mm <= 0.0:
        raise ValueError("mesh_size_mm must be positive")
    if not surface_boxes:
        raise ValueError("at least one named surface selector is required")
    names = [selector.name for selector in surface_boxes]
    if len(set(names)) != len(names):
        raise ValueError("surface group names must be unique")

    lines = [
        'SetFactory("OpenCASCADE");',
        f'Merge "{_geo_quote(source)}";',
        "Mesh.MshFileVersion = 2.2;",
        "Mesh.Binary = 0;",
        f"Mesh.CharacteristicLengthMin = {float(mesh_size_mm):.17g};",
        f"Mesh.CharacteristicLengthMax = {float(mesh_size_mm):.17g};",
        "volumes[] = Volume{:};",
        'If (#volumes[] == 0) Error("STEP import produced no volumes"); EndIf',
        'Physical Volume("SOLID") = {volumes[]};',
    ]
    for index, selector in enumerate(surface_boxes):
        values = (*selector.minimum, *selector.maximum)
        bounds = ", ".join(f"{float(value):.17g}" for value in values)
        lines.extend(
            [
                f"surface_{index}[] = Surface In BoundingBox{{{bounds}}};",
                f'If (#surface_{index}[] == 0) Error("surface selector {selector.name} matched no faces"); EndIf',
                f'Physical Surface("{selector.name}") = {{surface_{index}[]}};',
            ]
        )
    return "\n".join(lines) + "\n"


def mesh_step_with_gmsh(
    step_path: str | Path,
    msh_path: str | Path,
    *,
    surface_boxes: tuple[SurfaceBox, ...] | list[SurfaceBox],
    mesh_size_mm: float,
    gmsh_executable: str = "gmsh",
    minimum_tet_quality: float = 0.05,
) -> TetraMesh:
    """Validate mm STEP, tetrahedralize it and reject poor TET4 shape quality."""
    source = Path(step_path)
    destination = Path(msh_path)
    if not source.is_file():
        raise GmshPipelineError(f"STEP file does not exist: {source}")

    try:
        step_text = source.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise GmshPipelineError("STEP Part 21 input must be readable ASCII/UTF-8 text") from exc
    # Hard physics gate: no hidden metre/inch conversion is allowed.
    require_step_mm(step_text)

    geo_text = build_step_meshing_geo(
        source, surface_boxes=surface_boxes, mesh_size_mm=mesh_size_mm
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    executable = _gmsh_path(gmsh_executable)

    with tempfile.TemporaryDirectory(prefix="astermax-gmsh-") as temporary:
        geo_path = Path(temporary) / "mesh_step.geo"
        geo_path.write_text(geo_text, encoding="utf-8")
        command = [
            executable,
            str(geo_path),
            "-3",
            "-format",
            "msh2",
            "-o",
            str(destination.resolve()),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise GmshPipelineError(f"Gmsh STEP meshing failed: {detail}")
    if not destination.is_file() or destination.stat().st_size == 0:
        raise GmshPipelineError("Gmsh reported success but produced no mesh artifact")

    mesh = read_gmsh_v2_ascii(destination, declared_unit="mm")
    try:
        require_tet4_mesh_quality(
            mesh.nodes,
            mesh.elements,
            minimum_quality=minimum_tet_quality,
        )
    except MeshQualityError as exc:
        raise GmshPipelineError(f"Gmsh mesh rejected before solve: {exc}") from exc
    return mesh
