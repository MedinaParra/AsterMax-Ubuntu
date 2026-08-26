import pytest

from astermax.solver.result_post import (
    ElementFamily,
    FeResultTopologyManifestV1,
    MeshConvergenceSampleV1,
    MeshLevelV1,
    ResultArrayV1,
    ResultAssociation,
    evaluate_pair,
)


def mesh(level, h, hc, nodes, elems, family=ElementFamily.TET10):
    return MeshLevelV1(
        level_id=level,
        global_size_mm=h,
        contact_size_mm=hc,
        element_family=family,
        node_count=nodes,
        element_count=elems,
        mesh_sha256=("a" if level == "M0" else "b") * 64,
    )


def sample(level, h, hc, nodes, elems, factor=1.0):
    return MeshConvergenceSampleV1(
        mesh=mesh(level, h, hc, nodes, elems),
        displacement_probe_mm=0.300 * factor,
        reaction_resultant_n=1_190_000 * factor,
        contact_resultant_n=1_190_000 * factor,
        active_contact_area_mm2=22_500 * factor,
        von_mises_p95_mpa=250 * factor,
        von_mises_p99_mpa=300 * factor,
        contact_pressure_p95_mpa=400 * factor,
        contact_pressure_p99_mpa=480 * factor,
        von_mises_max_mpa=900 * factor,
        contact_pressure_max_mpa=1_200 * factor,
    )


def test_topology_manifest_requires_preserved_connectivity():
    with pytest.raises(ValueError, match="complete mesh topology"):
        FeResultTopologyManifestV1(
            mesh=mesh("M0", 8, 3, 100, 200),
            body_ids=["HUB", "SEGMENT"],
            arrays=[
                ResultArrayV1(
                    name="S_VM_RAW",
                    association=ResultAssociation.CELL,
                    components=1,
                    unit="MPa",
                    evidence_class="SOLVER_RESULT",
                    raw_solver_values=True,
                )
            ],
            connectivity_preserved=False,
        )


def test_convergence_uses_percentiles_and_ignores_peak_as_gate():
    coarse = sample("M0", 8, 3, 1000, 4000, factor=0.98)
    fine = sample("M1", 6, 2, 2000, 9000, factor=1.0)
    coarse.von_mises_max_mpa = 400
    fine.von_mises_max_mpa = 1200
    report = evaluate_pair(coarse, fine)
    assert report.passed
    peak = next(item for item in report.metrics if item.metric == "von_mises_max_mpa")
    assert peak.gate_metric is False
    assert peak.passed is True


def test_convergence_fails_when_p99_does_not_converge():
    coarse = sample("M0", 8, 3, 1000, 4000, factor=1.0)
    fine = sample("M1", 6, 2, 2000, 9000, factor=1.0)
    coarse.von_mises_p99_mpa = 250
    fine.von_mises_p99_mpa = 300
    report = evaluate_pair(coarse, fine)
    assert not report.passed
    p99 = next(item for item in report.metrics if item.metric == "von_mises_p99_mpa")
    assert not p99.passed


def test_tet4_tet10_are_not_equivalent_convergence_evidence():
    coarse = sample("M0", 8, 3, 1000, 4000)
    fine = sample("M1", 6, 2, 2000, 9000)
    fine.mesh.element_family = ElementFamily.TET4
    with pytest.raises(ValueError, match="Tet4 and Tet10"):
        evaluate_pair(coarse, fine)
