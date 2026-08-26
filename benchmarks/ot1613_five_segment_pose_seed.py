from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from astermax.geometry.five_segment_poses import (
    FiveSegmentPoseStatus,
    SegmentSeatingPose,
    evaluate_five_segment_poses,
)
from astermax.geometry.seating_kinematics import BoltHoleFit, CylindricalPadArc, GapBand


def main() -> int:
    lower = 0.5830768898949259
    upper = 0.8800087156050722
    midpoint = 0.5 * (lower + upper)
    pads = (
        CylindricalPadArc("PAD_A", 398.05, 26.898317, 33.710104),
        CylindricalPadArc("PAD_B", 398.05, -33.739793, -26.928006),
    )
    gap_band = GapBand(0.10, 0.40)
    bolt_fit = BoltHoleFit(24.5, 25.0, 22.225)
    # Canonical normalized five-segment ring. Absolute assembly phase is not
    # required for a hub-centered radial contact preprocessor; 72-degree pitch is.
    deltas = (lower, 0.65, midpoint, 0.80, upper)
    poses = tuple(
        SegmentSeatingPose(f"S{i + 1}", 72.0 * i, delta)
        for i, delta in enumerate(deltas)
    )
    decision = evaluate_five_segment_poses(
        poses,
        arcs=pads,
        flange_radius_mm=796.87 / 2.0,
        gap_band=gap_band,
        bolt_fit=bolt_fit,
    )

    payload = {
        "schema_version": "AsterMaxFiveSegmentContactSeedEvidenceV1",
        "classification": "CONTACT_PREPROCESSING_KINEMATICS_NOT_FEA",
        "case": "OT1613_FIVE_SEGMENT_CANONICAL_SEATING_SEED",
        "source_boundaries": {
            "cad_file_name": "CONJUNTO A MODELAR.stp",
            "cad_sha256": "ed305386f592943aaf4df6dbbca420808ec032c503e4e3456e15db0ecc19ca88",
            "cad_bytes_committed": False,
            "pad_arc_geometry": "DERIVED_FROM_EXACT_LOCAL_CAD_INSPECTION",
            "five_segment_pitch_deg": 72.0,
            "absolute_ring_phase": "NORMALIZED_TO_ZERO_FOR_CONTACT_PREPROCESSING",
            "flange_diameter_mm": 796.87,
            "gap_evidence_mm": [0.10, 0.40],
            "segment_hole_diameter_mm": 24.5,
            "hub_hole_diameter_mm": 25.0,
            "bolt_nominal_diameter_mm": 22.225,
        },
        "pose_strategy": {
            "purpose": "SPAN_ADMISSIBLE_GAP_A_TRANSLATION_INTERVAL_WITH_FIVE_INDEPENDENT_SEGMENT_POSES",
            "translations_mm": list(deltas),
            "not_measured_individual_segment_positions": True,
            "do_not_relabel_as_field_measurement": True,
        },
        "inputs": {
            "pads": [asdict(pad) for pad in pads],
            "gap_band": asdict(gap_band),
            "bolt_fit": asdict(bolt_fit),
            "poses": [asdict(pose) for pose in poses],
        },
        "decision": asdict(decision),
        "engineering_interpretation": {
            "five_independent_segment_poses_parameterized": True,
            "contact_seed_points_generated": sum(
                len(check["contact_seed_points"]) for check in decision.segment_checks
            ),
            "contact_fea_executed": False,
            "preload_solved": False,
            "friction_solved": False,
            "torque_transfer_solved": False,
            "authentic_ot1613_fea_result_claimed": False,
            "industrial_validation_claimed": False,
            "next_gate": decision.next_gate,
        },
    }
    output = Path("ot1613_five_segment_pose_seed.json")
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    expected = FiveSegmentPoseStatus.CONTACT_READY_KINEMATICS_VALIDATED
    return 0 if decision.status == expected else 2


if __name__ == "__main__":
    raise SystemExit(main())
