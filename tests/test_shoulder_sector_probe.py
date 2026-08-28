import math

import numpy as np
import pytest

from astermax.fea.shoulder_sector_probe import (
    ShoulderSectorProbeError,
    sectorized_ring_indices,
)


def _ring_points(sectors=12, x=38.0, radius=10.0, radial_offset=0.2, axial_offset=0.1):
    rows = []
    for i in range(sectors):
        theta = (i + 0.5) * 2.0 * math.pi / sectors
        rows.append(
            [
                x + axial_offset,
                (radius + radial_offset) * math.cos(theta),
                (radius + radial_offset) * math.sin(theta),
            ]
        )
    return np.asarray(rows, dtype=float)


def test_sectorized_probe_selects_exactly_one_point_per_sector():
    primary = _ring_points()
    farther = _ring_points(radial_offset=0.8, axial_offset=0.7)
    coords = np.vstack([farther, primary])
    indices, distances, azimuths = sectorized_ring_indices(
        coords,
        center_yz_mm=(0.0, 0.0),
        ring_x_mm=38.0,
        ring_radius_mm=10.0,
        sector_count=12,
        maximum_allowed_distance_mm=2.0,
    )
    assert indices.shape == (12,)
    assert np.all(indices >= 12)  # nearer primary point wins in every sector
    assert np.max(distances) < 0.25
    assert len(set(indices.tolist())) == 12
    sector_width = 2.0 * math.pi / 12
    observed = np.floor(azimuths / sector_width).astype(int)
    assert observed.tolist() == list(range(12))


def test_sectorized_probe_fails_closed_when_one_azimuth_sector_is_unresolved():
    coords = np.delete(_ring_points(), 5, axis=0)
    with pytest.raises(ShoulderSectorProbeError, match="UNRESOLVED_AZIMUTH_SECTOR:5"):
        sectorized_ring_indices(
            coords,
            center_yz_mm=(0.0, 0.0),
            ring_x_mm=38.0,
            ring_radius_mm=10.0,
            sector_count=12,
            maximum_allowed_distance_mm=1.0,
        )


def test_sectorized_probe_tie_break_is_deterministic_by_flat_index():
    base = _ring_points(sectors=4, radial_offset=0.0, axial_offset=0.0)
    duplicate = base[[0]].copy()
    coords = np.vstack([base, duplicate])
    indices, _, _ = sectorized_ring_indices(
        coords,
        center_yz_mm=(0.0, 0.0),
        ring_x_mm=38.0,
        ring_radius_mm=10.0,
        sector_count=4,
        maximum_allowed_distance_mm=0.1,
    )
    assert indices[0] == 0


def test_sectorized_probe_rejects_too_few_sectors():
    with pytest.raises(ValueError, match="sector_count must be >= 4"):
        sectorized_ring_indices(
            _ring_points(sectors=4),
            center_yz_mm=(0.0, 0.0),
            ring_x_mm=38.0,
            ring_radius_mm=10.0,
            sector_count=3,
            maximum_allowed_distance_mm=1.0,
        )
