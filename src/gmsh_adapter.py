from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class GmshAdapterError(RuntimeError):
    """Raised when STEP import or meshing leaves the certified PMV boundary."""


@dataclass(frozen=True)
class MeshManifest:
    schema: str
    source_step_sha256: str
    length_unit: str
    gmsh_version: str
    bbox_mm: tuple[float, float, float, float, float, float]
    dimensions_mm: tuple[float, float, float]
    volume_count: int
    surface_count: int
    node_count: int
    tet4_count: int
    surface_groups: dict[str, tuple[int, ...]]

    def canonical_bytes(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode("utf-8")

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _import_gmsh():
    try:
        import gmsh  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised by deployment, not unit CI after install
        raise GmshAdapterError("gmsh Python package is required for STEP meshing") from exc
    return gmsh


def _axis_surface_groups(gmsh: Any, surfaces: list[tuple[int, int]], bbox: tuple[float, ...]) -> dict[str, tuple[int, ...]]:
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    span = max(xmax - xmin, ymax - ymin, zmax - zmin, 1.0)
    tol = span * 1.0e-7
    groups: dict[str, list[int]] = {name: [] for name in ("X_MIN", "X_MAX", "Y_MIN", "Y_MAX", "Z_MIN", "Z_MAX")}

    for dim, tag in surfaces:
        sxmin, symin, szmin, sxmax, symax, szmax = gmsh.model.getBoundingBox(dim, tag)
        if abs(sxmin - xmin) <= tol and abs(sxmax - xmin) <= tol:
            groups["X_MIN"].append(tag)
        if abs(sxmin - xmax) <= tol and abs(sxmax - xmax) <= tol:
            groups["X_MAX"].append(tag)
        if abs(symin - ymin) <= tol and abs(symax - ymin) <= tol:
            groups["Y_MIN"].append(tag)
        if abs(symin - ymax) <= tol and abs(symax - ymax) <= tol:
            groups["Y_MAX"].append(tag)
        if abs(szmin - zmin) <= tol and abs(szmax - zmin) <= tol:
            groups["Z_MIN"].append(tag)
        if abs(szmin - zmax) <= tol and abs(szmax - zmax) <= tol:
            groups["Z_MAX"].append(tag)

    return {name: tuple(sorted(tags)) for name, tags in groups.items()}


def mesh_step_to_tet4(
    step_path: str | Path,
    mesh_size_mm: float,
    *,
    output_msh: str | Path | None = None,
) -> MeshManifest:
    """Import one STEP solid in millimetres and generate a first-order TET4 mesh.

    The adapter intentionally fails closed: multiple solids, missing axis faces,
    non-positive mesh size, non-TET4 3-D elements, or empty meshes are rejected.
    """
    step_path = Path(step_path)
    if step_path.suffix.lower() not in {".step", ".stp"}:
        raise GmshAdapterError("Certified CAD input must be STEP/STP")
    if not step_path.is_file():
        raise GmshAdapterError(f"STEP file does not exist: {step_path}")
    if mesh_size_mm <= 0.0:
        raise GmshAdapterError("mesh_size_mm must be positive")

    gmsh = _import_gmsh()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_step_pm_v")
        imported = gmsh.model.occ.importShapes(str(step_path))
        gmsh.model.occ.synchronize()

        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise GmshAdapterError(f"PMV supports exactly one STEP solid; found {len(volumes)}")
        if not any(dim == 3 for dim, _ in imported):
            raise GmshAdapterError("STEP import did not report a 3-D OCC entity")

        bbox_raw = gmsh.model.getBoundingBox(3, volumes[0][1])
        bbox = tuple(float(v) for v in bbox_raw)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox
        dimensions = (xmax - xmin, ymax - ymin, zmax - zmin)
        if not all(d > 0.0 for d in dimensions):
            raise GmshAdapterError(f"Invalid STEP bounding dimensions: {dimensions}")

        surfaces = gmsh.model.getEntities(2)
        surface_groups = _axis_surface_groups(gmsh, surfaces, bbox)
        missing_groups = [name for name, tags in surface_groups.items() if not tags]
        if missing_groups:
            raise GmshAdapterError(
                "Axis-face scoping is incomplete for this PMV geometry; missing " + ", ".join(missing_groups)
            )

        gmsh.option.setNumber("Mesh.MeshSizeMin", float(mesh_size_mm))
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(mesh_size_mm))
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.model.mesh.generate(3)

        node_tags, _, _ = gmsh.model.mesh.getNodes()
        element_types, element_tags, _ = gmsh.model.mesh.getElements(3)
        if len(node_tags) == 0:
            raise GmshAdapterError("Gmsh generated zero nodes")
        if not element_types:
            raise GmshAdapterError("Gmsh generated zero 3-D elements")

        tet4_count = 0
        unsupported: list[int] = []
        for element_type, tags in zip(element_types, element_tags):
            element_type = int(element_type)
            if element_type == 4:  # Gmsh 4-node tetrahedron
                tet4_count += len(tags)
            elif len(tags):
                unsupported.append(element_type)
        if unsupported:
            raise GmshAdapterError(f"Non-TET4 3-D element types generated: {sorted(set(unsupported))}")
        if tet4_count == 0:
            raise GmshAdapterError("Gmsh generated zero TET4 elements")

        if output_msh is not None:
            output_path = Path(output_msh)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            gmsh.write(str(output_path))

        version = getattr(gmsh, "__version__", "unknown")
        return MeshManifest(
            schema="astermax.mesh_manifest.v1",
            source_step_sha256=file_sha256(step_path),
            length_unit="mm",
            gmsh_version=str(version),
            bbox_mm=bbox,
            dimensions_mm=tuple(float(v) for v in dimensions),
            volume_count=len(volumes),
            surface_count=len(surfaces),
            node_count=len(node_tags),
            tet4_count=tet4_count,
            surface_groups=surface_groups,
        )
    finally:
        gmsh.finalize()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="AsterMax STEP -> TET4 Gmsh adapter")
    parser.add_argument("step", type=Path)
    parser.add_argument("--size-mm", type=float, required=True)
    parser.add_argument("--msh", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    manifest = mesh_step_to_tet4(args.step, args.size_mm, output_msh=args.msh)
    payload = asdict(manifest) | {"manifest_sha256": manifest.sha256()}
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
