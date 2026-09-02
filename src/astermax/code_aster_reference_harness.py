from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from .code_aster_med_writer import verify_code_aster_med_groups, write_code_aster_med
from .code_aster_study import LinearStaticStudy, render_linear_static_comm


class ReferenceHarnessError(RuntimeError):
    pass


@dataclass(frozen=True)
class UniaxialPrismSpec:
    length_mm: float = 100.0
    width_mm: float = 20.0
    height_mm: float = 10.0
    young_mpa: float = 210000.0
    poisson: float = 0.3
    total_force_n: float = 10000.0
    mesh_size_mm: float = 10.0

    def validate(self) -> None:
        values = (
            self.length_mm,
            self.width_mm,
            self.height_mm,
            self.young_mpa,
            self.mesh_size_mm,
        )
        if not all(np.isfinite(v) and v > 0.0 for v in values):
            raise ReferenceHarnessError("REFERENCE_SPEC_POSITIVE_VALUE_REQUIRED")
        if not np.isfinite(self.total_force_n) or self.total_force_n == 0.0:
            raise ReferenceHarnessError("REFERENCE_SPEC_FORCE_INVALID")
        if not (-1.0 < self.poisson < 0.5):
            raise ReferenceHarnessError("REFERENCE_SPEC_POISSON_INVALID")

    @property
    def area_mm2(self) -> float:
        return self.width_mm * self.height_mm

    @property
    def expected_sigma_x_mpa(self) -> float:
        return self.total_force_n / self.area_mm2

    @property
    def expected_epsilon_x(self) -> float:
        return self.expected_sigma_x_mpa / self.young_mpa

    @property
    def expected_ux_mm(self) -> float:
        return self.expected_epsilon_x * self.length_mm

    @property
    def expected_support_reaction_x_n(self) -> float:
        return -self.total_force_n

    @property
    def traction_x_mpa(self) -> float:
        return self.total_force_n / self.area_mm2


@dataclass(frozen=True)
class ReferenceMesh:
    nodes_mm: np.ndarray
    tet10: np.ndarray
    support_tri6: np.ndarray
    load_tri6: np.ndarray


@dataclass(frozen=True)
class ReferenceObservedMetrics:
    load_face_mean_ux_mm: float
    support_reaction_x_n: float
    axial_stress_mpa: float


@dataclass(frozen=True)
class ReferenceVerificationEvidence:
    expected_ux_mm: float
    observed_ux_mm: float
    ux_relative_error: float
    expected_reaction_x_n: float
    observed_reaction_x_n: float
    reaction_relative_error: float
    expected_sigma_x_mpa: float
    observed_sigma_x_mpa: float
    stress_relative_error: float
    displacement_verified: bool
    reaction_verified: bool
    stress_verified: bool
    numerical_verification: bool
    fea_solve_executed: bool
    results_verified: bool

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def _relative_error(observed: float, expected: float) -> float:
    scale = abs(expected)
    if scale == 0.0:
        raise ReferenceHarnessError("REFERENCE_EXPECTED_VALUE_ZERO")
    return abs(observed - expected) / scale


def verify_uniaxial_reference_results(
    spec: UniaxialPrismSpec,
    observed: ReferenceObservedMetrics,
    *,
    displacement_rtol: float = 0.03,
    reaction_rtol: float = 0.01,
    stress_rtol: float = 0.05,
    fea_solve_executed: bool,
) -> ReferenceVerificationEvidence:
    """Verify a solved 3-D uniaxial reference case against mechanics.

    The expected solution is the Saint-Venant uniform axial state for a prismatic
    bar loaded by uniform end traction. This gate cannot create solver evidence:
    callers must pass a real solve-evidence state. If no genuine solve occurred,
    numerical_verification and results_verified remain False even if synthetic
    numbers happen to equal the analytical solution.
    """
    spec.validate()
    if not all(np.isfinite(v) for v in (
        observed.load_face_mean_ux_mm,
        observed.support_reaction_x_n,
        observed.axial_stress_mpa,
    )):
        raise ReferenceHarnessError("REFERENCE_OBSERVED_METRIC_NONFINITE")
    for tol in (displacement_rtol, reaction_rtol, stress_rtol):
        if not np.isfinite(tol) or not (0.0 < tol < 1.0):
            raise ReferenceHarnessError("REFERENCE_TOLERANCE_INVALID")

    ux_error = _relative_error(observed.load_face_mean_ux_mm, spec.expected_ux_mm)
    reaction_error = _relative_error(observed.support_reaction_x_n, spec.expected_support_reaction_x_n)
    stress_error = _relative_error(observed.axial_stress_mpa, spec.expected_sigma_x_mpa)
    ux_ok = ux_error <= displacement_rtol
    reaction_ok = reaction_error <= reaction_rtol
    stress_ok = stress_error <= stress_rtol
    numerical_ok = bool(fea_solve_executed and ux_ok and reaction_ok and stress_ok)
    return ReferenceVerificationEvidence(
        expected_ux_mm=spec.expected_ux_mm,
        observed_ux_mm=observed.load_face_mean_ux_mm,
        ux_relative_error=ux_error,
        expected_reaction_x_n=spec.expected_support_reaction_x_n,
        observed_reaction_x_n=observed.support_reaction_x_n,
        reaction_relative_error=reaction_error,
        expected_sigma_x_mpa=spec.expected_sigma_x_mpa,
        observed_sigma_x_mpa=observed.axial_stress_mpa,
        stress_relative_error=stress_error,
        displacement_verified=ux_ok,
        reaction_verified=reaction_ok,
        stress_verified=stress_ok,
        numerical_verification=numerical_ok,
        fea_solve_executed=bool(fea_solve_executed),
        results_verified=numerical_ok,
    )


def generate_uniaxial_prism_tet10(spec: UniaxialPrismSpec) -> ReferenceMesh:
    """Generate a real second-order Gmsh box mesh and identify x-end TRI6 faces."""
    spec.validate()
    import gmsh

    owned = not bool(gmsh.isInitialized())
    if owned:
        gmsh.initialize()
    try:
        gmsh.clear()
        gmsh.model.add("astermax_uniaxial_reference")
        volume = gmsh.model.occ.addBox(0.0, 0.0, 0.0, spec.length_mm, spec.width_mm, spec.height_mm)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", spec.mesh_size_mm)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", spec.mesh_size_mm)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.model.mesh.generate(3)
        gmsh.model.mesh.setOrder(2)

        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        points = np.asarray(coords, dtype=float).reshape((-1, 3))
        tag_to_index = {int(tag): i for i, tag in enumerate(node_tags)}

        def connectivity_for(dim: int, tag: int | None, wanted_type: int, width: int) -> list[list[int]]:
            types, _, node_blocks = gmsh.model.mesh.getElements(dim, -1 if tag is None else tag)
            rows: list[list[int]] = []
            for element_type, raw_nodes in zip(types, node_blocks):
                if int(element_type) != wanted_type:
                    continue
                raw = np.asarray(raw_nodes, dtype=np.int64).reshape((-1, width))
                rows.extend([[tag_to_index[int(n)] for n in row] for row in raw])
            return rows

        tet_rows = connectivity_for(3, volume, 11, 10)
        if not tet_rows:
            raise ReferenceHarnessError("REFERENCE_GMSH_TET10_MISSING")

        support_rows: list[list[int]] = []
        load_rows: list[list[int]] = []
        tol = max(1.0e-7 * spec.length_mm, 1.0e-9)
        for _, surface_tag in gmsh.model.getEntities(2):
            tri_rows = connectivity_for(2, int(surface_tag), 9, 6)
            for row in tri_rows:
                corner_x = points[np.asarray(row[:3], dtype=int), 0]
                mean_x = float(np.mean(corner_x))
                if abs(mean_x) <= tol and float(np.max(np.abs(corner_x))) <= tol:
                    support_rows.append(row)
                elif abs(mean_x - spec.length_mm) <= tol and float(np.max(np.abs(corner_x - spec.length_mm))) <= tol:
                    load_rows.append(row)
        if not support_rows:
            raise ReferenceHarnessError("REFERENCE_SUPPORT_TRI6_MISSING")
        if not load_rows:
            raise ReferenceHarnessError("REFERENCE_LOAD_TRI6_MISSING")

        return ReferenceMesh(
            nodes_mm=points,
            tet10=np.asarray(tet_rows, dtype=int),
            support_tri6=np.asarray(support_rows, dtype=int),
            load_tri6=np.asarray(load_rows, dtype=int),
        )
    finally:
        gmsh.clear()
        if owned:
            gmsh.finalize()


def prepare_reference_solver_bundle(spec: UniaxialPrismSpec, directory: str | Path) -> dict[str, object]:
    """Build geometry/mesh/MED/.comm evidence without claiming solver execution."""
    spec.validate()
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    mesh = generate_uniaxial_prism_tet10(spec)
    med = write_code_aster_med(
        root / "astermax.med",
        nodes_mm=mesh.nodes_mm,
        tet10=mesh.tet10,
        support_tri6=mesh.support_tri6,
        load_tri6=mesh.load_tri6,
        support_group="FIXED_FACE",
        load_group="LOAD_FACE",
        volume_group="SOLID",
    )
    med_evidence = verify_code_aster_med_groups(
        med,
        expected_support_tri6=mesh.support_tri6.shape[0],
        expected_load_tri6=mesh.load_tri6.shape[0],
        expected_tet10=mesh.tet10.shape[0],
    )
    study = LinearStaticStudy(
        mesh_filename="astermax.med",
        support_group=med_evidence.support_group,
        load_group=med_evidence.load_group,
        young_mpa=spec.young_mpa,
        poisson=spec.poisson,
        traction_mpa=(spec.traction_x_mpa, 0.0, 0.0),
    )
    comm_text = render_linear_static_comm(study)
    comm = root / "astermax.comm"
    comm.write_text(comm_text, encoding="utf-8", newline="\n")
    evidence = {
        "case": "3D_UNIAXIAL_PRISM_TET10",
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "nodes": int(mesh.nodes_mm.shape[0]),
        "tet10": int(mesh.tet10.shape[0]),
        "support_tri6": int(mesh.support_tri6.shape[0]),
        "load_tri6": int(mesh.load_tri6.shape[0]),
        "area_mm2": spec.area_mm2,
        "force_n": spec.total_force_n,
        "traction_x_mpa": spec.traction_x_mpa,
        "expected_sigma_x_mpa": spec.expected_sigma_x_mpa,
        "expected_epsilon_x": spec.expected_epsilon_x,
        "expected_ux_mm": spec.expected_ux_mm,
        "expected_support_reaction_x_n": spec.expected_support_reaction_x_n,
        "med_sha256": med_evidence.med_sha256,
        "comm_sha256": sha256(comm.read_bytes()).hexdigest(),
        "med_groups_verified": med_evidence.med_family_names_verified,
        "fea_solve_executed": False,
        "numerical_verification": False,
        "results_verified": False,
    }
    (root / "reference_case_evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    return evidence
