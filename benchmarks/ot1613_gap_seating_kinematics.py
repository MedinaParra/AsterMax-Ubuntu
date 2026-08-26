from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from astermax.geometry.seating_kinematics import (
    BoltHoleFit,
    CylindricalPadArc,
    GapBand,
    SeatingCompatibilityStatus,
    evaluate_seating_compatibility,
)


def main() -> int:
    # Geometry below is derived from the exact confidential STEP inspection;
    # CAD bytes are intentionally not part of this repository or CI fixture.
    pads = (
        CylindricalPadArc("PAD_A", 398.05, 26.898317, 33.710104),
        CylindricalPadArc("PAD_B", 398.05, -33.739793, -26.928006),
    )
    measured_gap = GapBand(0.10, 0.40)
    bolt_fit = BoltHoleFit(
        segment_hole_diameter_mm=24.5,
        hub_hole_diameter_mm=25.0,
        bolt_nominal_diameter_mm=22.225,  # 7/8 inch nominal major diameter
    )
    decision = evaluate_seating_compatibility(
        arcs=pads,
        flange_diameter_mm=796.87,
        gap_band=measured_gap,
        bolt_fit=bolt_fit,
    )

    payload = {
        "schema_version": "AsterMaxGapSeatingKinematicsEvidenceV1",
        "classification": "GEOMETRIC_KINEMATIC_SCREENING_NOT_CONTACT_FEA",
        "case": "OT1613_HUB_SPROCKET_TEST_FLANGE",
        "source_boundaries": {
            "cad_file_name": "CONJUNTO A MODELAR.stp",
            "cad_sha256": "ed305386f592943aaf4df6dbbca420808ec032c503e4e3456e15db0ecc19ca88",
            "cad_byte_size": 3117839,
            "cad_bytes_committed": False,
            "cad_unit": "mm",
            "pad_arc_geometry": "DERIVED_FROM_EXACT_LOCAL_CAD_INSPECTION",
            "flange_diameter_796_87_mm": "MEASURED_TEST_CONFIGURATION_FROM_SKM_ING_IT_001_REV3",
            "gap_0_10_to_0_40_mm": "MEASURED_ENDPOINT_RANGE_FROM_SKM_ING_IT_001_REV3",
            "segment_hole_24_5_mm": "ITM_REPORT_EVIDENCE",
            "hub_hole_25_0_mm": "HUB_DRAWING_REPORT_EVIDENCE",
            "bolt_7_8_14": "HARDWARE_EVIDENCE_FROM_PRELIMINARY_CALCULATION_MEMORY",
        },
        "inputs": {
            "pads": [asdict(pad) for pad in pads],
            "flange_diameter_mm": 796.87,
            "measured_gap_band_mm": [0.10, 0.40],
            "bolt_fit": asdict(bolt_fit),
        },
        "decision": asdict(decision),
        "engineering_interpretation": {
            "prior_concentric_only_rejection_is_valid": False,
            "reason": (
                "The segment is not constrained to remain concentric during seating. "
                "The measured test-flange configuration can be reconciled with the "
                "R398.05 CAD pad arcs by sub-millimetre outward segment translation "
                "that remains below the geometric fastener-clearance bound."
            ),
            "next_gate": "PARAMETERIZE_RIGID_SEGMENT_SEATING_POSES_THEN_BUILD_CONTACT_VERIFICATION_FIXTURE",
            "contact_fea_executed": False,
            "authentic_ot1613_fea_result_claimed": False,
            "industrial_validation_claimed": False,
        },
    }
    output = Path("ot1613_gap_seating_kinematics.json")
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))

    expected = SeatingCompatibilityStatus.KINEMATICALLY_COMPATIBLE_REQUIRES_CONTACT_FEA
    return 0 if decision.status == expected else 2


if __name__ == "__main__":
    raise SystemExit(main())
