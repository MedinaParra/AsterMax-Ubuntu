import math

import numpy as np
import pytest

from astermax.fea.feature_geometry_error import summarize_deviations


def test_geometry_deviation_summary_is_exact_and_deterministic():
    summary = summarize_deviations(np.asarray([0.0, 0.1, 0.2, 0.3]))
    assert summary.count == 4
    assert summary.maximum_mm == pytest.approx(0.3)
    assert summary.mean_mm == pytest.approx(0.15)
    assert summary.rms_mm == pytest.approx(math.sqrt((0.0 + 0.01 + 0.04 + 0.09) / 4.0))


def test_geometry_deviation_summary_rejects_negative_values():
    with pytest.raises(ValueError, match="non-empty finite non-negative"):
        summarize_deviations(np.asarray([0.0, -1.0]))


def test_geometry_deviation_summary_rejects_nonfinite_values():
    with pytest.raises(ValueError, match="non-empty finite non-negative"):
        summarize_deviations(np.asarray([0.0, np.nan]))


def test_geometry_deviation_summary_rejects_empty_input():
    with pytest.raises(ValueError, match="non-empty finite non-negative"):
        summarize_deviations(np.asarray([]))
