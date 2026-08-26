from __future__ import annotations

import argparse
import json
from pathlib import Path

from astermax.domain.hub_sprocket import HubSprocketBaselineV1
from astermax.geometry.step_intake import (
    build_gap_sensitivity,
    evaluate_geometry_preparation,
    inspect_local_step,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect the local OT1613 STEP without uploading CAD bytes and emit "
            "a fail-closed geometry-preparation report."
        )
    )
    parser.add_argument("step", type=Path)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("examples/hub_sprocket/ot1613_baseline.json"),
    )
    args = parser.parse_args()

    baseline = HubSprocketBaselineV1.model_validate_json(
        args.baseline.read_text(encoding="utf-8")
    )
    inspection = inspect_local_step(
        args.step,
        expected_sha256=baseline.geometry.sha256,
        expected_byte_size=baseline.geometry.byte_size,
        hub_solid_index_1based=baseline.geometry.hub_solid_index_1based,
        segment_solid_indices_1based=baseline.geometry.segment_solid_indices_1based,
    )
    scenarios = build_gap_sensitivity(
        baseline.measured_gap.minimum_mm,
        baseline.measured_gap.maximum_mm,
        source_id=baseline.measured_gap.source_ids[0],
    )
    preparation = evaluate_geometry_preparation(
        inspection,
        scenarios,
        test_flange_diameter_mm=baseline.measured_gap.test_flange_diameter_mm,
    )

    payload = {
        "inspection": inspection.model_dump(mode="json"),
        "geometry_preparation": preparation.model_dump(mode="json"),
        "physical_test_flange_diameter_mm": baseline.measured_gap.test_flange_diameter_mm,
        "cad_bytes_uploaded": False,
        "authentic_fea_result_claimed": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
