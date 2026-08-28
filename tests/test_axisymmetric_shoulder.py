import pytest

from astermax.fea.axisymmetric_shoulder import (
    AxisymmetricFaceObservation,
    ShaftShoulderRecognitionError,
    recognize_x_axis_shoulder_from_observations,
)


def _face(tag, kind, bbox):
    return AxisymmetricFaceObservation(
        tag=tag,
        surface_type=kind,
        bbox_mm=tuple(float(v) for v in bbox),
        center_mm=(
            0.5 * (bbox[0] + bbox[3]),
            0.5 * (bbox[1] + bbox[4]),
            0.5 * (bbox[2] + bbox[5]),
        ),
    )


def _standard_faces():
    return (
        _face(1, "Plane", (0, -10, -10, 0, 10, 10)),
        _face(2, "Cylinder", (0, -10, -10, 38, 10, 10)),
        _face(3, "Surface of Revolution", (38, -12, -12, 40, 12, 12)),
        _face(4, "Plane", (40, -15, -15, 40, 15, 15)),
        _face(5, "Cylinder", (40, -15, -15, 80, 15, 15)),
        _face(6, "Plane", (80, -15, -15, 80, 15, 15)),
    )


def _recognize(faces):
    return recognize_x_axis_shoulder_from_observations(
        faces,
        feature_id="S1",
        source_name="fixture.step",
        source_sha256="a" * 64,
        source_size_bytes=1234,
        gmsh_version="verification",
        model_bbox_mm=(0.0, -15.0, -15.0, 80.0, 15.0, 15.0),
    )


def test_recognizes_one_x_axis_filleted_shoulder_and_infers_radius():
    feature = _recognize(_standard_faces())
    assert feature.small_cylinder_tag == 2
    assert feature.large_cylinder_tag == 5
    assert feature.transition_face_tag == 3
    assert feature.shoulder_plane_tag == 4
    assert feature.small_radius_mm == pytest.approx(10.0)
    assert feature.large_radius_mm == pytest.approx(15.0)
    assert feature.fillet_radius_mm == pytest.approx(2.0)
    assert feature.transition_x_mm == pytest.approx(40.0)
    assert feature.small_side == "X_MIN_SIDE"
    assert len(feature.feature_sha256) == 64


def test_transition_ambiguity_fails_closed():
    faces = _standard_faces() + (
        _face(7, "Torus", (38, -11.5, -11.5, 40, 11.5, 11.5)),
    )
    with pytest.raises(ShaftShoulderRecognitionError, match="TRANSITION_FACE_AMBIGUOUS"):
        _recognize(faces)


def test_fillet_radius_larger_than_radial_step_is_rejected():
    faces = list(_standard_faces())
    faces[1] = _face(2, "Cylinder", (0, -10, -10, 30, 10, 10))
    faces[2] = _face(3, "Surface of Revolution", (30, -12, -12, 40, 12, 12))
    with pytest.raises(ShaftShoulderRecognitionError, match="FILLET_RADIUS_EXCEEDS_RADIAL_STEP"):
        _recognize(tuple(faces))


def test_extra_coaxial_cylinder_is_outside_declared_scope():
    faces = _standard_faces() + (
        _face(8, "Cylinder", (80, -8, -8, 100, 8, 8)),
    )
    with pytest.raises(ShaftShoulderRecognitionError, match="EXPECTED_EXACTLY_TWO_COAXIAL_CYLINDERS"):
        recognize_x_axis_shoulder_from_observations(
            faces,
            feature_id="S1",
            source_name="fixture.step",
            source_sha256="b" * 64,
            source_size_bytes=1234,
            gmsh_version="verification",
            model_bbox_mm=(0.0, -15.0, -15.0, 100.0, 15.0, 15.0),
        )
