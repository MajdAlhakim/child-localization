"""Pydantic request and response models for the ESP32-C5 gateway endpoint.

Wire format matches firmware/esp32c5/trakn_tag/trakn_tag.ino exactly.
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel


class ImuSampleIn(BaseModel):
    ts: int      # device timestamp, ms since boot
    ax: float    # accel X, m/s²
    ay: float    # accel Y, m/s²
    az: float    # accel Z, m/s²
    gx: float    # gyro X, rad/s
    gy: float    # gyro Y, rad/s
    gz: float    # gyro Z, rad/s


class WifiApIn(BaseModel):
    bssid: str   # AP BSSID, e.g. "aa:bb:cc:dd:ee:ff"
    ssid: str    # AP SSID
    rssi: int    # signal strength, dBm (signed)
    ch: int      # Wi-Fi channel (1–13 = 2.4 GHz, 36+ = 5 GHz)


class GatewayPacketRequest(BaseModel):
    mac: str                    # device MAC, e.g. "24:42:E3:15:E5:72"
    ts: int                     # packet timestamp, ms since boot
    imu: List[ImuSampleIn]      # IMU samples (up to 5 per packet at 50 ms cadence)
    wifi: List[WifiApIn] = []   # Wi-Fi RSSI scan results (empty between scans)


class GatewayPacketResponse(BaseModel):
    status: str
    imu_count: int
    wifi_count: int
    device_mac: str
