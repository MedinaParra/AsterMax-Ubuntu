from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import numpy as np

from astermax.credibility import canonical_sha256
from .adaptive_execution_bundle import AdaptiveExecutionArtifactBundleV1, verify_adaptive_execution_artifact_bundle
from .adaptive_hotspot_visualization import AdaptiveHotspotMarkerV1, AdaptiveHotspotVisualizationV1
from .adaptive_stress_comparison import (
    AdaptiveStressComparisonV1,
    StressContourElementV1,
    VerifiedStressContourFieldV1,
    verify_adaptive_stress_comparison,
)


class PortableAdaptiveResultsError(ValueError):
    pass


@dataclass(frozen=True)
class PortableAdaptiveResultsPackageV1:
    schema: str
    status: str
    source_bundle_sha256: str
    source_step_sha256: str
    baseline_mesh_sha256: str
    refined_mesh_sha256: str
    baseline_solve_evidence_sha256: str
    refined_solve_evidence_sha256: str
    payload_sha256: str
    views_sha256: str
    manifest_sha256: str
    package_path: str
    package_file_sha256: str
    payload_arrays: Mapping[str, np.ndarray]
    hotspot_view: AdaptiveHotspotVisualizationV1
    stress_view: AdaptiveStressComparisonV1
    claims: dict[str, bool]
    package_sha256: str


@dataclass(frozen=True)
class PortableAdaptiveResultsBindingReceiptV1:
    schema: str
    package_sha256: str
    bound_tabs: tuple[str, ...]
    hotspot_visualization_sha256: str
    stress_comparison_sha256: str
    receipt_sha256: str


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _payload_bytes(bundle: AdaptiveExecutionArtifactBundleV1) -> bytes:
    baseline_result = bundle.baseline_solved["result"]
    refined_result = bundle.refined_solved["result"]
    buffer = BytesIO()
    np.savez_compressed(
        buffer,
        baseline_nodes_mm=np.asarray(bundle.baseline_mesh.nodes_mm),
        baseline_elements=np.asarray(bundle.baseline_mesh.elements),
        baseline_displacement_mm=np.asarray(baseline_result.displacement_mm),
        baseline_reactions_n=np.asarray(baseline_result.reactions_n),
        baseline_ip_stress_mpa=np.asarray(baseline_result.integration_point_stress_mpa),
        baseline_ip_von_mises_mpa=np.asarray(baseline_result.integration_point_von_mises_mpa),
        refined_nodes_mm=np.asarray(bundle.refined_mesh.nodes_mm),
        refined_elements=np.asarray(bundle.refined_mesh.elements),
        refined_displacement_mm=np.asarray(refined_result.displacement_mm),
        refined_reactions_n=np.asarray(refined_result.reactions_n),
        refined_ip_stress_mpa=np.asarray(refined_result.integration_point_stress_mpa),
        refined_ip_von_mises_mpa=np.asarray(refined_result.integration_point_von_mises_mpa),
    )
    return buffer.getvalue()


def _views_payload(bundle: AdaptiveExecutionArtifactBundleV1) -> dict[str, Any]:
    return {
        "hotspot_view": asdict(bundle.hotspot_view),
        "stress_view": asdict(bundle.stress_view),
    }


def _manifest_core(bundle: AdaptiveExecutionArtifactBundleV1, payload_sha: str, views_sha: str) -> dict[str, Any]:
    return {
        "schema": "AsterMaxPortableAdaptiveResultsManifestV1",
        "source_bundle_sha256": bundle.bundle_sha256,
        "source_step_sha256": bundle.hotspot_view.source_step_sha256,
        "baseline_mesh_sha256": bundle.baseline_mesh_sha256,
        "refined_mesh_sha256": bundle.refined_mesh_sha256,
        "baseline_solve_evidence_sha256": bundle.baseline_solve_evidence_sha256,
        "refined_solve_evidence_sha256": bundle.refined_solve_evidence_sha256,
        "baseline_result_field_sha256": bundle.baseline_result_field_sha256,
        "refined_result_field_sha256": bundle.refined_result_field_sha256,
        "hotspot_visualization_sha256": bundle.hotspot_visualization_sha256,
        "stress_comparison_sha256": bundle.stress_comparison_sha256,
        "payload_entry": "results.npz",
        "payload_sha256": payload_sha,
        "views_entry": "views.json",
        "views_sha256": views_sha,
        "solver_required_to_open": False,
        "gmsh_required_to_open": False,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }


def write_portable_adaptive_results_package(bundle: AdaptiveExecutionArtifactBundleV1, output_path: str | Path) -> Path:
    """Persist a verified adaptive execution as a self-contained reopenable Results package.

    Opening the package never invokes CAD import, Gmsh or the structural solver. The
    binary arrays and presentation views are independently hashed and linked through
    a canonical manifest.
    """
    verify_adaptive_execution_artifact_bundle(bundle)
    output = Path(output_path)
    if output.suffix.lower() != ".astermaxr":
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_EXTENSION")
    output.parent.mkdir(parents=True, exist_ok=True)

    payload = _payload_bytes(bundle)
    payload_sha = _sha256_bytes(payload)
    views = _views_payload(bundle)
    views_bytes = _json_bytes(views)
    views_sha = _sha256_bytes(views_bytes)
    manifest_core = _manifest_core(bundle, payload_sha, views_sha)
    manifest = dict(manifest_core)
    manifest["manifest_sha256"] = canonical_sha256(manifest_core)
    manifest_bytes = _json_bytes(manifest)

    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest_bytes)
        archive.writestr("views.json", views_bytes)
        archive.writestr("results.npz", payload)
    if not output.is_file() or output.stat().st_size <= 0:
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_FILE_REQUIRED")
    return output


def _tuple3(value: Any) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_POINT")
    point = tuple(float(v) for v in value)
    if not all(np.isfinite(v) for v in point):
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_POINT_NONFINITE")
    return point


def _rebuild_hotspot(raw: Mapping[str, Any]) -> AdaptiveHotspotVisualizationV1:
    markers = tuple(
        AdaptiveHotspotMarkerV1(
            rank=int(row["rank"]), element_index=int(row["element_index"]),
            centroid_mm=_tuple3(row["centroid_mm"]), normalized_indicator=float(row["normalized_indicator"]),
            mean_von_mises_mpa=float(row["mean_von_mises_mpa"]), refinement_radius_mm=float(row["refinement_radius_mm"]),
            refinement_target_size_mm=float(row["refinement_target_size_mm"]),
        )
        for row in raw["hotspot_markers"]
    )
    bounds = raw["projection_bounds_mm"]
    view = AdaptiveHotspotVisualizationV1(
        schema=str(raw["schema"]), semantics=str(raw["semantics"]), status=str(raw["status"]),
        source_step_sha256=str(raw["source_step_sha256"]), baseline_mesh_sha256=str(raw["baseline_mesh_sha256"]),
        refined_mesh_sha256=str(raw["refined_mesh_sha256"]), baseline_element_count=int(raw["baseline_element_count"]),
        refined_element_count=int(raw["refined_element_count"]), baseline_max_indicator=float(raw["baseline_max_indicator"]),
        refined_max_indicator=float(raw["refined_max_indicator"]), indicator_relative_change=float(raw["indicator_relative_change"]),
        indicator_status=str(raw["indicator_status"]), qoi_status=str(raw["qoi_status"]), qoi_relative_change=float(raw["qoi_relative_change"]),
        hotspot_markers=markers, projection_bounds_mm=(_tuple3(bounds[0]), _tuple3(bounds[1])), claims=dict(raw["claims"]),
        visualization_sha256=str(raw["visualization_sha256"]),
    )
    core = {
        "schema": view.schema, "status": view.status, "source_step_sha256": view.source_step_sha256,
        "baseline_mesh_sha256": view.baseline_mesh_sha256, "refined_mesh_sha256": view.refined_mesh_sha256,
        "baseline_element_count": view.baseline_element_count, "refined_element_count": view.refined_element_count,
        "baseline_max_indicator": view.baseline_max_indicator, "refined_max_indicator": view.refined_max_indicator,
        "indicator_relative_change": view.indicator_relative_change, "indicator_status": view.indicator_status,
        "qoi_status": view.qoi_status, "qoi_relative_change": view.qoi_relative_change,
        "hotspot_markers": [asdict(v) for v in view.hotspot_markers], "projection_bounds_mm": view.projection_bounds_mm,
        "claims": view.claims,
    }
    if canonical_sha256(core) != view.visualization_sha256:
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_HOTSPOT_TAMPERED")
    if view.claims.get("estimator_certified") or view.claims.get("solution_error_bound_claimed") or view.claims.get("ansys_equivalence"):
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_HOTSPOT_OVERCLAIM")
    return view


def _rebuild_field(raw: Mapping[str, Any]) -> VerifiedStressContourFieldV1:
    rows = tuple(
        StressContourElementV1(
            element_index=int(row["element_index"]), centroid_mm=_tuple3(row["centroid_mm"]),
            deformed_centroid_mm=_tuple3(row["deformed_centroid_mm"]), von_mises_mpa=float(row["von_mises_mpa"]),
        )
        for row in raw["elements"]
    )
    return VerifiedStressContourFieldV1(
        mesh_identity_sha256=str(raw["mesh_identity_sha256"]), solve_evidence_sha256=str(raw["solve_evidence_sha256"]),
        element_count=int(raw["element_count"]), stress_semantics=str(raw["stress_semantics"]),
        displacement_scale=float(raw["displacement_scale"]), stress_min_mpa=float(raw["stress_min_mpa"]),
        stress_max_mpa=float(raw["stress_max_mpa"]), displacement_max_mm=float(raw["displacement_max_mm"]), elements=rows,
    )


def _rebuild_stress(raw: Mapping[str, Any]) -> AdaptiveStressComparisonV1:
    view = AdaptiveStressComparisonV1(
        schema=str(raw["schema"]), semantics=str(raw["semantics"]), status=str(raw["status"]),
        baseline=_rebuild_field(raw["baseline"]), refined=_rebuild_field(raw["refined"]),
        common_scale_min_mpa=float(raw["common_scale_min_mpa"]), common_scale_max_mpa=float(raw["common_scale_max_mpa"]),
        baseline_peak_mpa=float(raw["baseline_peak_mpa"]), refined_peak_mpa=float(raw["refined_peak_mpa"]),
        peak_relative_change=float(raw["peak_relative_change"]), qoi_status=str(raw["qoi_status"]),
        qoi_relative_change=float(raw["qoi_relative_change"]), indicator_status=str(raw["indicator_status"]),
        indicator_relative_change=float(raw["indicator_relative_change"]), claims=dict(raw["claims"]),
        comparison_sha256=str(raw["comparison_sha256"]),
    )
    verify_adaptive_stress_comparison(view)
    return view


def _load_payload(data: bytes) -> Mapping[str, np.ndarray]:
    expected = {
        "baseline_nodes_mm", "baseline_elements", "baseline_displacement_mm", "baseline_reactions_n",
        "baseline_ip_stress_mpa", "baseline_ip_von_mises_mpa", "refined_nodes_mm", "refined_elements",
        "refined_displacement_mm", "refined_reactions_n", "refined_ip_stress_mpa", "refined_ip_von_mises_mpa",
    }
    with np.load(BytesIO(data), allow_pickle=False) as archive:
        if set(archive.files) != expected:
            raise PortableAdaptiveResultsError("PORTABLE_RESULTS_PAYLOAD_INVENTORY")
        arrays: dict[str, np.ndarray] = {}
        for name in sorted(expected):
            value = np.array(archive[name], copy=True)
            if value.dtype.kind in {"f", "c"} and not np.all(np.isfinite(value)):
                raise PortableAdaptiveResultsError("PORTABLE_RESULTS_NONFINITE_PAYLOAD")
            value.setflags(write=False)
            arrays[name] = value
    return MappingProxyType(arrays)


def open_portable_adaptive_results_package(path: str | Path) -> PortableAdaptiveResultsPackageV1:
    package_path = Path(path)
    if package_path.suffix.lower() != ".astermaxr" or not package_path.is_file():
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_FILE_REQUIRED")
    try:
        with ZipFile(package_path, "r") as archive:
            if set(archive.namelist()) != {"manifest.json", "views.json", "results.npz"}:
                raise PortableAdaptiveResultsError("PORTABLE_RESULTS_ARCHIVE_INVENTORY")
            manifest_bytes = archive.read("manifest.json")
            views_bytes = archive.read("views.json")
            payload_bytes = archive.read("results.npz")
    except BadZipFile as exc:
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_BAD_ARCHIVE") from exc

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        views = json.loads(views_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_JSON") from exc
    if manifest.get("schema") != "AsterMaxPortableAdaptiveResultsManifestV1":
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_MANIFEST_SCHEMA")
    manifest_core = dict(manifest); manifest_sha = str(manifest_core.pop("manifest_sha256", ""))
    if canonical_sha256(manifest_core) != manifest_sha:
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_MANIFEST_TAMPERED")
    payload_sha = _sha256_bytes(payload_bytes)
    views_sha = _sha256_bytes(views_bytes)
    if payload_sha != manifest.get("payload_sha256"):
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_PAYLOAD_TAMPERED")
    if views_sha != manifest.get("views_sha256"):
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_VIEWS_TAMPERED")
    if manifest.get("solver_required_to_open") or manifest.get("gmsh_required_to_open"):
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_REOPEN_DEPENDENCY_OVERCLAIM")
    if manifest.get("global_analysis_converged") or manifest.get("industrial_validation") or manifest.get("ansys_equivalence"):
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_VALIDATION_OVERCLAIM")

    hotspot = _rebuild_hotspot(views["hotspot_view"])
    stress = _rebuild_stress(views["stress_view"])
    if hotspot.visualization_sha256 != manifest.get("hotspot_visualization_sha256") or stress.comparison_sha256 != manifest.get("stress_comparison_sha256"):
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_VIEW_PROVENANCE")
    if hotspot.baseline_mesh_sha256 != manifest.get("baseline_mesh_sha256") or hotspot.refined_mesh_sha256 != manifest.get("refined_mesh_sha256"):
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_MESH_PROVENANCE")
    if stress.baseline.solve_evidence_sha256 != manifest.get("baseline_solve_evidence_sha256") or stress.refined.solve_evidence_sha256 != manifest.get("refined_solve_evidence_sha256"):
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_SOLVE_PROVENANCE")

    arrays = _load_payload(payload_bytes)
    if arrays["baseline_nodes_mm"].shape[0] != arrays["baseline_displacement_mm"].shape[0]:
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_BASELINE_NODE_RESULT_ALIGNMENT")
    if arrays["refined_nodes_mm"].shape[0] != arrays["refined_displacement_mm"].shape[0]:
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_REFINED_NODE_RESULT_ALIGNMENT")
    if arrays["baseline_elements"].shape[0] != stress.baseline.element_count or arrays["refined_elements"].shape[0] != stress.refined.element_count:
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_ELEMENT_ALIGNMENT")

    claims = {
        "reopened_without_solver": True,
        "reopened_without_gmsh": True,
        "binary_result_payload_verified": True,
        "native_views_restored_from_verified_package": True,
        "global_analysis_converged": False,
        "industrial_validation": False,
        "ansys_equivalence": False,
    }
    core = {
        "schema": "AsterMaxPortableAdaptiveResultsPackageV1", "status": "READY",
        "source_bundle_sha256": str(manifest["source_bundle_sha256"]), "source_step_sha256": str(manifest["source_step_sha256"]),
        "baseline_mesh_sha256": str(manifest["baseline_mesh_sha256"]), "refined_mesh_sha256": str(manifest["refined_mesh_sha256"]),
        "baseline_solve_evidence_sha256": str(manifest["baseline_solve_evidence_sha256"]),
        "refined_solve_evidence_sha256": str(manifest["refined_solve_evidence_sha256"]),
        "payload_sha256": payload_sha, "views_sha256": views_sha, "manifest_sha256": manifest_sha, "claims": claims,
    }
    return PortableAdaptiveResultsPackageV1(
        **core, package_path=str(package_path), package_file_sha256=_sha256_file(package_path), payload_arrays=arrays,
        hotspot_view=hotspot, stress_view=stress, package_sha256=canonical_sha256(core),
    )


def verify_portable_adaptive_results_package(package: PortableAdaptiveResultsPackageV1) -> None:
    if package.schema != "AsterMaxPortableAdaptiveResultsPackageV1" or package.status != "READY":
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_SCHEMA_STATUS")
    if package.claims.get("global_analysis_converged") or package.claims.get("industrial_validation") or package.claims.get("ansys_equivalence"):
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_VALIDATION_OVERCLAIM")
    path = Path(package.package_path)
    if not path.is_file() or _sha256_file(path) != package.package_file_sha256:
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_PACKAGE_FILE_CHANGED")
    reopened = open_portable_adaptive_results_package(path)
    if reopened.package_sha256 != package.package_sha256 or reopened.payload_sha256 != package.payload_sha256:
        raise PortableAdaptiveResultsError("PORTABLE_RESULTS_REOPEN_MISMATCH")


def bind_portable_adaptive_results(
    package: PortableAdaptiveResultsPackageV1,
    *,
    hotspot_binder: Callable[[AdaptiveHotspotVisualizationV1], None],
    stress_binder: Callable[[AdaptiveStressComparisonV1], None],
) -> PortableAdaptiveResultsBindingReceiptV1:
    verify_portable_adaptive_results_package(package)
    hotspot_binder(package.hotspot_view)
    stress_binder(package.stress_view)
    core = {
        "schema": "AsterMaxPortableAdaptiveResultsBindingReceiptV1",
        "package_sha256": package.package_sha256,
        "bound_tabs": ("Adaptive Hotspots", "Stress Compare"),
        "hotspot_visualization_sha256": package.hotspot_view.visualization_sha256,
        "stress_comparison_sha256": package.stress_view.comparison_sha256,
    }
    return PortableAdaptiveResultsBindingReceiptV1(**core, receipt_sha256=canonical_sha256(core))
