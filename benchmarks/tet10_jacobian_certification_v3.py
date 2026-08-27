from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from astermax.fea.tet10_jacobian_adaptive import tet10_adaptive_jacobian_report
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

    v2_fail = 0
    v3_fail = 0
    v2_fail_v3_pass = 0
    v2_pass_v3_fail = 0
    evaluated_points: list[int] = []
    examples: list[dict] = []

    for fixture_index in range(fixture_count):
        coords = BASE.copy()
        coords[4:] += rng.normal(size=(6, 3)) * midside_sigma
        v2 = tet10_reference_jacobian_report(coords, elements)
        v3 = tet10_adaptive_jacobian_report(coords, elements)
        evaluated_points.append(v3.evaluated_points)
        if v2.status == "FAIL":
            v2_fail += 1
        if v3.status == "FAIL":
            v3_fail += 1
        if v2.status == "FAIL" and v3.status == "PASS":
            v2_fail_v3_pass += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "fixture_index": fixture_index,
                        "class": "V2_FAIL_V3_PASS",
                        "v2_minimum_determinant": v2.minimum_determinant,
                        "v3_minimum_determinant": v3.minimum_determinant,
                    }
                )
        if v2.status == "PASS" and v3.status == "FAIL":
            v2_pass_v3_fail += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "fixture_index": fixture_index,
                        "class": "V2_PASS_V3_FAIL",
                        "v2_minimum_determinant": v2.minimum_determinant,
                        "v3_minimum_determinant": v3.minimum_determinant,
                        "v3_worst_natural_coordinates": v3.worst_natural_coordinates,
                    }
                )

    decision = {
        "schema": "AsterMaxTet10JacobianCertificationV3",
        "seed": seed,
        "fixture_count": fixture_count,
        "midside_gaussian_sigma_reference_edge": midside_sigma,
        "v2_reference_fail_count": v2_fail,
        "v3_adaptive_fail_count": v3_fail,
        "v2_fail_v3_pass_count": v2_fail_v3_pass,
        "v2_pass_v3_fail_count": v2_pass_v3_fail,
        "v3_evaluated_points_min": min(evaluated_points),
        "v3_evaluated_points_max": max(evaluated_points),
        "v3_evaluated_points_mean": float(np.mean(evaluated_points)),
        "v3_is_global_positivity_proof": False,
        "curved_tet10_solver_enabled": False,
        "examples": examples,
        "decision": (
            "KEEP_V2_AS_FAIL_CLOSED_AUTHORITY_AND_EVALUATE_V3_AS_DIAGNOSTIC"
            if v2_fail_v3_pass > 0
            else "V3_MATCHES_OR_EXCEEDS_V2_ON_DECLARED_ADVERSARIAL_SET_BUT_IS_NOT_A_GLOBAL_PROOF"
        ),
    }
    Path("tet10_jacobian_certification_v3.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
