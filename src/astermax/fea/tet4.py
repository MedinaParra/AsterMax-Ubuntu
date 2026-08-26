from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class IsotropicMaterial:
    young_modulus_mpa: float
    poisson_ratio: float

    def constitutive_matrix(self) -> np.ndarray:
        e = float(self.young_modulus_mpa)
        nu = float(self.poisson_ratio)
        if e <= 0.0:
            raise ValueError("Young's modulus must be positive")
        if not (-1.0 < nu < 0.5):
            raise ValueError("Poisson ratio must satisfy -1 < nu < 0.5")
        lam = e * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
        mu = e / (2.0 * (1.0 + nu))
        return np.array([
            [lam + 2*mu, lam, lam, 0, 0, 0],
            [lam, lam + 2*mu, lam, 0, 0, 0],
            [lam, lam, lam + 2*mu, 0, 0, 0],
            [0, 0, 0, mu, 0, 0],
            [0, 0, 0, 0, mu, 0],
            [0, 0, 0, 0, 0, mu],
        ], dtype=float)


def tet4_B_matrix(coords_mm: np.ndarray) -> tuple[np.ndarray, float]:
    coords = np.asarray(coords_mm, dtype=float)
    if coords.shape != (4, 3):
        raise ValueError("TET4 coordinates must have shape (4, 3)")
    m = np.ones((4, 4), dtype=float)
    m[:, 1:] = coords
    det_m = np.linalg.det(m)
    volume = abs(det_m) / 6.0
    if volume <= 1e-12:
        raise ValueError("Degenerate TET4 element")
    inv_m = np.linalg.inv(m)
    grads = inv_m[1:, :].T
    b = np.zeros((6, 12), dtype=float)
    for i, (dx, dy, dz) in enumerate(grads):
        j = 3*i
        b[0, j] = dx
        b[1, j+1] = dy
        b[2, j+2] = dz
        b[3, j] = dy; b[3, j+1] = dx
        b[4, j+1] = dz; b[4, j+2] = dy
        b[5, j] = dz; b[5, j+2] = dx
    return b, volume


def tet4_stiffness(coords_mm: np.ndarray, material: IsotropicMaterial) -> np.ndarray:
    b, volume = tet4_B_matrix(coords_mm)
    d = material.constitutive_matrix()
    return b.T @ d @ b * volume


def von_mises(stress_mpa: np.ndarray) -> float:
    sx, sy, sz, txy, tyz, txz = np.asarray(stress_mpa, dtype=float)
    return float(np.sqrt(0.5*((sx-sy)**2 + (sy-sz)**2 + (sz-sx)**2) + 3*(txy**2 + tyz**2 + txz**2)))
