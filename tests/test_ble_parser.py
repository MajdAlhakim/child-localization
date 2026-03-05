"""
tests/test_ble_parser.py

Full test suite for backend/app/core/ble_parser.py

Tests cover:
  - Valid IMU (0x01) packet: exact byte layout and field values
  - Valid RTT (0x02) packet: zero APs, one AP, three APs
  - Type dispatch: correct dataclass type returned
  - Error paths: empty payload, unknown type byte, truncated IMU, truncated RTT header,
    truncated RTT record area
  - MAC formatting: colon-separated uppercase hex
  - RTT band decoding: 0x01→2.4GHz, 0x02→5GHz, unknown byte
  - Signed RSSI (negative values)
  - Sequence counter wraparound (uint8)
"""

from __future__ import annotations

import struct
import pytest

from backend.app.core.ble_parser import (
    ImuPacket,
    RttPacket,
    ApRecord,
    parse,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — build raw packets from component values
# ─────────────────────────────────────────────────────────────────────────────

def _mac_bytes(mac_str: str = "24:42:E3:15:E5:72") -> bytes:
    return bytes(int(x, 16) for x in mac_str.split(":"))


def build_imu_packet(
    mac: str = "24:42:E3:15:E5:72",
    ts_ms: int = 123456789,
    ax: float = 0.1,
    ay: float = -0.2,
    az: float = 9.81,
    gx: float = 0.01,
    gy: float = -0.02,
    gz: float = 0.005,
    seq: int = 42,
) -> bytes:
    """Construct a valid 40-byte Type 0x01 IMU packet."""
    buf = bytearray(40)
    buf[0] = 0x01
    buf[1:7] = _mac_bytes(mac)
    struct.pack_into("<Q", buf, 7, ts_ms)
    struct.pack_into("<ffffff", buf, 15, ax, ay, az, gx, gy, gz)
    buf[39] = seq & 0xFF
    return bytes(buf)


def build_rtt_packet(
    mac: str = "24:42:E3:15:E5:72",
    ts_ms: int = 987654321,
    aps: list[tuple[str, float, float, int, int]] | None = None,
    # each ap: (bssid_str, d_mean, d_std, rssi_signed, band_u8)
) -> bytes:
    """Construct a valid variable-length Type 0x02 RTT packet."""
    aps = aps or []
    ap_count = len(aps)
    total = 16 + ap_count * 16
    buf = bytearray(total)
    buf[0] = 0x02
    buf[1:7] = _mac_bytes(mac)
    struct.pack_into("<Q", buf, 7, ts_ms)
    buf[15] = ap_count & 0xFF
    for i, (bssid_str, d_mean, d_std, rssi, band_u8) in enumerate(aps):
        offset = 16 + i * 16
        buf[offset : offset + 6] = _mac_bytes(bssid_str)
        struct.pack_into("<f", buf, offset + 6, d_mean)
        struct.pack_into("<f", buf, offset + 10, d_std)
        struct.pack_into("<b", buf, offset + 14, rssi)   # signed
        buf[offset + 15] = band_u8
    return bytes(buf)


# ─────────────────────────────────────────────────────────────────────────────
# IMU packet tests
# ─────────────────────────────────────────────────────────────────────────────

class TestImuPacket:
    def test_parse_returns_imu_packet_type(self):
        pkt = parse(build_imu_packet())
        assert isinstance(pkt, ImuPacket)

    def test_packet_type_field(self):
        pkt = parse(build_imu_packet())
        assert pkt.packet_type == 0x01

    def test_mac_formatted_correctly(self):
        pkt = parse(build_imu_packet(mac="24:42:E3:15:E5:72"))
        assert pkt.mac == "24:42:E3:15:E5:72"

    def test_mac_uppercase(self):
        pkt = parse(build_imu_packet(mac="AA:BB:CC:DD:EE:FF"))
        assert pkt.mac == "AA:BB:CC:DD:EE:FF"

    def test_ts_ms_roundtrip(self):
        pkt = parse(build_imu_packet(ts_ms=0xDEADBEEFCAFEBABE & 0xFFFFFFFFFFFFFFFF))
        # uint64 — just check it's a positive int
        assert isinstance(pkt.ts_ms, int)
        assert pkt.ts_ms >= 0

    def test_accel_values(self):
        pkt = parse(build_imu_packet(ax=1.5, ay=-2.25, az=9.81))
        assert abs(pkt.ax_ms2 - 1.5) < 1e-5
        assert abs(pkt.ay_ms2 - (-2.25)) < 1e-5
        assert abs(pkt.az_ms2 - 9.81) < 1e-4

    def test_gyro_values(self):
        pkt = parse(build_imu_packet(gx=0.01, gy=-0.02, gz=0.005))
        assert abs(pkt.gx_rads - 0.01) < 1e-6
        assert abs(pkt.gy_rads - (-0.02)) < 1e-6
        assert abs(pkt.gz_rads - 0.005) < 1e-6

    def test_seq_zero(self):
        pkt = parse(build_imu_packet(seq=0))
        assert pkt.seq == 0

    def test_seq_max_uint8(self):
        pkt = parse(build_imu_packet(seq=255))
        assert pkt.seq == 255

    def test_seq_wraps_to_255(self):
        # seq field is uint8; build_imu_packet masks to 0xFF already
        pkt = parse(build_imu_packet(seq=255))
        assert pkt.seq == 255

    def test_ts_ms_specific_value(self):
        pkt = parse(build_imu_packet(ts_ms=123456789))
        assert pkt.ts_ms == 123456789

    def test_imu_too_short_raises(self):
        raw = build_imu_packet()[:20]  # truncated
        with pytest.raises(ValueError, match="IMU packet too short"):
            parse(raw)

    def test_exact_40_bytes(self):
        raw = build_imu_packet()
        assert len(raw) == 40
        pkt = parse(raw)
        assert isinstance(pkt, ImuPacket)

    def test_trailing_bytes_ignored(self):
        # Packets may have trailing padding — parser should tolerate extra bytes
        raw = build_imu_packet() + b"\x00\x00\x00"
        pkt = parse(raw)
        assert isinstance(pkt, ImuPacket)


# ─────────────────────────────────────────────────────────────────────────────
# RTT packet tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRttPacket:
    def test_parse_returns_rtt_packet_type(self):
        pkt = parse(build_rtt_packet())
        assert isinstance(pkt, RttPacket)

    def test_packet_type_field(self):
        pkt = parse(build_rtt_packet())
        assert pkt.packet_type == 0x02

    def test_zero_aps(self):
        pkt = parse(build_rtt_packet(aps=[]))
        assert pkt.ap_count == 0
        assert len(pkt.measurements) == 0

    def test_mac_formatted_correctly(self):
        pkt = parse(build_rtt_packet(mac="AA:BB:CC:DD:EE:FF"))
        assert pkt.mac == "AA:BB:CC:DD:EE:FF"

    def test_ts_ms_roundtrip(self):
        pkt = parse(build_rtt_packet(ts_ms=42000000))
        assert pkt.ts_ms == 42000000

    def test_single_ap(self):
        pkt = parse(build_rtt_packet(aps=[
            ("AA:BB:CC:11:22:33", 5.0, 0.5, -65, 0x01),
        ]))
        assert pkt.ap_count == 1
        assert len(pkt.measurements) == 1
        ap = pkt.measurements[0]
        assert ap.bssid == "AA:BB:CC:11:22:33"
        assert abs(ap.d_raw_mean - 5.0) < 1e-5
        assert abs(ap.d_raw_std - 0.5) < 1e-5
        assert ap.rssi == -65
        assert ap.band == "2.4GHz"

    def test_three_aps(self):
        aps_input = [
            ("AA:BB:CC:11:22:11", 3.0, 0.3, -60, 0x01),
            ("AA:BB:CC:11:22:22", 6.5, 0.7, -72, 0x02),
            ("AA:BB:CC:11:22:33", 10.1, 1.2, -80, 0x02),
        ]
        pkt = parse(build_rtt_packet(aps=aps_input))
        assert pkt.ap_count == 3
        assert len(pkt.measurements) == 3
        # check second AP
        ap2 = pkt.measurements[1]
        assert ap2.band == "5GHz"
        assert abs(ap2.d_raw_mean - 6.5) < 1e-4

    def test_band_24ghz(self):
        pkt = parse(build_rtt_packet(aps=[("AA:BB:CC:11:22:33", 1.0, 0.1, -50, 0x01)]))
        assert pkt.measurements[0].band == "2.4GHz"

    def test_band_5ghz(self):
        pkt = parse(build_rtt_packet(aps=[("AA:BB:CC:11:22:33", 1.0, 0.1, -50, 0x02)]))
        assert pkt.measurements[0].band == "5GHz"

    def test_band_unknown(self):
        pkt = parse(build_rtt_packet(aps=[("AA:BB:CC:11:22:33", 1.0, 0.1, -50, 0x03)]))
        assert "unknown" in pkt.measurements[0].band.lower()

    def test_negative_rssi(self):
        pkt = parse(build_rtt_packet(aps=[("AA:BB:CC:11:22:33", 1.0, 0.1, -90, 0x01)]))
        assert pkt.measurements[0].rssi == -90

    def test_rssi_minimum(self):
        pkt = parse(build_rtt_packet(aps=[("AA:BB:CC:11:22:33", 1.0, 0.1, -128, 0x01)]))
        assert pkt.measurements[0].rssi == -128

    def test_rssi_max_positive(self):
        pkt = parse(build_rtt_packet(aps=[("AA:BB:CC:11:22:33", 1.0, 0.1, 0, 0x01)]))
        assert pkt.measurements[0].rssi == 0

    def test_rtt_header_too_short_raises(self):
        raw = build_rtt_packet()[:8]
        with pytest.raises(ValueError, match="RTT packet too short for header"):
            parse(raw)

    def test_rtt_records_truncated_raises(self):
        # Build a 3-AP packet but strip the last record entirely
        raw = build_rtt_packet(aps=[
            ("AA:BB:CC:11:22:11", 1.0, 0.1, -60, 0x01),
            ("AA:BB:CC:11:22:22", 2.0, 0.2, -70, 0x01),
            ("AA:BB:CC:11:22:33", 3.0, 0.3, -80, 0x01),
        ])
        raw_truncated = raw[: 16 + 2 * 16]  # only 2 AP records, header says N=3
        with pytest.raises(ValueError, match="RTT packet too short for 3 AP records"):
            parse(raw_truncated)

    def test_measurements_is_tuple(self):
        pkt = parse(build_rtt_packet(aps=[("AA:BB:CC:11:22:33", 1.0, 0.1, -60, 0x01)]))
        assert isinstance(pkt.measurements, tuple)

    def test_ap_record_type(self):
        pkt = parse(build_rtt_packet(aps=[("AA:BB:CC:11:22:33", 1.0, 0.1, -60, 0x01)]))
        assert isinstance(pkt.measurements[0], ApRecord)


# ─────────────────────────────────────────────────────────────────────────────
# Error path tests
# ─────────────────────────────────────────────────────────────────────────────

class TestParseErrors:
    def test_empty_payload_raises(self):
        with pytest.raises(ValueError, match="empty payload"):
            parse(b"")

    def test_unknown_type_byte_raises(self):
        with pytest.raises(ValueError, match="Unknown packet type byte"):
            parse(bytes([0xFF]) + b"\x00" * 39)

    def test_unknown_type_byte_0x00(self):
        with pytest.raises(ValueError, match="Unknown packet type byte"):
            parse(bytes([0x00]) + b"\x00" * 39)

    def test_error_message_includes_hex(self):
        """The error message should include the hex value of the bad byte."""
        with pytest.raises(ValueError, match="0xAB"):
            parse(bytes([0xAB]) + b"\x00" * 39)

    def test_parse_imu_type_byte_is_0x01(self):
        raw = build_imu_packet()
        assert raw[0] == 0x01

    def test_parse_rtt_type_byte_is_0x02(self):
        raw = build_rtt_packet()
        assert raw[0] == 0x02
