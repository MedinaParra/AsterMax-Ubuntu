from __future__ import annotations

import json as std_json
from typing import Any

import numpy as np

import curved_tet10_solver_verification as benchmark
from astermax.credibility import canonical_sha256 as canonical_sha256_native


def json_native(value: Any) -> Any:
    """Convert NumPy scalar leaves to deterministic JSON-native values only.

    This runner is intentionally instrumentation-only: it does not alter C11
    geometry, quadrature, solver, loads, thresholds, checks or claim policy.
    Arrays are not accepted into reports here; C11 hashes those separately.
    """
    if isinstance(value, np.generic):
        return json_native(value.item())
    if isinstance(value, dict):
        return {str(key): json_native(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_native(item) for item in value]
    if isinstance(value, tuple):
        return [json_native(item) for item in value]
    return value


class _JsonProxy:
    @staticmethod
    def dumps(value: Any, **kwargs: Any) -> str:
        return std_json.dumps(json_native(value), **kwargs)


def _canonical_sha256(value: Any) -> str:
    return canonical_sha256_native(json_native(value))


def main() -> int:
    # The original benchmark bound these names at import time. Replace only its
    # evidence serializers so NumPy booleans/floats become standard JSON leaves.
    benchmark.json = _JsonProxy
    benchmark.canonical_sha256 = _canonical_sha256
    return benchmark.main()


if __name__ == "__main__":
    raise SystemExit(main())
