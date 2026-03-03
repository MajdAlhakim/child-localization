"""tests/test_fusion_coordinator.py — TASK-13"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from backend.app.fusion import coordinator as coord_module
from backend.app.fusion.coordinator import FusionCoordinator, publish_position, set_publisher
from backend.app.fusion.ekf import ExtendedKalmanFilter
from backend.app.fusion.bayesian_grid import BayesianGrid
from backend.app.fusion.pdr import PDRProcessor
from backend.app.fusion.grid_loader import make_synthetic_grid


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _make_coordinator(ap_positions=None, offset_fn=None) -> FusionCoordinator:
    ekf  = ExtendedKalmanFilter((2.5, 2.5))
    grid = BayesianGrid(make_synthetic_grid(10, 10))
    pdr  = PDRProcessor()
    return FusionCoordinator(
        device_id="test-device-001",
        ekf=ekf,
        grid=grid,
        pdr=pdr,
        offset_fn=offset_fn,
        ap_positions=ap_positions or {},
    )


# ── publish_position interface ────────────────────────────────────────────────

class TestPublishPositionInterface:
    @pytest.mark.asyncio
    async def test_stub_does_not_raise_without_publisher(self):
        """publish_position() must not raise when no publisher is registered."""
        # Temporarily unset publisher
        coord_module._publisher = None
        await publish_position(
            device_id="dev1",
            position=(1.0, 2.0),
            source="fused",
            confidence=0.8,
            active_aps=2,
            mode="normal",
        )

    @pytest.mark.asyncio
    async def test_set_publisher_routes_call(self):
        """set_publisher() routes publish_position() calls to the registered fn."""
        received = {}
        async def mock_pub(**kwargs):
            received.update(kwargs)

        set_publisher(mock_pub)
        try:
            await publish_position(
                device_id="dev1",
                position=(3.0, 4.0),
                source="fused",
                confidence=0.7,
                active_aps=3,
                mode="normal",
            )
            assert received["device_id"] == "dev1"
            assert received["position"]  == (3.0, 4.0)
            assert received["mode"]      == "normal"
        finally:
            coord_module._publisher = None

    @pytest.mark.asyncio
    async def test_publish_position_signature(self):
        """Verify kwarg names match the interface contract."""
        import inspect
        sig = inspect.signature(publish_position)
        params = list(sig.parameters.keys())
        assert "device_id" in params
        assert "position"  in params
        assert "source"    in params
        assert "confidence" in params
        assert "active_aps" in params
        assert "mode"      in params


# ── FusionCoordinator.on_imu ──────────────────────────────────────────────────

class TestOnIMU:
    @pytest.mark.asyncio
    async def test_on_imu_calls_ekf_predict(self):
        c = _make_coordinator()
        with patch.object(c.ekf, "predict", wraps=c.ekf.predict) as mock_predict:
            await c.on_imu(ax=0.1, ay=0.0, az=9.8, gz=0.0, t=0.5, dt=0.02)
        mock_predict.assert_called_once_with(0.1, 0.0, 0.02)

    @pytest.mark.asyncio
    async def test_on_imu_calls_pdr_update(self):
        c = _make_coordinator()
        with patch.object(c.pdr, "update", wraps=c.pdr.update) as mock_pdr:
            await c.on_imu(ax=0.1, ay=0.0, az=9.8, gz=0.0, t=0.5, dt=0.02)
        mock_pdr.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_imu_updates_last_data_time(self):
        c = _make_coordinator()
        t_before = c._last_data_t
        await c.on_imu(ax=0.0, ay=0.0, az=9.8, gz=0.0, t=0.5, dt=0.02)
        assert c._last_data_t >= t_before

    @pytest.mark.asyncio
    async def test_zupt_triggered_after_stationary_period(self):
        """ZUPT fires when |a| < 0.05 for > 2 s."""
        c = _make_coordinator()
        dt = 0.1
        with patch.object(c.ekf, "apply_zupt") as mock_zupt:
            for i in range(30):  # 3 seconds
                await c.on_imu(
                    ax=0.01, ay=0.01, az=0.01,  # tiny a → |a| ≈ 0.017 < 0.05
                    gz=0.0, t=i * dt, dt=dt,
                )
            mock_zupt.assert_called()

    @pytest.mark.asyncio
    async def test_zupt_not_triggered_when_moving(self):
        c = _make_coordinator()
        with patch.object(c.ekf, "apply_zupt") as mock_zupt:
            for i in range(30):
                await c.on_imu(
                    ax=0.5, ay=0.5, az=9.8,  # active walking
                    gz=0.0, t=i * 0.02, dt=0.02,
                )
            mock_zupt.assert_not_called()


# ── FusionCoordinator.on_rtt ──────────────────────────────────────────────────

class TestOnRTT:
    @pytest.mark.asyncio
    async def test_on_rtt_unknown_ap_skipped(self):
        c = _make_coordinator(ap_positions={})
        with patch.object(c.grid, "update") as mock_upd:
            await c.on_rtt([{
                "bssid": "AA:BB:CC:DD:EE:FF",
                "d_raw_mean": 10.0, "d_raw_std": 0.5,
                "rssi": -60, "band": "5GHz",
            }])
        mock_upd.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_rtt_known_ap_updates_grid(self):
        ap_pos = {"AA:BB:CC:DD:EE:FF": (1.0, 2.5)}
        c = _make_coordinator(ap_positions=ap_pos)
        with patch.object(c.grid, "update") as mock_upd:
            with patch.object(c.grid, "map_position", return_value=(2.0, 2.5)):
                await c.on_rtt([{
                    "bssid": "AA:BB:CC:DD:EE:FF",
                    "d_raw_mean": 8.0, "d_raw_std": 0.5,
                    "rssi": -60, "band": "5GHz",
                }])
        mock_upd.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_rtt_single_ap_uses_degraded_update(self):
        ap_pos = {"AP1": (1.0, 2.5)}
        c = _make_coordinator(ap_positions=ap_pos)
        with patch.object(c.ekf, "update") as mock_upd:
            with patch.object(c.grid, "update"):
                with patch.object(c.grid, "map_position", return_value=(2.0, 2.5)):
                    await c.on_rtt([{
                        "bssid": "AP1", "d_raw_mean": 8.0, "d_raw_std": 0.5,
                        "rssi": -60, "band": "5GHz",
                    }])
        mock_upd.assert_called_once_with((2.0, 2.5), degraded=True)

    @pytest.mark.asyncio
    async def test_on_rtt_two_aps_uses_normal_update(self):
        ap_pos = {"AP1": (1.0, 2.5), "AP2": (4.0, 2.5)}
        c = _make_coordinator(ap_positions=ap_pos)
        with patch.object(c.ekf, "update") as mock_upd:
            with patch.object(c.grid, "update"):
                with patch.object(c.grid, "map_position", return_value=(2.5, 2.5)):
                    await c.on_rtt([
                        {"bssid": "AP1", "d_raw_mean": 8.0, "d_raw_std": 0.5,
                         "rssi": -60, "band": "5GHz"},
                        {"bssid": "AP2", "d_raw_mean": 9.0, "d_raw_std": 0.5,
                         "rssi": -65, "band": "5GHz"},
                    ])
        mock_upd.assert_called_once_with((2.5, 2.5), degraded=False)


# ── Operating mode logic ──────────────────────────────────────────────────────

class TestOperatingMode:
    def test_disconnected_after_timeout(self):
        c = _make_coordinator()
        # Push last_data_t far into the past
        c._last_data_t = 0.0
        import time
        # Force monotonic past disconnect threshold
        with patch("backend.app.fusion.coordinator.time") as mock_time:
            mock_time.monotonic.return_value = 100.0  # > 5 s after last data
            mode = c._current_mode(active_aps=0)
        assert mode == "disconnected"

    def test_imu_only_mode(self):
        c = _make_coordinator()
        import time
        with patch("backend.app.fusion.coordinator.time") as mock_time:
            mock_time.monotonic.return_value = c._last_data_t + 0.5
            mode = c._current_mode(active_aps=0)
        assert mode == "imu_only"

    def test_degraded_mode(self):
        c = _make_coordinator()
        import time
        with patch("backend.app.fusion.coordinator.time") as mock_time:
            mock_time.monotonic.return_value = c._last_data_t + 0.5
            mode = c._current_mode(active_aps=1)
        assert mode == "degraded"

    def test_normal_mode(self):
        c = _make_coordinator()
        import time
        with patch("backend.app.fusion.coordinator.time") as mock_time:
            mock_time.monotonic.return_value = c._last_data_t + 0.5
            mode = c._current_mode(active_aps=2)
        assert mode == "normal"


# ── EKF divergence handling ───────────────────────────────────────────────────

class TestDivergenceHandling:
    @pytest.mark.asyncio
    async def test_divergence_reset_after_threshold(self):
        """After DIVERGENCE_MAX_CYCLES consecutive divergence calls, EKF is reset."""
        ap_pos = {"AP1": (1.0, 2.5)}
        c = _make_coordinator(ap_positions=ap_pos)
        # Force EKF to a position very far from Bayesian MAP
        c.ekf.x[0] = 100.0
        c.ekf.x[1] = 100.0

        reset_called = []
        original_reset = c.ekf.reset_from_bayes
        def tracked_reset(pos):
            reset_called.append(pos)
            return original_reset(pos)
        c.ekf.reset_from_bayes = tracked_reset

        with patch.object(c.grid, "update"):
            with patch.object(c.grid, "map_position", return_value=(2.5, 2.5)):
                for _ in range(c.DIVERGENCE_MAX_CYCLES + 1):
                    await c.on_rtt([{
                        "bssid": "AP1", "d_raw_mean": 8.0, "d_raw_std": 0.5,
                        "rssi": -60, "band": "5GHz",
                    }])
        assert len(reset_called) > 0, "EKF.reset_from_bayes should have been called"
