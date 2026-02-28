"""Tests for TASK-07: RTT offset correction engine.

PRD §8.2: d_corrected = d_raw − d_offset; clamp minimum 0.5 m
Expected offset ranges: 2400–2700 m (5 GHz), ~1500 m (2.4 GHz)
"""
import pytest
from backend.app.fusion.offset_corrector import correct


def test_correct_5ghz_typical():
    """5 GHz AP: d_raw=2600.0, offset=2587.3 → 12.7 m."""
    result = correct(2600.0, 2587.3)
    assert abs(result - 12.7) < 1e-6


def test_correct_24ghz_typical():
    """2.4 GHz AP: d_raw=1560.0, offset=1542.1 → 17.9 m."""
    result = correct(1560.0, 1542.1)
    assert abs(result - 17.9) < 1e-6


def test_correct_clamp_minimum():
    """Result below 0.5 m is clamped to 0.5 m."""
    result = correct(2500.0, 2500.4)  # would give 0.4 — must clamp
    assert result == pytest.approx(0.5)


def test_correct_exact_minimum():
    """Result exactly 0.5 m is returned as-is."""
    result = correct(2500.5, 2500.0)
    assert result == pytest.approx(0.5)


def test_correct_zero_offset():
    """Zero offset: d_corrected == d_raw (if ≥ 0.5)."""
    result = correct(15.0, 0.0)
    assert result == pytest.approx(15.0)


def test_correct_large_distance():
    """Normal large corrected distance passes through without clamping."""
    result = correct(2700.0, 2587.3)
    assert result == pytest.approx(112.7)


def test_correct_clamp_is_exactly_point_five():
    """Clamp value is precisely 0.5 — not 0 or 1."""
    result = correct(1000.0, 2000.0)  # negative → clamped
    assert result == 0.5
