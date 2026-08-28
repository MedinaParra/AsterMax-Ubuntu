from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from astermax.credibility import canonical_sha256
from .evidence import sha256_file
from .gmsh_bridge import GmshBridgeError, _gmsh


class ShaftShoulderRecognitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class AxisymmetricFaceObservation:
    tag: int
    surface_type: str
    bbox_mm: tuple[float, float, float, float, float, float]
    center_mm: tuple[float, float, float]

    def canonical(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class XAxisShoulderFeature:
    feature_id: str
    source_name: str
    source_sha256: str
    source_size_bytes: int
    gmsh_version: str
    recognition_scope: str
    small_cylinder_tag: int
    large_cylinder_tag: int
    transition_face_tag: int
    shoulder_plane_tag: int
    small_radius_mm: float
    large_radius_mm: float
    fillet_radius_mm: float
    transition_x_mm: float
    small_side: str
    axis_center_yz_mm: tuple[float, float]
    transition_bbox_mm: tuple[float, float, float, float, float, float]
    feature_sha256: str

    def canonical_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("feature_sha256")
        return payload


@dataclass(frozen=True)
class _CylinderCandidate:
    face: AxisymmetricFaceObservation
    radius_mm: float
    x_min_mm: float
    x_max_mm: float


def _step(path: str | Path) -> Path:
    p = Path(path)
    if p.suffix.lower() not in {".step", ".stp"} or not p.is_file():
        raise GmshBridgeError("shaft shoulder recognition input must be an existing STEP/STP file")
    return p


def _close(a: float, b: float, scale: float, rel: float) -> bool:
    atol = max(abs(scale) * rel, np.finfo(float).eps * max(abs(scale), 1.0) * 64.0)
    return abs(float(a) - float(b)) <= max(atol, max(abs(float(a)), abs(float(b))) * rel)


def _span(box: tuple[float, ...], axis: int) -> float:
    return float(box[axis + 3] - box[axis])


def _mid(box: tuple[float, ...], axis: int) -> float:
    return 0.5 * float(box[axis + 3] + box[axis])


def _surface_kind(value: str) -> str:
    return str(value).strip().lower().replace(" ", "_")


def _cylinders(
    observations: Iterable[AxisymmetricFaceObservation],
    *,
    axis_center_yz_mm: tuple[float, float],
    model_diagonal_mm: float,
    relative_tolerance: float,
) -> tuple[_CylinderCandidate, ...]:
    out: list[_CylinderCandidate] = []
    cy, cz = axis_center_yz_mm
    for face in observations:
        if "cylinder" not in _surface_kind(face.surface_type):
            continue
        box = face.bbox_mm
        x_span = _span(box, 0)
        y_span = _span(box, 1)
        z_span = _span(box, 2)
        if x_span <= model_diagonal_mm * relative_tolerance:
            continue
        if y_span <= 0.0 or z_span <= 0.0:
            continue
        radial_scale = max(y_span, z_span, 1.0)
        if not _close(y_span, z_span, radial_scale, relative_tolerance * 100.0):
            continue
        if not _close(_mid(box, 1), cy, model_diagonal_mm, relative_tolerance * 100.0):
            continue
        if not _close(_mid(box, 2), cz, model_diagonal_mm, relative_tolerance * 100.0):
            continue
        radius = 0.25 * (y_span + z_span)
        if radius <= 0.0 or not np.isfinite(radius):
            continue
        out.append(_CylinderCandidate(face, radius, float(box[0]), float(box[3])))
    return tuple(out)


def _plane_at_x(
    observations: Iterable[AxisymmetricFaceObservation],
    x_mm: float,
    *,
    axis_center_yz_mm: tuple[float, float],
    model_diagonal_mm: float,
    relative_tolerance: float,
) -> tuple[AxisymmetricFaceObservation, ...]:
    cy, cz = axis_center_yz_mm
    matches = []
    for face in observations:
        if _surface_kind(face.surface_type) != "plane":
            continue
        box = face.bbox_mm
        if _span(box, 0) > model_diagonal_mm * relative_tolerance * 100.0:
            continue
        if not _close(_mid(box, 0), x_mm, model_diagonal_mm, relative_tolerance * 100.0):
            continue
        if not _close(_mid(box, 1), cy, model_diagonal_mm, relative_tolerance * 100.0):
            continue
        if not _close(_mid(box, 2), cz, model_diagonal_mm, relative_tolerance * 100.0):
            continue
        matches.append(face)
    return tuple(matches)


def _transition_faces(
    observations: Iterable[AxisymmetricFaceObservation],
    x0_mm: float,
    x1_mm: float,
    *,
    axis_center_yz_mm: tuple[float, float],
    small_radius_mm: float,
    large_radius_mm: float,
    model_diagonal_mm: float,
    relative_tolerance: float,
) -> tuple[AxisymmetricFaceObservation, ...]:
    lo, hi = sorted((float(x0_mm), float(x1_mm)))
    cy, cz = axis_center_yz_mm
    matches = []
    for face in observations:
        kind = _surface_kind(face.surface_type)
        if kind == "plane" or "cylinder" in kind:
            continue
        box = face.bbox_mm
        tol = model_diagonal_mm * relative_tolerance * 100.0
        if float(box[0]) > lo + tol or float(box[3]) < hi - tol:
            continue
        if not _close(_mid(box, 1), cy, model_diagonal_mm, relative_tolerance * 200.0):
            continue
        if not _close(_mid(box, 2), cz, model_diagonal_mm, relative_tolerance * 200.0):
            continue
        radial_extent = 0.25 * (_span(box, 1) + _span(box, 2))
        if radial_extent <= small_radius_mm or radial_extent >= large_radius_mm + tol:
            continue
        matches.append(face)
    return tuple(matches)


def recognize_x_axis_shoulder_from_observations(
    observations: Iterable[AxisymmetricFaceObservation],
    *,
    feature_id: str,
    source_name: str,
    source_sha256: str,
    source_size_bytes: int,
    gmsh_version: str,
    model_bbox_mm: tuple[float, float, float, float, float, float],
    relative_tolerance: float = 1.0e-7,
) -> XAxisShoulderFeature:
    """Recognize one standard filleted shaft shoulder in a deliberately narrow scope.

    Certified scope: one X-aligned axisymmetric stepped shaft, two full coaxial
    cylindrical lateral faces, one quarter-round transition and one radial
    shoulder plane. The fillet radius is inferred from the axial distance
    between the small-cylinder tangent and the radial shoulder plane. Anything
    ambiguous or outside this topology fails closed.
    """
    faces = tuple(observations)
    fid = str(feature_id).strip()
    if not fid or any(ch.isspace() for ch in fid):
        raise ValueError("feature_id must be non-empty and contain no whitespace")
    if len(source_sha256) != 64:
        raise ValueError("source_sha256 must be a SHA-256 hex digest")
    if source_size_bytes <= 0:
        raise ValueError("source_size_bytes must be positive")
    if not np.isfinite(relative_tolerance) or not (0.0 < relative_tolerance <= 1.0e-3):
        raise ValueError("relative_tolerance must be finite and in (0, 1e-3]")

    bbox = tuple(float(v) for v in model_bbox_mm)
    dims = np.asarray((bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]), dtype=float)
    if np.any(dims <= 0.0) or not np.all(np.isfinite(dims)):
        raise ShaftShoulderRecognitionError("INVALID_MODEL_BBOX")
    diagonal = float(np.linalg.norm(dims))
    axis_center = (_mid(bbox, 1), _mid(bbox, 2))
    cylinders = _cylinders(
        faces,
        axis_center_yz_mm=axis_center,
        model_diagonal_mm=diagonal,
        relative_tolerance=relative_tolerance,
    )
    if len(cylinders) != 2:
        raise ShaftShoulderRecognitionError(f"EXPECTED_EXACTLY_TWO_COAXIAL_CYLINDERS:{len(cylinders)}")

    small, large = sorted(cylinders, key=lambda item: item.radius_mm)
    radial_step = large.radius_mm - small.radius_mm
    if radial_step <= diagonal * relative_tolerance:
        raise ShaftShoulderRecognitionError("CYLINDER_RADII_NOT_DISTINCT")

    tol = diagonal * relative_tolerance * 100.0
    if small.x_max_mm < large.x_min_mm - tol:
        small_side = "X_MIN_SIDE"
        small_tangent_x = small.x_max_mm
        transition_x = large.x_min_mm
    elif large.x_max_mm < small.x_min_mm - tol:
        small_side = "X_MAX_SIDE"
        small_tangent_x = small.x_min_mm
        transition_x = large.x_max_mm
    else:
        raise ShaftShoulderRecognitionError("CYLINDER_AXIAL_RANGES_OVERLAP_OR_TOUCH_WITHOUT_FILLET")

    fillet_radius = abs(transition_x - small_tangent_x)
    if fillet_radius <= tol:
        raise ShaftShoulderRecognitionError("ZERO_OR_UNRESOLVED_FILLET_RADIUS")
    if fillet_radius > radial_step + tol:
        raise ShaftShoulderRecognitionError("FILLET_RADIUS_EXCEEDS_RADIAL_STEP")

    planes = _plane_at_x(
        faces,
        transition_x,
        axis_center_yz_mm=axis_center,
        model_diagonal_mm=diagonal,
        relative_tolerance=relative_tolerance,
    )
    if len(planes) != 1:
        raise ShaftShoulderRecognitionError("SHOULDER_PLANE_AMBIGUOUS:" + ",".join(str(f.tag) for f in planes))

    transitions = _transition_faces(
        faces,
        small_tangent_x,
        transition_x,
        axis_center_yz_mm=axis_center,
        small_radius_mm=small.radius_mm,
        large_radius_mm=large.radius_mm,
        model_diagonal_mm=diagonal,
        relative_tolerance=relative_tolerance,
    )
    if len(transitions) != 1:
        raise ShaftShoulderRecognitionError("TRANSITION_FACE_AMBIGUOUS:" + ",".join(str(f.tag) for f in transitions))
    transition = transitions[0]

    payload = {
        "schema": "AsterMaxXAxisShoulderFeatureV1",
        "feature_id": fid,
        "source_name": str(source_name),
        "source_sha256": str(source_sha256).lower(),
        "source_size_bytes": int(source_size_bytes),
        "gmsh_version": str(gmsh_version),
        "recognition_scope": "ONE_X_ALIGNED_FILLETED_AXISYMMETRIC_SHOULDER_TWO_COAXIAL_CYLINDERS",
        "small_cylinder_tag": small.face.tag,
        "large_cylinder_tag": large.face.tag,
        "transition_face_tag": transition.tag,
        "shoulder_plane_tag": planes[0].tag,
        "small_radius_mm": small.radius_mm,
        "large_radius_mm": large.radius_mm,
        "fillet_radius_mm": fillet_radius,
        "transition_x_mm": transition_x,
        "small_side": small_side,
        "axis_center_yz_mm": axis_center,
        "transition_bbox_mm": transition.bbox_mm,
    }
    return XAxisShoulderFeature(**payload | {"feature_sha256": canonical_sha256(payload)})


def recognize_x_axis_shaft_shoulder(
    step_path: str | Path,
    *,
    feature_id: str = "SHAFT_SHOULDER_1",
    relative_tolerance: float = 1.0e-7,
) -> XAxisShoulderFeature:
    source = _step(step_path)
    gmsh = _gmsh(); gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("astermax_shaft_shoulder_recognition")
        gmsh.model.occ.importShapes(str(source))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise ShaftShoulderRecognitionError(f"EXPECTED_ONE_SOLID:{len(volumes)}")
        bbox = tuple(float(v) for v in gmsh.model.getBoundingBox(3, volumes[0][1]))
        observations = tuple(
            AxisymmetricFaceObservation(
                tag=int(tag),
                surface_type=str(gmsh.model.getType(2, int(tag))),
                bbox_mm=tuple(float(v) for v in gmsh.model.getBoundingBox(2, int(tag))),
                center_mm=tuple(float(v) for v in gmsh.model.occ.getCenterOfMass(2, int(tag))),
            )
            for _, tag in gmsh.model.getEntities(2)
        )
        return recognize_x_axis_shoulder_from_observations(
            observations,
            feature_id=feature_id,
            source_name=source.name,
            source_sha256=sha256_file(source),
            source_size_bytes=int(source.stat().st_size),
            gmsh_version=str(getattr(gmsh, "__version__", "unknown")),
            model_bbox_mm=bbox,
            relative_tolerance=relative_tolerance,
        )
    finally:
        gmsh.finalize()
