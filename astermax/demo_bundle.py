"""Deterministic evidence bundle for the AsterMax Windows technical demo.

The bundle is intentionally self-contained and auditable. It executes the verified
multi-GAP / multi-bolt benchmark, exports professional VTK fields, writes a compact
engineering summary, and fingerprints every artifact with SHA-256. No industrial
simulation result is embedded here: all numerical values come from the analytical
verification case already exercised by the harness.

Units: mm, N, MPa.
"""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import argparse
import json
from pathlib import Path

from .bolt_pretension import BoltPretensionConnector
from .gapped_joint_diagnostics import evaluate_gapped_joint
from .gapped_joint_vtk import write_gapped_joint_legacy_vtk
from .gapped_preloaded_joint import solve_gapped_preloaded_joint_from_stiffness
from .gmsh_ascii import SurfaceGroup, TetraMesh


DEMO_CASE_ID = "ASTMX-VERIFIED-MULTIGAP-001"


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def build_verified_multigap_case():
    """Build and solve the deterministic analytical multi-GAP demo benchmark."""
    nodes = (
        (0.0, 0.0, 0.0),
        (3.0, 0.0, 0.0),
        (0.0, 3.0, 0.0),
        (0.5, 0.5, 0.0),
        (1.0, 0.5, 0.0),
        (0.5, 1.0, 0.0),
    )
    mesh = TetraMesh(
        nodes=nodes,
        elements=((0, 1, 2, 3), (0, 1, 2, 4), (0, 1, 2, 5)),
        source_unit="mm",
        surface_groups=(SurfaceGroup("CONTACT_SLAVE", 10, ((3, 4, 5),)),),
    )
    ndof = 18
    stiffness = [[0.0] * ndof for _ in range(ndof)]
    for i in range(ndof):
        stiffness[i][i] = 1.0
    z = (11, 14, 17)
    block = (
        (1500.0, -500.0, 0.0),
        (-500.0, 2000.0, -500.0),
        (0.0, -500.0, 1500.0),
    )
    for a in range(3):
        for b in range(3):
            stiffness[z[a]][z[b]] = block[a][b]
    constraints = {i: 0.0 for i in range(9)}
    for node in (3, 4, 5):
        constraints[3 * node] = 0.0
        constraints[3 * node + 1] = 0.0
    connectors = tuple(
        BoltPretensionConnector(
            node_a=0,
            node_b=node,
            direction=(0.0, 0.0, 1.0),
            axial_stiffness_n_per_mm=4000.0,
            preload_n=1000.0,
        )
        for node in (3, 4, 5)
    )
    gap = {3: 0.1, 4: 0.2, 5: 0.4}
    result = solve_gapped_preloaded_joint_from_stiffness(
        nodes,
        stiffness,
        constraints,
        {},
        connectors,
        gap_by_slave_mm=gap,
        slave_nodes=(3, 4, 5),
        master_triangles=((0, 1, 2),),
        master_normal_hint=(0.0, 0.0, 1.0),
        normal_penalty_n_per_mm=5000.0,
        tangential_penalty_n_per_mm=4000.0,
        friction_coefficient=0.2,
        search_distance_mm=1.0,
        max_iterations=100,
    )
    return mesh, connectors, result


def generate_demo_bundle(output_dir: str | Path) -> dict:
    """Execute the verified case and write a deterministic evidence folder."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    mesh, connectors, result = build_verified_multigap_case()
    diagnostics = evaluate_gapped_joint(connectors, result)
    if not result.joint.contact_result.converged:
        raise RuntimeError("verified demo solver did not converge")

    vtk_path = write_gapped_joint_legacy_vtk(
        destination / "verified_multigap_joint.vtk", mesh, connectors, result
    )

    free_residual_max = max(
        abs(float(v))
        for dof, v in enumerate(result.joint.residual)
        if dof not in {i for i in range(9)} | {9, 10, 12, 13, 15, 16}
    )
    summary = {
        "case_id": DEMO_CASE_ID,
        "scope": "analytical verification benchmark; not an industrial simulation result",
        "unit_system": "mm-N-MPa",
        "source_geometry_policy": "nominal/source coordinates preserved; GAP is an analysis overlay",
        "solver_converged": bool(result.joint.contact_result.converged),
        "solver_iterations": int(result.joint.contact_result.iterations),
        "free_residual_max_N": free_residual_max,
        "initial_gap_mm": [float(g) for _, g in result.gap.gap_by_slave_mm],
        "final_gap_mm": [float(z.final_signed_gap_mm) for z in diagnostics.zones],
        "support_state": ["ACTIVE" if z.active else "OPEN" for z in diagnostics.zones],
        "support_loss_fraction": float(diagnostics.support_loss_fraction),
        "total_normal_contact_force_N": float(diagnostics.total_normal_contact_force_n),
        "total_friction_capacity_N": float(diagnostics.total_friction_capacity_n),
        "bolt_axial_force_N": [
            float(state.final_axial_force_n)
            for state in diagnostics.redistribution.bolt_states
        ],
        "bolt_load_share": [
            float(state.tensile_load_share)
            for state in diagnostics.redistribution.bolt_states
        ],
        "verification_oracle": {
            "expected_final_gap_mm": [-0.052189781021898, 0.004014598540146, 0.200364963503650],
            "expected_bolt_force_N": [391.240875912409, 216.058394160584, 201.459854014599],
            "expected_total_normal_force_N": 260.948905109489,
        },
    }
    summary_path = destination / "summary.json"
    summary_path.write_text(_canonical_json(summary) + "\n", encoding="utf-8")

    readme = (
        "AsterMax Verified Technical Demo Bundle\n"
        "========================================\n"
        f"Case: {DEMO_CASE_ID}\n"
        "Units: mm-N-MPa\n"
        "Scope: analytical verification benchmark, not an industrial simulation result.\n"
        "Open verified_multigap_joint.vtk in ParaView and inspect initial_gap_mm, "
        "final_gap_mm, support_state, contact_pressure_MPa, friction_utilization, "
        "bolt_axial_force_N and bolt_load_share.\n"
        "summary.json contains the numerical evidence and analytical oracle.\n"
        "manifest.json contains SHA-256 fingerprints for reproducibility.\n"
    )
    readme_path = destination / "README.txt"
    readme_path.write_text(readme, encoding="utf-8")

    artifacts = {}
    for path in (vtk_path, summary_path, readme_path):
        artifacts[path.name] = {
            "sha256": _sha256_file(path),
            "bytes": path.stat().st_size,
        }
    evidence_fingerprint = sha256(_canonical_json(artifacts).encode("utf-8")).hexdigest()
    manifest = {
        "case_id": DEMO_CASE_ID,
        "format_version": 1,
        "artifacts": artifacts,
        "evidence_fingerprint_sha256": evidence_fingerprint,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(_canonical_json(manifest) + "\n", encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate the AsterMax verified Windows demo evidence bundle")
    parser.add_argument("--output", default="astermax_demo_evidence", help="output evidence directory")
    args = parser.parse_args(argv)
    manifest = generate_demo_bundle(args.output)
    print(f"AsterMax demo evidence: {Path(args.output).resolve()}")
    print(f"fingerprint: {manifest['evidence_fingerprint_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
