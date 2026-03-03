"""tests/test_ekf.py — TASK-12"""
import numpy as np
import pytest

from backend.app.fusion.ekf import ExtendedKalmanFilter


class TestInitialisation:
    def test_initial_position(self):
        ekf = ExtendedKalmanFilter((3.0, 4.0))
        px, py = ekf.get_position()
        assert px == pytest.approx(3.0)
        assert py == pytest.approx(4.0)

    def test_initial_velocity_zero(self):
        ekf = ExtendedKalmanFilter((0.0, 0.0))
        state = ekf.get_state()
        assert state[2] == pytest.approx(0.0)
        assert state[3] == pytest.approx(0.0)

    def test_P0_diagonal(self):
        ekf = ExtendedKalmanFilter()
        expected = np.diag([25.0, 25.0, 4.0, 4.0])
        np.testing.assert_allclose(ekf.P, expected)

    def test_Q_diagonal(self):
        ekf = ExtendedKalmanFilter()
        expected = np.diag([0.01, 0.01, 0.1, 0.1])
        np.testing.assert_allclose(ekf.Q, expected)

    def test_R_normal(self):
        ekf = ExtendedKalmanFilter()
        expected = np.diag([9.0, 9.0])
        np.testing.assert_allclose(ekf.R_normal, expected)

    def test_R_degraded(self):
        ekf = ExtendedKalmanFilter()
        expected = np.diag([18.0, 18.0])
        np.testing.assert_allclose(ekf.R_degraded, expected)


class TestPredict:
    def test_predict_updates_position(self):
        ekf = ExtendedKalmanFilter((0.0, 0.0))
        ekf.predict(ax=1.0, ay=0.0, dt=0.1)
        px, py = ekf.get_position()
        # px = 0 + 0·0.1 + 0.5·1·0.1² = 0.005
        assert px == pytest.approx(0.005, abs=1e-9)
        assert py == pytest.approx(0.0, abs=1e-9)

    def test_predict_updates_velocity(self):
        ekf = ExtendedKalmanFilter((0.0, 0.0))
        ekf.predict(ax=2.0, ay=0.0, dt=0.5)
        state = ekf.get_state()
        # vx = 0 + ax·dt = 1.0
        assert state[2] == pytest.approx(1.0, abs=1e-9)

    def test_predict_grows_covariance(self):
        ekf = ExtendedKalmanFilter()
        P_before = ekf.P.copy()
        ekf.predict(ax=0.0, ay=0.0, dt=0.1)
        assert ekf.P[0, 0] > P_before[0, 0]

    def test_predict_zero_accel_constant_velocity(self):
        ekf = ExtendedKalmanFilter((1.0, 2.0))
        # Inject velocity artificially
        ekf.x[2] = 3.0   # vx
        ekf.x[3] = 4.0   # vy
        ekf.predict(ax=0.0, ay=0.0, dt=1.0)
        px, py = ekf.get_position()
        assert px == pytest.approx(4.0, abs=1e-9)
        assert py == pytest.approx(6.0, abs=1e-9)

    def test_small_dt_clamped(self):
        # dt=0 should not error (clamped to 1e-6 internally)
        ekf = ExtendedKalmanFilter()
        ekf.predict(ax=1.0, ay=1.0, dt=0.0)


class TestUpdate:
    def test_update_normal_pulls_toward_measurement(self):
        ekf = ExtendedKalmanFilter((0.0, 0.0))
        ekf.update((5.0, 5.0), degraded=False)
        px, py = ekf.get_position()
        assert px > 0.0
        assert py > 0.0

    def test_update_reduces_covariance(self):
        ekf = ExtendedKalmanFilter()
        P_before = ekf.P.copy()
        ekf.update((2.0, 2.0), degraded=False)
        assert ekf.P[0, 0] < P_before[0, 0]

    def test_update_degraded_uses_larger_R(self):
        ekf1 = ExtendedKalmanFilter((0.0, 0.0))
        ekf2 = ExtendedKalmanFilter((0.0, 0.0))
        ekf1.update((10.0, 0.0), degraded=False)
        ekf2.update((10.0, 0.0), degraded=True)
        # Degraded → larger R → less trust in measurement → smaller correction
        assert ekf2.get_position()[0] < ekf1.get_position()[0]

    def test_perfect_match_minimal_correction(self):
        ekf = ExtendedKalmanFilter((3.0, 4.0))
        ekf.update((3.0, 4.0), degraded=False)
        px, py = ekf.get_position()
        # Kalman gain × 0 innovation ≈ no change
        assert px == pytest.approx(3.0, abs=0.01)
        assert py == pytest.approx(4.0, abs=0.01)


class TestDivergenceAndReset:
    def test_no_divergence_close(self):
        ekf = ExtendedKalmanFilter((1.0, 1.0))
        assert not ekf.check_divergence((1.5, 1.5))

    def test_divergence_detected(self):
        ekf = ExtendedKalmanFilter((0.0, 0.0))
        assert ekf.check_divergence((11.0, 0.0))

    def test_divergence_boundary_exactly_10(self):
        ekf = ExtendedKalmanFilter((0.0, 0.0))
        # Exactly 10 m is NOT divergent (> 10 required)
        assert not ekf.check_divergence((10.0, 0.0))

    def test_reset_from_bayes(self):
        ekf = ExtendedKalmanFilter((0.0, 0.0))
        ekf.predict(ax=1.0, ay=1.0, dt=0.5)
        ekf.reset_from_bayes((7.0, 8.0))
        px, py = ekf.get_position()
        assert px == pytest.approx(7.0)
        assert py == pytest.approx(8.0)
        # Velocity zeroed
        state = ekf.get_state()
        assert state[2] == pytest.approx(0.0)
        assert state[3] == pytest.approx(0.0)
        # Covariance reset to P₀
        np.testing.assert_allclose(ekf.P, np.diag([25.0, 25.0, 4.0, 4.0]))


class TestZUPT:
    def test_zupt_zeroes_velocity(self):
        ekf = ExtendedKalmanFilter()
        ekf.predict(ax=2.0, ay=3.0, dt=0.5)
        assert ekf.get_state()[2] != pytest.approx(0.0)
        ekf.apply_zupt()
        state = ekf.get_state()
        assert state[2] == pytest.approx(0.0)
        assert state[3] == pytest.approx(0.0)

    def test_zupt_preserves_position(self):
        ekf = ExtendedKalmanFilter((5.0, 6.0))
        ekf.predict(ax=0.5, ay=0.5, dt=1.0)
        px_before, py_before = ekf.get_position()
        ekf.apply_zupt()
        px_after, py_after = ekf.get_position()
        assert px_after == pytest.approx(px_before, abs=1e-9)
        assert py_after == pytest.approx(py_before, abs=1e-9)
