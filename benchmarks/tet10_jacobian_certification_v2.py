from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from astermax.fea.tet10_jacobian import tet10_sampled_jacobian_report
from astermax.fea.tet10_jacobian_reference import tet10_reference_jacobian_report


BASE = np.asarray(
    [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.5, 0.0, 0.0],
        [0.5, 0.5, 0.0],
        [0.0, 0.5, 0.0],
        [0.0, 0.0, 0.5],
        [0.0, 0.5, 0.5],
        [0.5, 0.0, 0.5],
    ],
    dtype=float,
)


def main() -> int:
    seed = 12345
    fixture_count = 500
    midside_sigma = 0.10
    rng = np.random.default_rng(seed)
    elements = np.arange(10, dtype=np.int64)[None, :]

    v1_pass = 0
    reference_fail = 0
    v1_false_negative = 0
    examples: list[dict] = []
    for fixture_index in range(fixture_count):
        coords = BASE.copy()
        coords[4:] += rng.normal(size=(6, 3)) * midside_sigma
        v1 = tet10_sampled_jacobian_report(coords, elements)
        reference = tet10_reference_jacobian_report(coords, elements)
        if v1.status == "PASS":
            v1_pass += 1
        if reference.status == "FAIL":
            reference_fail += 1
        if v1.status == "PASS" and reference.status == "FAIL":
            v1_false_negative += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "fixture_index": fixture_index,
                        "v1_minimum_determinant": v1.minimum_determinant,
                        "reference_minimum_determinant": reference.minimum_determinant,
                        "reference_worst_natural_coordinates": reference.worst_natural_coordinates,
                    }
                )

    decision = {
        "schema": "AsterMaxTet10JacobianCertificationV2",
        "seed": seed,
        "fixture_count": fixture_count,
        "midside_gaussian_sigma_reference_edge": midside_sigma,
        "v1_sample_count": 15,
        "reference_sample_count": 286,
        "v1_pass_count": v1_pass,
        "reference_fail_count": reference_fail,
        "v1_false_negative_count": v1_false_negative,
        "v1_false_negative_rate_of_all_fixtures": v1_false_negative / fixture_count,
        "v1_false_negative_rate_conditioned_on_v1_pass": v1_false_negative / v1_pass if v1_pass else None,
        "known_blind_spot_reproduced": v1_false_negative > 0,
        "v1_sufficient_for_curved_tet10_admission": False,
        "reference_is_global_positivity_proof": False,
        "curved_tet10_solver_enabled": False,
        "examples": examples,
        "decision": "KEEP_CURVED_TET10_DISABLED_AND_REQUIRE_DENSE_REFERENCE_SCAN",
    }
    Path("tet10_jacobian_certification_v2.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(decision, indent=2, sort_keys=True))
    if v1_false_negative <= 0:
        raise RuntimeError("adversarial harness failed to reproduce the declared V1 Jacobian blind spot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
