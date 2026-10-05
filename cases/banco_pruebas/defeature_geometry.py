from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Defeaturing


EXPECTED_SOLIDS = 106
THRESHOLD_MM2 = 50.0
DENSITY_KG_M3 = 7850.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove sub-mesh-scale sliver faces from the verified SKM test-bench BREP."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--threshold-mm2", type=float, default=THRESHOLD_MM2)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("artifacts/banco_pruebas/defeature_evidence.json"),
    )
    args = parser.parse_args()

    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, object] = {
        "status": "FAIL",
        "method": "OpenCascade BRepAlgoAPI_Defeaturing via CadQuery/OCP",
        "threshold_mm2": float(args.threshold_mm2),
        "density_kg_m3": DENSITY_KG_M3,
        "expected_solids": EXPECTED_SOLIDS,
        "rationale": (
            "Remove only CAD sliver faces whose area is below 50 mm^2, while preserving "
            "the 106 load-bearing solids. The calculation-memory FEM target has a 30 mm "
            "minimum element size, so these features are sub-mesh-scale."
        ),
    }

    try:
        if not args.input.is_file():
            raise RuntimeError(f"INPUT_NOT_FOUND:{args.input}")
        if args.threshold_mm2 <= 0:
            raise RuntimeError("INVALID_THRESHOLD")

        evidence["input_sha256"] = sha256(args.input)
        shape = cq.importers.importBrep(str(args.input)).val()
        solids = list(shape.Solids())
        if len(solids) != EXPECTED_SOLIDS:
            raise RuntimeError(f"SOLID_COUNT_MISMATCH:{len(solids)}!={EXPECTED_SOLIDS}")
        if not shape.isValid():
            raise RuntimeError("INPUT_COMPOUND_INVALID")

        before_volume_mm3 = float(sum(s.Volume() for s in solids))
        cleaned: list[cq.Shape] = []
        removed_faces = 0
        changed_solids = 0
        per_solid: list[dict[str, object]] = []

        for index, solid in enumerate(solids):
            tiny = [face for face in solid.Faces() if float(face.Area()) < args.threshold_mm2]
            row: dict[str, object] = {
                "solid_index": index,
                "input_volume_mm3": float(solid.Volume()),
                "tiny_face_count": len(tiny),
            }
            if not tiny:
                cleaned.append(solid)
                row["status"] = "UNCHANGED"
                per_solid.append(row)
                continue

            algorithm = BRepAlgoAPI_Defeaturing()
            algorithm.SetShape(solid.wrapped)
            for face in tiny:
                algorithm.AddFaceToRemove(face.wrapped)
            algorithm.Build()
            if not algorithm.IsDone():
                raise RuntimeError(f"DEFEATURE_NOT_DONE_SOLID_{index}")

            out = cq.Shape.cast(algorithm.Shape())
            out_solids = list(out.Solids())
            if len(out_solids) != 1:
                raise RuntimeError(f"DEFEATURE_SOLID_COUNT_{index}:{len(out_solids)}")
            clean_solid = out_solids[0]
            if not clean_solid.isValid():
                raise RuntimeError(f"DEFEATURE_INVALID_SOLID_{index}")

            cleaned.append(clean_solid)
            removed_faces += len(tiny)
            changed_solids += 1
            row.update(
                {
                    "status": "DEFEATURED",
                    "output_volume_mm3": float(clean_solid.Volume()),
                    "volume_delta_mm3": float(clean_solid.Volume() - solid.Volume()),
                    "min_input_face_area_mm2": min(float(f.Area()) for f in tiny),
                }
            )
            per_solid.append(row)

        compound = cq.Compound.makeCompound(cleaned)
        output_solids = list(compound.Solids())
        if len(output_solids) != EXPECTED_SOLIDS:
            raise RuntimeError(f"OUTPUT_SOLID_COUNT_MISMATCH:{len(output_solids)}")
        if not compound.isValid():
            raise RuntimeError("OUTPUT_COMPOUND_INVALID")

        after_volume_mm3 = float(sum(s.Volume() for s in output_solids))
        delta_mm3 = after_volume_mm3 - before_volume_mm3
        relative_delta = delta_mm3 / before_volume_mm3
        mass_delta_kg = delta_mm3 * 1.0e-9 * DENSITY_KG_M3

        args.output.parent.mkdir(parents=True, exist_ok=True)
        cq.exporters.export(compound, str(args.output))

        evidence.update(
            {
                "status": "PASS",
                "input_solids": len(solids),
                "output_solids": len(output_solids),
                "changed_solids": changed_solids,
                "removed_faces": removed_faces,
                "before_volume_mm3": before_volume_mm3,
                "after_volume_mm3": after_volume_mm3,
                "volume_delta_mm3": delta_mm3,
                "relative_volume_delta": relative_delta,
                "mass_delta_kg": mass_delta_kg,
                "output_sha256": sha256(args.output),
                "output_path": args.output.as_posix(),
                "per_solid": per_solid,
            }
        )
        print(
            "PASS "
            f"solids={len(output_solids)} changed={changed_solids} "
            f"removed_faces={removed_faces} volume_delta_mm3={delta_mm3:.6f} "
            f"mass_delta_kg={mass_delta_kg:.9f} sha256={evidence['output_sha256']}"
        )
        return 0
    except Exception as exc:
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAIL {evidence['error']}")
        return 2
    finally:
        args.evidence.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
