"""
backend/app/fusion/bayesian_grid.py
Bayesian grid update engine — TASK-11

Maintains a 2-D probability distribution over walkable grid cells.
Updated multiplicatively with RTT likelihood measurements; MAP position
is returned after each update.

Person C owns this file.
"""

from __future__ import annotations

import logging

import numpy as np

from .grid_loader import cell_to_xy, CELL_SIZE_M
from .observation_model import p_observation

logger = logging.getLogger(__name__)

COLLAPSE_THRESHOLD = 1e-10  # locked — do not change


class BayesianGrid:
    """
    Bayesian probability grid over walkable cells at 0.5 m resolution.

    The grid is initialised to a uniform prior over walkable cells.
    Each call to update() multiplies walkable cell probabilities by the
    RTT likelihood p_observation(d_corrected, dist(cell, AP)).

    Collapse recovery: if the total probability mass drops below 1e-10,
    the grid is reset to a uniform prior and the event is logged.
    """

    def __init__(self, walkable: np.ndarray):
        """
        Args:
            walkable: 2-D bool array (rows × cols), True = walkable cell.
                      Produced by grid_loader.load_grid() or make_synthetic_grid().
        """
        self._walkable = walkable.astype(bool)
        rows, cols = walkable.shape
        self._rows = rows
        self._cols = cols

        # Pre-compute (x, y) centre coordinates for all cells
        self._cell_xy = self._precompute_cell_xy()

        # Initialise uniform prior over walkable cells
        self._prob = np.zeros((rows, cols), dtype=np.float64)
        n_walkable = int(walkable.sum())
        if n_walkable > 0:
            self._prob[walkable] = 1.0 / n_walkable

    # ── Update ────────────────────────────────────────────────────────────────

    def update(
        self,
        d_corrected: float,
        ap_xy: tuple[float, float],
    ) -> None:
        """
        Incorporate one RTT measurement into the grid posterior.

        Multiply each walkable cell's probability by p(d_corrected | dist(cell, AP))
        then re-normalise.

        Args:
            d_corrected: offset-corrected RTT distance in metres.
            ap_xy:       physical (x_m, y_m) position of the measuring AP.
        """
        ap_x, ap_y = float(ap_xy[0]), float(ap_xy[1])

        # Vectorised distance from every cell centre to AP
        dx = self._cell_xy[:, :, 0] - ap_x
        dy = self._cell_xy[:, :, 1] - ap_y
        dist_grid = np.sqrt(dx**2 + dy**2)

        # Compute p_observation for every cell using vectorised ops
        # Clamp x to X0 and sigma to 0.1 (matches observation_model.p_observation)
        from .observation_model import X0, A, ALPHA, SIGMA0, SIGMA_M, BETA
        x_c = np.maximum(dist_grid, X0)
        m_grid = x_c * (1.0 + A * ALPHA * (x_c - X0) * np.exp(-ALPHA * (x_c - X0)))
        s_grid = np.maximum(
            SIGMA0 + SIGMA_M * (x_c - X0) * np.exp(-BETA * (x_c - X0)),
            0.1,
        )
        likelihood = (1.0 / (np.sqrt(2.0 * np.pi) * s_grid)) * np.exp(
            -0.5 * ((d_corrected - m_grid) / s_grid) ** 2
        )

        # Apply likelihood only to walkable cells
        self._prob[self._walkable] *= likelihood[self._walkable]

        # Normalise
        total = self._prob.sum()
        if total < COLLAPSE_THRESHOLD:
            logger.warning(
                "BayesianGrid: probability collapse (sum=%g) — resetting to uniform prior",
                total,
            )
            self._reset_uniform()
        else:
            self._prob /= total

    # ── MAP estimate ──────────────────────────────────────────────────────────

    def map_position(self) -> tuple[float, float]:
        """
        Return the Maximum A Posteriori position estimate.

        Returns:
            (x_m, y_m) of the walkable cell with highest posterior probability.
        """
        idx = int(np.argmax(self._prob))
        row = idx // self._cols
        col = idx %  self._cols
        return cell_to_xy(row, col)

    # ── Grid state accessors ──────────────────────────────────────────────────

    def probability_grid(self) -> np.ndarray:
        """Return a copy of the current probability grid (rows × cols)."""
        return self._prob.copy()

    def reset(self) -> None:
        """Manually reset to uniform prior (e.g. after device reacquired)."""
        self._reset_uniform()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _reset_uniform(self) -> None:
        self._prob[:] = 0.0
        n_walkable = int(self._walkable.sum())
        if n_walkable > 0:
            self._prob[self._walkable] = 1.0 / n_walkable

    def _precompute_cell_xy(self) -> np.ndarray:
        """
        Build (rows, cols, 2) array of (x_m, y_m) cell-centre coordinates.
        """
        rows, cols = self._rows, self._cols
        xy = np.zeros((rows, cols, 2), dtype=np.float64)
        for r in range(rows):
            for c in range(cols):
                xy[r, c, 0] = (c + 0.5) * CELL_SIZE_M  # x
                xy[r, c, 1] = (r + 0.5) * CELL_SIZE_M  # y
        return xy
