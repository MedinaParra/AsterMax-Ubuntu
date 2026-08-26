from __future__ import annotations

import argparse
import json
from pathlib import Path

from astermax.domain.hub_sprocket import HubSprocketBaselineV1
from astermax.geometry.planar_gap import (
    generate_local_gap_variants,
    identify_planar_mounting_interface,
)
from astermax.geometry.step_intake import build_gap_sensitivity


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate local posterior-planar GAP variants from the authenticated "
            "hub/sprocket STEP without committing CAD bytes."
        )
    )
    parser.add_argument("step", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("examples/hub_sprocket/ot1613_baseline.json"),
    )
    args = parser.parse_args()

    baseline = HubSprocketBaselineV1.model_validate_json(
        args.baseline.read_text(encoding="utf-8")
    )
    interface = identify_planar_mounting_interface(
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
    manifest = generate_local_gap_variants(
        args.step,
        args.output_directory,
        interface=interface,
        scenarios=scenarios,
        segment_solid_indices_1based=baseline.geometry.segment_solid_indices_1based,
    )
    manifest_path = args.output_directory / "gap_variant_manifest.json"
    manifest_path.write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
