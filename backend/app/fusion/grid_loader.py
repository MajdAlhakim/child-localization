"""
backend/app/fusion/grid_loader.py
Floor-plan grid loader — TASK-09

Produces a 2-D boolean NumPy array (dtype=bool, shape=(rows, cols)) where
True marks a walkable 0.5 m × 0.5 m cell.

Two input formats are supported:
  • PNG image  — any non-white pixel is walkable (uses Pillow)
  • JSON dict  — {"rows": int, "cols": int, "walkable": [[r, c], ...]}

When the real H07-C floor plan is available (OQ-03), pass its path to
load_grid().  Until then, create a synthetic grid with make_synthetic_grid().

Person C owns this file.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


CELL_SIZE_M: float = 0.5  # locked — do not change


def load_grid(path: str | Path) -> np.ndarray:
    """
    Load a walkable boolean grid from a PNG or JSON file.

    Args:
        path: Path to a .png floor-plan image or a .json walkable-cell file.

    Returns:
        2-D bool array, shape (rows, cols). True = walkable cell.

    Raises:
        ValueError: if the file extension is not .png or .json.
        FileNotFoundError: if the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Floor plan file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".png":
        return _load_from_png(path)
    elif suffix == ".json":
        return _load_from_json(path)
    else:
        raise ValueError(
            f"Unsupported floor plan format '{suffix}'. Expected '.png' or '.json'."
        )


def _load_from_png(path: Path) -> np.ndarray:
    """Load walkable grid from a PNG image (any non-white pixel → walkable)."""
    try:
        from PIL import Image  # type: ignore
    except ImportError as e:
        raise ImportError(
            "Pillow is required to load PNG floor plans: pip install Pillow"
        ) from e

    img = Image.open(path).convert("RGB")
    arr = np.array(img)               # shape (H, W, 3), dtype uint8
    # White pixel = (255, 255, 255) → not walkable
    walkable = ~np.all(arr == 255, axis=2)
    return walkable


def _load_from_json(path: Path) -> np.ndarray:
    """
    Load walkable grid from a JSON descriptor.

    Expected schema:
        {
          "rows": <int>,
          "cols": <int>,
          "walkable": [[r0, c0], [r1, c1], ...]
        }
    """
    import json

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    rows: int = int(data["rows"])
    cols: int = int(data["cols"])
    grid = np.zeros((rows, cols), dtype=bool)
    for r, c in data.get("walkable", []):
        grid[int(r), int(c)] = True
    return grid


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_synthetic_grid(rows: int = 10, cols: int = 10) -> np.ndarray:
    """
    Build a small synthetic walkable corridor grid for testing / development.

    The synthetic layout: a central horizontal corridor (row 4–5) spanning all
    columns, plus a vertical spur (col 4–5) spanning all rows.  This is a
    simple L/cross shape that exercises both axes without requiring the real
    H07-C floor plan.

    Args:
        rows: number of 0.5-m grid rows.
        cols: number of 0.5-m grid columns.

    Returns:
        2-D bool array, shape (rows, cols).
    """
    grid = np.zeros((rows, cols), dtype=bool)
    mid_r1 = rows // 2 - 1
    mid_r2 = rows // 2
    mid_c1 = cols // 2 - 1
    mid_c2 = cols // 2

    # Horizontal corridor
    grid[mid_r1:mid_r2 + 1, :] = True
    # Vertical spur
    grid[:, mid_c1:mid_c2 + 1] = True
    return grid


def grid_shape_m(grid: np.ndarray) -> tuple[float, float]:
    """Return physical size (height_m, width_m) of grid given CELL_SIZE_M."""
    rows, cols = grid.shape
    return (rows * CELL_SIZE_M, cols * CELL_SIZE_M)


def cell_to_xy(row: int, col: int) -> tuple[float, float]:
    """Convert grid (row, col) index to corridor (x, y) in metres (cell centre)."""
    x_m = (col + 0.5) * CELL_SIZE_M
    y_m = (row + 0.5) * CELL_SIZE_M
    return (x_m, y_m)


def xy_to_cell(x_m: float, y_m: float) -> tuple[int, int]:
    """Convert corridor (x, y) in metres to grid (row, col) index."""
    col = int(x_m / CELL_SIZE_M)
    row = int(y_m / CELL_SIZE_M)
    return (row, col)
