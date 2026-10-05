from __future__ import annotations

import argparse
import json
from pathlib import Path

import gmsh


MEMORY_REFERENCE_NODES = 148000
MEMORY_REFERENCE_ELEMENTS = 75900
RANDOM_FACTOR_RETRY_LADDER = (1.0e-9, 1.0e-8, 1.0e-7, 1.0e-6)
OCC_HEAL_TOLERANCE_MM = 1.0e-6


def _global_bbox(volumes: list[tuple[int, int]]) -> tuple[float, float, float, float, float, float]:
    boxes = [gmsh.model.getBoundingBox(dim, tag) for dim, tag in volumes]
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        min(b[2] for b in boxes),
        max(b[3] for b in boxes),
        max(b[4] for b in boxes),
        max(b[5] for b in boxes),
    )


def _smallest_occ_entities(dim: int, count: int = 30) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    metric_name = {1: "length_mm", 2: "area_mm2", 3: "volume_mm3"}[dim]
    for _, tag in gmsh.model.getEntities(dim):
        try:
            metric = float(gmsh.model.occ.getMass(dim, tag))
            bbox = [float(v) for v in gmsh.model.getBoundingBox(dim, tag)]
        except Exception as exc:
            rows.append({"tag": int(tag), "diagnostic_error": f"{type(exc).__name__}: {exc}"})
            continue
        rows.append({"tag": int(tag), metric_name: metric, "bbox_mm": bbox})
    rows.sort(key=lambda row: float(row.get(metric_name, float("inf"))))
    return rows[:count]


def _generate_tet10_with_deterministic_retry() -> tuple[float, list[dict[str, object]]]:
    attempts: list[dict[str, object]] = []
    last_error: Exception | None = None
    for factor in RANDOM_FACTOR_RETRY_LADDER:
        try:
            gmsh.model.mesh.clear()
            gmsh.option.setNumber("Mesh.RandomFactor", factor)
            gmsh.model.mesh.generate(3)
            gmsh.model.mesh.setOrder(2)
            attempts.append({"random_factor": factor, "status": "PASS"})
            return factor, attempts
        except Exception as exc:
            last_error = exc
            attempts.append(
                {
                    "random_factor": factor,
                    "status": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    assert last_error is not None
    raise RuntimeError(
        "TET10_MESH_RETRY_EXHAUSTED: "
        + "; ".join(f"rf={a['random_factor']}: {a.get('error', '')}" for a in attempts)
    ) from last_error


def main() -> int:
    parser = argparse.ArgumentParser(description="Mesh the SKM pulley test-bench structural CAD with Gmsh TET10.")
    parser.add_argument("step", type=Path)
    parser.add_argument("--out", type=Path, default=Path("artifacts/banco_pruebas"))
    parser.add_argument("--min-mm", type=float, default=30.0)
    parser.add_argument("--max-mm", type=float, default=110.0)
    parser.add_argument("--curvature-elements", type=float, default=20.0)
    args = parser.parse_args()

    if not args.step.is_file():
        raise SystemExit(f"CAD_NOT_FOUND: {args.step}")
    if args.min_mm <= 0 or args.max_mm < args.min_mm:
        raise SystemExit("INVALID_MESH_SIZE_RANGE")

    args.out.mkdir(parents=True, exist_ok=True)
    gmsh.initialize()
    evidence: dict[str, object] = {
        "status": "FAIL",
        "environment": "GitHub Actions windows-latest / gmsh 4.13.1 via AsterMax pyproject",
        "source_cad": str(args.step).replace("\\", "/"),
        "mesh": {
            "element_family": "TET10",
            "min_size_mm": args.min_mm,
            "max_size_mm": args.max_mm,
            "curvature_elements_per_2pi": args.curvature_elements,
            "random_factor_retry_ladder": list(RANDOM_FACTOR_RETRY_LADDER),
        },
        "geometry_healing": {
            "tolerance_mm": OCC_HEAL_TOLERANCE_MM,
            "fix_degenerated": True,
            "fix_small_edges": True,
            "fix_small_faces": True,
            "sew_faces": False,
            "make_solids": False,
            "reason": "Keep the 106 structural solids intact; prior global sewing converted them to shells.",
        },
        "memory_reference": {
            "nodes_approx": MEMORY_REFERENCE_NODES,
            "elements_approx": MEMORY_REFERENCE_ELEMENTS,
        },
    }
    try:
        gmsh.option.setNumber("General.Terminal", 1)
        gmsh.model.add("skm_banco_pruebas_structure")

        # Import the verified BREP without automatic OCC healing. In the previous
        # experiment enabling OCCSewFaces/OCCMakeSolids at import repaired wires
        # but converted all 106 valid solids into shells. Healing is therefore
        # applied below in a targeted mode that does not sew or rebuild solids.
        imported = gmsh.model.occ.importShapes(str(args.step))
        gmsh.model.occ.synchronize()
        initial_volumes = gmsh.model.getEntities(3)
        if not initial_volumes:
            raise RuntimeError("NO_IMPORTED_VOLUMES")

        evidence["before_heal"] = {
            "volume_count": len(initial_volumes),
            "curve_count": len(gmsh.model.getEntities(1)),
            "surface_count": len(gmsh.model.getEntities(2)),
            "smallest_edges": _smallest_occ_entities(1),
            "smallest_faces": _smallest_occ_entities(2),
        }

        healed = gmsh.model.occ.healShapes(
            [],
            tolerance=OCC_HEAL_TOLERANCE_MM,
            fixDegenerated=True,
            fixSmallEdges=True,
            fixSmallFaces=True,
            sewFaces=False,
            makeSolids=False,
        )
        gmsh.model.occ.synchronize()
        healed_volumes = gmsh.model.getEntities(3)
        if len(healed_volumes) != len(initial_volumes):
            raise RuntimeError(
                f"HEAL_CHANGED_VOLUME_COUNT:{len(initial_volumes)}->{len(healed_volumes)}"
            )

        evidence["after_heal"] = {
            "returned_entity_count": len(healed),
            "volume_count": len(healed_volumes),
            "curve_count": len(gmsh.model.getEntities(1)),
            "surface_count": len(gmsh.model.getEntities(2)),
            "smallest_edges": _smallest_occ_entities(1),
            "smallest_faces": _smallest_occ_entities(2),
        }

        gmsh.model.occ.removeAllDuplicates()
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if not volumes:
            raise RuntimeError("NO_VOLUMES_AFTER_OCC_DEDUP")

        bbox = _global_bbox(volumes)
        evidence.update(
            {
                "imported_entity_count": len(imported),
                "initial_volume_count": len(initial_volumes),
                "healed_volume_count": len(healed_volumes),
                "conformal_volume_count": len(volumes),
                "bbox_mm": list(map(float, bbox)),
                "post_dedup_smallest_edges": _smallest_occ_entities(1),
                "post_dedup_smallest_faces": _smallest_occ_entities(2),
            }
        )

        gmsh.option.setNumber("Mesh.MeshSizeMin", float(args.min_mm))
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(args.max_mm))
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", float(args.curvature_elements))
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.HighOrderOptimize", 1)
        gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)

        selected_random_factor, attempts = _generate_tet10_with_deterministic_retry()
        evidence["mesh_attempts"] = attempts
        evidence["selected_random_factor"] = selected_random_factor

        node_tags, _, _ = gmsh.model.mesh.getNodes()
        element_types, element_tags, _ = gmsh.model.mesh.getElements(3)
        tet10_count = 0
        unsupported: list[int] = []
        for etype, tags in zip(element_types, element_tags):
            if int(etype) == 11:
                tet10_count += len(tags)
            elif len(tags):
                unsupported.append(int(etype))
        if unsupported:
            raise RuntimeError(f"NON_TET10_VOLUME_TYPES:{sorted(set(unsupported))}")
        if tet10_count <= 0:
            raise RuntimeError("NO_TET10_ELEMENTS")

        msh_path = args.out / "banco_estructura_tet10.msh"
        med_path = args.out / "banco_estructura_tet10.med"
        gmsh.write(str(msh_path))
        gmsh.write(str(med_path))

        nodes = int(len(node_tags))
        evidence.update(
            {
                "status": "PASS",
                "gmsh_version": str(getattr(gmsh, "__version__", "unknown")),
                "node_count": nodes,
                "tet10_count": int(tet10_count),
                "node_ratio_to_memory": nodes / MEMORY_REFERENCE_NODES,
                "element_ratio_to_memory": tet10_count / MEMORY_REFERENCE_ELEMENTS,
                "outputs": {
                    "msh": msh_path.as_posix(),
                    "med": med_path.as_posix(),
                },
            }
        )
        return 0
    except Exception as exc:
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        return 2
    finally:
        (args.out / "mesh_evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
        )
        gmsh.finalize()


if __name__ == "__main__":
    raise SystemExit(main())
