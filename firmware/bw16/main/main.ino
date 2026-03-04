// firmware/bw16/main/main.ino
// BW16 (Realtek RTL8720DN) — Unified sketch
// All three subsystems compiled and flashed together:
//   1. IMU reader       — TASK-05B (person-b, pending)
//   2. Wi-Fi RTT ranger — TASK-05B (person-b, pending)
//   3. Wi-Fi HTTPS sender — TASK-05C (person-b, implemented below)
//
// Flashing this sketch overwrites the entire device.
// Never flash subsystem files individually — they do not exist separately.

#include <WiFiClient.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include "Base64.h"           // Arduino Base64 library
#include "packet_format.h"

// ═══════════════════════════════════════════════════════════════════════════════
// SUBSYSTEM 1 — IMU READER (TASK-05B — placeholder, person-b to implement)
// MPU6050 at I2C address 0x68, 400 kHz
// Register config: PWR_MGMT_1=0x00, GYRO_CONFIG=0x08, ACCEL_CONFIG=0x08, CONFIG=0x04
// Accel: raw × 0.0011978149 m/s²    Gyro: raw × 0.0002663309 rad/s
// Sampling: 100 Hz (10 ms loop), read 14 bytes in one I2C burst from 0x3B
// Output: Type 0x01 IMU packet packed into imu_packet buffer
// ═══════════════════════════════════════════════════════════════════════════════

// placeholder — implement in TASK-05B


// ═══════════════════════════════════════════════════════════════════════════════
// SUBSYSTEM 2 — WI-FI RTT RANGER (TASK-05B — placeholder, person-b to implement)
// One-sided Wi-Fi RTT per AP BSSID using Realtek SDK
// Output: Type 0x02 RTT packet packed into rtt_packet buffer
// OQ-01: confirm Realtek SDK exposes per-BSSID one-sided FTM RTT before implementing
// ═══════════════════════════════════════════════════════════════════════════════

// placeholder — implement in TASK-05B


// ═══════════════════════════════════════════════════════════════════════════════
// SUBSYSTEM 3 — WI-FI HTTPS SENDER (TASK-05C — implemented)
// Connects BW16 to QU-User Wi-Fi (MAC 24:42:E3:15:E5:72 registered by IT).
// POSTs IMU (0x01) and RTT (0x02) packets to the cloud server via HTTPS on port 443.
//
// Endpoint: POST https://trakn.duckdns.org/api/v1/gateway/packet
// Header:   X-API-Key: <GATEWAY_API_KEY>
// Body:     { "device_mac": "24:42:E3:15:E5:72",
//             "rx_ts_utc":  "<ISO-8601>",
//             "payload_b64": "<base64>" }
//
// On POST failure: retry once after 500 ms.
// On Wi-Fi disconnect: reconnect every 5 s; buffer locally during outage.
// ═══════════════════════════════════════════════════════════════════════════════

// ── Wi-Fi credentials ─────────────────────────────────────────────────────────
static const char* WIFI_SSID = "QU-User";
static const char* WIFI_PASS = "";          // Open network — authenticated by MAC

// ── Server ────────────────────────────────────────────────────────────────────
static const char* SERVER_URL =
    "https://trakn.duckdns.org/api/v1/gateway/packet";
static const char* API_KEY    =
    "580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990";
static const char* DEVICE_MAC = "24:42:E3:15:E5:72";

// ── Local packet buffer (stores up to 30 s of IMU at 4 posts/s = 120 entries) ─
#define BUF_MAX 128
static uint8_t  _buf_data[BUF_MAX][PKT_IMU_LEN];
static uint16_t _buf_len [BUF_MAX];
static int      _buf_head = 0;
static int      _buf_tail = 0;
static int      _buf_count = 0;

static void buf_push(const uint8_t* data, uint16_t len) {
    if (_buf_count == BUF_MAX) return;           // drop oldest on overflow
    memcpy(_buf_data[_buf_tail], data, len);
    _buf_len[_buf_tail] = len;
    _buf_tail = (_buf_tail + 1) % BUF_MAX;
    _buf_count++;
}

// ── ISO-8601 timestamp (millis-based, no RTC) ─────────────────────────────────
static String iso8601_now() {
    // Without RTC, use a fixed epoch + millis offset.
    // Replace with NTP sync if available.
    unsigned long ms = millis();
    char buf[32];
    snprintf(buf, sizeof(buf), "2026-01-01T00:00:%02lu.%03luZ",
             (ms / 1000) % 60, ms % 1000);
    return String(buf);
}

// ── HTTP POST helper ──────────────────────────────────────────────────────────
static bool post_packet(const uint8_t* data, uint16_t len) {
    if (WiFi.status() != WL_CONNECTED) return false;

    // Base64-encode the binary payload
    String b64 = base64::encode(data, len);

    // Build JSON body
    String body = "{\"device_mac\":\"";
    body += DEVICE_MAC;
    body += "\",\"rx_ts_utc\":\"";
    body += iso8601_now();
    body += "\",\"payload_b64\":\"";
    body += b64;
    body += "\"}";

    HTTPClient https;
    https.begin(SERVER_URL);
    https.addHeader("Content-Type", "application/json");
    https.addHeader("X-API-Key", API_KEY);

    int code = https.POST(body);
    https.end();

    return (code == 200 || code == 201 || code == 204);
}

// ── Wi-Fi reconnect ───────────────────────────────────────────────────────────
static unsigned long _last_wifi_attempt = 0;

static void ensure_wifi() {
    if (WiFi.status() == WL_CONNECTED) return;
    unsigned long now = millis();
    if (now - _last_wifi_attempt < 5000) return;
    _last_wifi_attempt = now;
    Serial.println("[WiFi] Reconnecting...");
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASS);
}

static void wifi_sender_setup() {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("[WiFi] Connecting to ");
    Serial.println(WIFI_SSID);
    unsigned long deadline = millis() + 15000;
    while (WiFi.status() != WL_CONNECTED && millis() < deadline) {
        delay(200);
        Serial.print('.');
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[WiFi] Connected. IP: " + WiFi.localIP().toString());
    } else {
        Serial.println("\n[WiFi] Failed — will retry every 5 s");
    }
}

// Call this from the main loop with a fully-formed IMU or RTT packet.
static void wifi_sender_send(const uint8_t* pkt, uint16_t len) {
    ensure_wifi();

    // Flush any buffered packets first (oldest first)
    while (_buf_count > 0) {
        const uint8_t* d = _buf_data[_buf_head];
        uint16_t l = _buf_len[_buf_head];
        if (!post_packet(d, l)) {
            buf_push(pkt, len);   // also buffer the new packet, give up for now
            return;
        }
        _buf_head = (_buf_head + 1) % BUF_MAX;
        _buf_count--;
    }

    // Send the new packet
    if (!post_packet(pkt, len)) {
        delay(500);
        if (!post_packet(pkt, len)) {
            buf_push(pkt, len);  // buffer for later
        }
    }
}


// ═══════════════════════════════════════════════════════════════════════════════
// ARDUINO ENTRY POINTS
// ═══════════════════════════════════════════════════════════════════════════════

void setup() {
    Serial.begin(115200);
    // TODO (TASK-05B): imu_setup();
    // TODO (TASK-05B): rtt_setup();
    wifi_sender_setup();
}

void loop() {
    // TODO (TASK-05B): read IMU, pack Type 0x01 packet, call wifi_sender_send()
    // TODO (TASK-05B): run RTT ranging, pack Type 0x02 packet, call wifi_sender_send()
    delay(10);  // 100 Hz loop placeholder
}
