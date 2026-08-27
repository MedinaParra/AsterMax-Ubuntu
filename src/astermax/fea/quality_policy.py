from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TetraQualityPolicy:
    warn_scaled_jacobian: float = 0.20
    fail_scaled_jacobian: float = 0.05
    warn_mean_ratio: float = 0.20
    fail_mean_ratio: float = 0.05
    warn_edge_aspect_ratio: float = 8.0
    fail_edge_aspect_ratio: float = 20.0
    determinant_epsilon: float = 1.0e-14

    def validate(self) -> None:
        if not (0.0 < self.fail_scaled_jacobian <= self.warn_scaled_jacobian <= 1.0):
            raise ValueError("scaled-Jacobian thresholds must satisfy 0 < fail <= warn <= 1")
        if not (0.0 < self.fail_mean_ratio <= self.warn_mean_ratio <= 1.0):
            raise ValueError("mean-ratio thresholds must satisfy 0 < fail <= warn <= 1")
        if not (1.0 <= self.warn_edge_aspect_ratio <= self.fail_edge_aspect_ratio):
            raise ValueError("aspect thresholds must satisfy 1 <= warn <= fail")
        if self.determinant_epsilon <= 0.0:
            raise ValueError("determinant_epsilon must be positive")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


DEFAULT_TETRA_QUALITY_POLICY = TetraQualityPolicy()
