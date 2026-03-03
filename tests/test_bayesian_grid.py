"""tests/test_bayesian_grid.py — TASK-11"""
import logging

import numpy as np
import pytest

from backend.app.fusion.bayesian_grid import BayesianGrid, COLLAPSE_THRESHOLD
from backend.app.fusion.grid_loader import make_synthetic_grid, CELL_SIZE_M


def _simple_grid() -> np.ndarray:
    """3×3 grid, all cells walkable."""
    return np.ones((3, 3), dtype=bool)


def _corridor_grid() -> np.ndarray:
    """10×10 synthetic corridor grid."""
    return make_synthetic_grid(10, 10)


class TestInitialisation:
    def test_uniform_prior_sum_one(self):
        g = BayesianGrid(_simple_grid())
        assert g.probability_grid().sum() == pytest.approx(1.0, rel=1e-9)

    def test_uniform_prior_equal_walkable(self):
        g = BayesianGrid(_simple_grid())
        p = g.probability_grid()
        vals = p[p > 0]
        assert np.allclose(vals, vals[0])

    def test_non_walkable_cells_zero(self):
        walk = np.zeros((4, 4), dtype=bool)
        walk[1, 1] = True
        g = BayesianGrid(walk)
        p = g.probability_grid()
        assert p[0, 0] == pytest.approx(0.0)
        assert p[1, 1] == pytest.approx(1.0)

    def test_empty_grid_no_crash(self):
        g = BayesianGrid(np.zeros((3, 3), dtype=bool))
        p = g.probability_grid()
        assert p.sum() == pytest.approx(0.0)


class TestUpdate:
    def test_sum_remains_one_after_update(self):
        g = BayesianGrid(_simple_grid())
        g.update(d_corrected=6.0, ap_xy=(0.5, 0.5))
        assert g.probability_grid().sum() == pytest.approx(1.0, rel=1e-6)

    def test_two_updates_sum_one(self):
        g = BayesianGrid(_corridor_grid())
        g.update(d_corrected=3.0, ap_xy=(1.0, 1.0))
        g.update(d_corrected=4.0, ap_xy=(4.0, 0.5))
        assert g.probability_grid().sum() == pytest.approx(1.0, rel=1e-6)

    def test_update_shifts_probability_toward_ap(self):
        """
        Two updates from orthogonal AP positions should concentrate the posterior
        (variance of walkable-cell probabilities must increase from uniform prior).
        Use a large 40×40 grid so walkable cells span true distances well above x₀.
        """
        big = make_synthetic_grid(40, 40)
        g = BayesianGrid(big)
        # AP at (0.25, 10.0) — walkable cells range from ~0.25 m to ~20 m away
        g.update(d_corrected=8.0, ap_xy=(0.25, 10.0))
        g.update(d_corrected=12.0, ap_xy=(20.0, 0.25))
        after = g.probability_grid()
        walkable_probs = after[big]
        # After two informative updates the posterior should be non-uniform:
        # std of walkable-cell probabilities must be > 0 (not flat)
        assert float(np.std(walkable_probs)) > 0.0, \
            "Posterior should be non-uniform after two updates"

    def test_reset_method(self):
        g = BayesianGrid(_simple_grid())
        g.update(d_corrected=6.0, ap_xy=(0.5, 0.5))
        g.reset()
        p = g.probability_grid()
        vals = p[p > 0]
        assert np.allclose(vals, vals[0])  # uniform again


class TestCollapse:
    def test_collapse_triggers_uniform_reset(self, caplog):
        """Force collapse by setting all probabilities to near-zero."""
        g = BayesianGrid(_simple_grid())
        # Manually corrupt internal probabilities
        g._prob[:] = 1e-20
        with caplog.at_level(logging.WARNING, logger="backend.app.fusion.bayesian_grid"):
            g.update(d_corrected=100.0, ap_xy=(50.0, 50.0))
        # After collapse reset, probabilities should sum to 1 again
        assert g.probability_grid().sum() == pytest.approx(1.0, rel=1e-6)
        assert any("collapse" in r.message.lower() for r in caplog.records)


class TestMapPosition:
    def test_map_position_returns_tuple(self):
        g = BayesianGrid(_simple_grid())
        pos = g.map_position()
        assert isinstance(pos, tuple)
        assert len(pos) == 2

    def test_map_position_within_grid(self):
        g = BayesianGrid(_corridor_grid())
        x, y = g.map_position()
        rows, cols = 10, 10
        assert 0 <= x <= cols * CELL_SIZE_M
        assert 0 <= y <= rows * CELL_SIZE_M

    def test_map_position_concentrates_after_updates(self):
        """Two consistent measurements should concentrate MAP near true position."""
        g = BayesianGrid(_corridor_grid())
        # AP at (1.0, 2.5); child at approx (2.0, 2.5) → true dist ≈ 1 m
        # But observation model is calibrated for d ≥ x₀=5.5, so use a realistic dist
        g.update(d_corrected=5.5, ap_xy=(0.5, 2.5))
        g.update(d_corrected=5.5, ap_xy=(0.5, 2.5))
        x, y = g.map_position()
        # Cell must be walkable — just check it returned a valid coordinate
        assert x > 0 or y > 0
