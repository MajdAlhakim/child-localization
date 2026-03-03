"""tests/test_observation_model.py — TASK-10"""
import numpy as np
import pytest

from backend.app.fusion.observation_model import (
    X0, A, ALPHA, SIGMA0, SIGMA_M, BETA,
    mu, sigma, p_observation,
)


class TestLockedConstants:
    def test_x0(self):    assert X0      == pytest.approx(5.5)
    def test_a(self):     assert A       == pytest.approx(2.23)
    def test_alpha(self): assert ALPHA   == pytest.approx(0.043)
    def test_sigma0(self):assert SIGMA0  == pytest.approx(4.0)
    def test_sigm(self):  assert SIGMA_M == pytest.approx(0.55)
    def test_beta(self):  assert BETA    == pytest.approx(0.015)


class TestMu:
    def test_at_x0(self):
        # At x = x₀: exponent term = 0 → mu = x₀ * (1 + A*α*0*exp(0)) = x₀
        assert mu(X0) == pytest.approx(X0, rel=1e-9)

    def test_increases_with_distance(self):
        # mu should increase as x increases beyond x₀ (positive bias)
        assert mu(10.0) > mu(7.0)

    def test_positive(self):
        for x in [5.5, 8.0, 15.0, 30.0]:
            assert mu(x) > 0

    def test_formula_at_known_point(self):
        x = 10.0
        expected = x * (1.0 + A * ALPHA * (x - X0) * np.exp(-ALPHA * (x - X0)))
        assert mu(x) == pytest.approx(expected, rel=1e-9)


class TestSigma:
    def test_at_x0(self):
        # At x = x₀: sigma = σ₀ + σ_m * 0 * exp(0) = σ₀
        assert sigma(X0) == pytest.approx(SIGMA0, rel=1e-9)

    def test_positive_for_large_x(self):
        assert sigma(20.0) > 0

    def test_formula_at_known_point(self):
        x = 12.0
        expected = SIGMA0 + SIGMA_M * (x - X0) * np.exp(-BETA * (x - X0))
        assert sigma(x) == pytest.approx(expected, rel=1e-9)


class TestPObservation:
    def test_positive(self):
        for y in [5.5, 8.0, 15.0]:
            assert p_observation(y, 10.0) >= 0.0

    def test_mode_near_mu(self):
        # p(y|x) should be maximised when y ≈ mu(x)
        x = 12.0
        y_peak = mu(x)
        assert p_observation(y_peak, x) > p_observation(y_peak + 3.0, x)
        assert p_observation(y_peak, x) > p_observation(y_peak - 3.0, x)

    def test_x_clamped_to_x0(self):
        # Passing x < x₀ should give the same result as x = x₀
        assert p_observation(6.0, 2.0) == pytest.approx(
            p_observation(6.0, X0), rel=1e-9
        )

    def test_normalisation_integral_approx_one(self):
        # Numerical integration ∫ p(y|x) dy should be ≈ 1 for x > x₀
        x = 15.0
        y_vals = np.linspace(0, 50, 10000)
        dy = y_vals[1] - y_vals[0]
        integral = sum(p_observation(y, x) for y in y_vals) * dy
        assert integral == pytest.approx(1.0, abs=0.02)

    def test_returns_float(self):
        result = p_observation(10.0, 10.0)
        assert isinstance(result, float)
