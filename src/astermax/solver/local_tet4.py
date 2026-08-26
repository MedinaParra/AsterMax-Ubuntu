from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class IsotropicMaterialV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="IsotropicMaterialV1", pattern=r"^IsotropicMaterialV1$"
    )
    elastic_modulus_mpa: float = Field(gt=0)
    poisson_ratio: float = Field(ge=0, lt=0.5)


@dataclass(frozen=True)
class Tet4Kinematics:
    b_matrix: np.ndarray
    volume_mm3: float


@dataclass(frozen=True)
class NormalPenaltyContact:
    stiffness_n_per_mm: float
    gap_mm: float

    def matrix_and_rhs(self) -> tuple[np.ndarray, np.ndarray]:
        if self.stiffness_n_per_mm <= 0:
            raise ValueError("contact stiffness must be positive")
        if self.gap_mm < 0:
            raise ValueError("contact gap cannot be negative")
        k = self.stiffness_n_per_mm
        matrix = np.array([[k, -k], [-k, k]], dtype=float)
        rhs = np.array([k * self.gap_mm, -k * self.gap_mm], dtype=float)
        return matrix, rhs

    def penetration_mm(self, segment_ux_mm: float, hub_ux_mm: float) -> float:
        return max(segment_ux_mm - hub_ux_mm - self.gap_mm, 0.0)

    def force_n(self, segment_ux_mm: float, hub_ux_mm: float) -> float:
        return self.stiffness_n_per_mm * self.penetration_mm(
            segment_ux_mm, hub_ux_mm
        )


def elasticity_matrix(material: IsotropicMaterialV1) -> np.ndarray:
    e = material.elastic_modulus_mpa
    nu = material.poisson_ratio
    lam = e * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = e / (2.0 * (1.0 + nu))
    return np.array(
        [
            [lam + 2 * mu, lam, lam, 0, 0, 0],
            [lam, lam + 2 * mu, lam, 0, 0, 0],
            [lam, lam, lam + 2 * mu, 0, 0, 0],
            [0, 0, 0, mu, 0, 0],
            [0, 0, 0, 0, mu, 0],
            [0, 0, 0, 0, 0, mu],
        ],
        dtype=float,
    )


def tet4_kinematics(coordinates_mm: np.ndarray) -> Tet4Kinematics:
    coordinates = np.asarray(coordinates_mm, dtype=float)
    if coordinates.shape != (4, 3):
        raise ValueError("Tet4 coordinates must have shape (4, 3)")

    interpolation = np.ones((4, 4), dtype=float)
    interpolation[:, 1:] = coordinates
    determinant = float(np.linalg.det(interpolation))
    volume = determinant / 6.0
    if not np.isfinite(volume) or volume <= 1e-12:
        raise ValueError("Tet4 must be positively oriented and non-degenerate")

    inverse = np.linalg.inv(interpolation)
    gradients = inverse[1:, :]
    b = np.zeros((6, 12), dtype=float)
    for node_index in range(4):
        bx, by, bz = gradients[:, node_index]
        column = 3 * node_index
        b[0, column] = bx
        b[1, column + 1] = by
        b[2, column + 2] = bz
        b[3, column] = by
        b[3, column + 1] = bx
        b[4, column + 1] = bz
        b[4, column + 2] = by
        b[5, column] = bz
        b[5, column + 2] = bx

    return Tet4Kinematics(b_matrix=b, volume_mm3=volume)


def tet4_stiffness(
    coordinates_mm: np.ndarray, material: IsotropicMaterialV1
) -> np.ndarray:
    kin = tet4_kinematics(coordinates_mm)
    constitutive = elasticity_matrix(material)
    stiffness = (
        kin.b_matrix.T @ constitutive @ kin.b_matrix * kin.volume_mm3
    )
    return 0.5 * (stiffness + stiffness.T)


def tet4_stress_mpa(
    coordinates_mm: np.ndarray,
    displacement_mm: np.ndarray,
    material: IsotropicMaterialV1,
) -> np.ndarray:
    displacement = np.asarray(displacement_mm, dtype=float)
    if displacement.shape == (4, 3):
        displacement = displacement.reshape(12)
    if displacement.shape != (12,):
        raise ValueError("Tet4 displacement must have shape (4, 3) or (12,)")
    kin = tet4_kinematics(coordinates_mm)
    return elasticity_matrix(material) @ (kin.b_matrix @ displacement)


def von_mises_mpa(stress_mpa: np.ndarray) -> float:
    stress = np.asarray(stress_mpa, dtype=float)
    if stress.shape != (6,):
        raise ValueError("stress must have six components [xx, yy, zz, xy, yz, zx]")
    sx, sy, sz, txy, tyz, tzx = stress
    value = 0.5 * (
        (sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2
    ) + 3.0 * (txy**2 + tyz**2 + tzx**2)
    return float(np.sqrt(max(value, 0.0)))
