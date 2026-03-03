"""tests/test_grid_loader.py — TASK-09"""
import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from backend.app.fusion.grid_loader import (
    CELL_SIZE_M,
    cell_to_xy,
    grid_shape_m,
    load_grid,
    make_synthetic_grid,
    xy_to_cell,
)


# ── make_synthetic_grid ───────────────────────────────────────────────────────

class TestSyntheticGrid:
    def test_shape(self):
        g = make_synthetic_grid(10, 10)
        assert g.shape == (10, 10)

    def test_dtype(self):
        g = make_synthetic_grid(10, 10)
        assert g.dtype == bool

    def test_horizontal_corridor_walkable(self):
        g = make_synthetic_grid(10, 10)
        # Row 4 and 5 should all be walkable
        assert g[4, :].all(), "row 4 should be fully walkable"
        assert g[5, :].all(), "row 5 should be fully walkable"

    def test_vertical_spur_walkable(self):
        g = make_synthetic_grid(10, 10)
        assert g[:, 4].all(), "col 4 should be fully walkable"
        assert g[:, 5].all(), "col 5 should be fully walkable"

    def test_corner_not_walkable(self):
        g = make_synthetic_grid(10, 10)
        assert not g[0, 0], "corner (0,0) should not be walkable"
        assert not g[0, 9], "corner (0,9) should not be walkable"
        assert not g[9, 0], "corner (9,0) should not be walkable"

    def test_at_least_one_walkable(self):
        g = make_synthetic_grid(10, 10)
        assert g.sum() > 0

    def test_custom_size(self):
        g = make_synthetic_grid(6, 8)
        assert g.shape == (6, 8)


# ── coordinate helpers ────────────────────────────────────────────────────────

class TestCoordinateHelpers:
    def test_cell_to_xy_origin(self):
        x, y = cell_to_xy(0, 0)
        assert x == pytest.approx(0.25)
        assert y == pytest.approx(0.25)

    def test_cell_to_xy_general(self):
        x, y = cell_to_xy(2, 3)
        assert x == pytest.approx((3 + 0.5) * CELL_SIZE_M)
        assert y == pytest.approx((2 + 0.5) * CELL_SIZE_M)

    def test_xy_to_cell_origin(self):
        r, c = xy_to_cell(0.1, 0.1)
        assert r == 0
        assert c == 0

    def test_xy_to_cell_roundtrip(self):
        x, y = cell_to_xy(3, 7)
        r, c = xy_to_cell(x, y)
        assert r == 3
        assert c == 7

    def test_cell_size_is_half_metre(self):
        assert CELL_SIZE_M == pytest.approx(0.5)

    def test_grid_shape_m(self):
        g = make_synthetic_grid(10, 10)
        h, w = grid_shape_m(g)
        assert h == pytest.approx(5.0)
        assert w == pytest.approx(5.0)


# ── load_grid from JSON ───────────────────────────────────────────────────────

class TestLoadGridJSON:
    def test_load_json_walkable_cells(self, tmp_path):
        data = {
            "rows": 4,
            "cols": 4,
            "walkable": [[1, 0], [1, 1], [1, 2], [1, 3]],
        }
        p = tmp_path / "floor.json"
        p.write_text(json.dumps(data))
        g = load_grid(p)
        assert g.shape == (4, 4)
        assert g[1, 0] and g[1, 1] and g[1, 2] and g[1, 3]
        assert not g[0, 0]

    def test_load_json_empty_walkable(self, tmp_path):
        data = {"rows": 3, "cols": 3, "walkable": []}
        p = tmp_path / "floor.json"
        p.write_text(json.dumps(data))
        g = load_grid(p)
        assert not g.any()

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_grid(tmp_path / "missing.json")

    def test_load_unsupported_extension_raises(self, tmp_path):
        p = tmp_path / "floor.txt"
        p.write_text("data")
        with pytest.raises(ValueError, match="Unsupported"):
            load_grid(p)
