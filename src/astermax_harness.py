from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOWED_LENGTH_UNITS = {"mm"}
ALLOWED_ANALYSIS_TYPES = {"static_structural"}
ALLOWED_ELEMENT_TYPES = {"TET4"}


class ModelValidationError(ValueError):
    """Raised when an AsterMax MVP project violates the certified boundary."""


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    sha256: str
    checks: tuple[str, ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ModelValidationError(message)


def canonical_project_bytes(project: dict[str, Any]) -> bytes:
    return json.dumps(project, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def project_sha256(project: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_project_bytes(project)).hexdigest()


def validate_project(project: dict[str, Any]) -> ValidationReport:
    checks: list[str] = []

    units = project.get("units", {})
    _require(units.get("length") in ALLOWED_LENGTH_UNITS, "MVP requires length unit 'mm'.")
    checks.append("units:mm")

    analysis = project.get("analysis", {})
    _require(analysis.get("type") in ALLOWED_ANALYSIS_TYPES, "Only static_structural is certified in this MVP.")
    _require(analysis.get("linear") is True, "MVP requires linear analysis.")
    _require(analysis.get("small_displacement") is True, "MVP requires small-displacement kinematics.")
    checks.append("analysis:linear_static")

    geometry = project.get("geometry", {})
    _require(geometry.get("part_count") == 1, "MVP supports exactly one 3-D solid part.")
    source = geometry.get("source", {})
    _require(source.get("format", "").upper() in {"STEP", "STP", "BREP", "IGES", "IGS"}, "Unsupported CAD source format.")
    _require(source.get("scale_to_mm") == 1.0, "CAD must enter the certified boundary normalized to millimetres.")
    checks.append("geometry:single_part_mm")

    material = project.get("material", {})
    _require(material.get("model") == "isotropic_linear_elastic", "MVP requires isotropic linear elasticity.")
    e = float(material.get("youngs_modulus_mpa", 0.0))
    nu = float(material.get("poisson_ratio", -1.0))
    _require(e > 0.0, "Young's modulus must be positive in MPa.")
    _require(-1.0 < nu < 0.5, "Poisson ratio must satisfy -1 < nu < 0.5.")
    checks.append("material:isotropic_linear")

    mesh = project.get("mesh", {})
    _require(mesh.get("element_type") in ALLOWED_ELEMENT_TYPES, "MVP requires first-order TET4 elements.")
    size = float(mesh.get("global_size_mm", 0.0))
    _require(size > 0.0, "Global mesh size must be positive in mm.")
    checks.append("mesh:TET4")

    bcs = project.get("boundary_conditions", [])
    loads = project.get("loads", [])
    _require(any(bc.get("type") in {"fixed_support", "displacement"} for bc in bcs), "At least one support is required.")
    _require(len(loads) > 0, "At least one load is required.")
    checks.append("model:supported_and_loaded")

    unsupported = project.get("unsupported_objects", [])
    _require(not unsupported, f"Unsupported advanced objects present: {unsupported}")
    checks.append("scope:no_unsupported_objects")

    return ValidationReport(valid=True, sha256=project_sha256(project), checks=tuple(checks))


def cantilever_reference(project: dict[str, Any]) -> dict[str, float]:
    """Return analytical Euler-Bernoulli reference values; this is not an FEA solve."""
    ref = project.get("analytical_reference", {})
    L = float(ref["length_mm"])
    b = float(ref["width_mm"])
    h = float(ref["height_mm"])
    F = float(ref["tip_force_n"])
    E = float(project["material"]["youngs_modulus_mpa"])

    inertia_mm4 = b * h**3 / 12.0
    tip_displacement_mm = F * L**3 / (3.0 * E * inertia_mm4)
    root_bending_stress_mpa = 6.0 * F * L / (b * h**2)

    return {
        "second_moment_mm4": inertia_mm4,
        "tip_displacement_mm": tip_displacement_mm,
        "root_bending_stress_mpa": root_bending_stress_mpa,
        "reaction_force_n": F,
        "reaction_moment_nmm": F * L,
    }


def load_and_validate(path: str | Path) -> tuple[dict[str, Any], ValidationReport]:
    project = json.loads(Path(path).read_text(encoding="utf-8"))
    return project, validate_project(project)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="AsterMax portable MVP harness")
    parser.add_argument("project", type=Path)
    parser.add_argument("--reference", action="store_true", help="print analytical cantilever reference values")
    args = parser.parse_args()

    project, report = load_and_validate(args.project)
    payload: dict[str, Any] = {
        "valid": report.valid,
        "sha256": report.sha256,
        "checks": list(report.checks),
    }
    if args.reference:
        payload["analytical_reference"] = cantilever_reference(project)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
