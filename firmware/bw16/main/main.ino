// firmware/bw16/main/main.ino
// BW16 (Realtek RTL8720DN) — Unified sketch
// All three subsystems compiled and flashed together:
//   1. IMU reader       — TASK-05B (implemented below)
//   2. Wi-Fi RTT ranger — TASK-05B (stub — OQ-01 unresolved, see below)
//   3. Wi-Fi HTTPS sender — TASK-05C (implemented below)
//
// Flashing this sketch overwrites the entire device.
// Never flash subsystem files individually — they do not exist separately.
//
// SDK DEVIATIONS FROM STANDARD ARDUINO (Realtek Ameba Arduino SDK):
//   - WiFi.h on AmebaD provides WiFiSSLClient (not HTTPClient)
//   - Wire.h is the Realtek Ameba Wire for I2C on RTL8720DN
//   - millis() and delay() behave as standard Arduino
//   - Serial.begin() uses UART0 at 115200 baud

// ── Includes ──────────────────────────────────────────────────────────────────
#include <Wire.h>
#include <WiFi.h>   // Provides WiFiSSLClient on Realtek AmebaD SDK
#include <stdint.h>

// ═══════════════════════════════════════════════════════════════════════════════
// PACKET FORMAT — LOCKED (workspace rules §7 / PRD §15)
// (Formerly in packet_format.h — inlined here to avoid Arduino IDE include issues)
// ═══════════════════════════════════════════════════════════════════════════════

// ── Type 0x01 — IMU Packet (fixed 40 bytes, little-endian) ───────────────────
#define PKT_IMU_LEN        40
#define PKT_IMU_TYPE_OFFSET  0
#define PKT_IMU_MAC_OFFSET   1
#define PKT_IMU_TS_OFFSET    7
#define PKT_IMU_AX_OFFSET   15
#define PKT_IMU_AY_OFFSET   19
#define PKT_IMU_AZ_OFFSET   23
#define PKT_IMU_GX_OFFSET   27
#define PKT_IMU_GY_OFFSET   31
#define PKT_IMU_GZ_OFFSET   35
#define PKT_IMU_SEQ_OFFSET  39

#pragma pack(push, 1)
typedef struct {
    uint8_t  type;      // [0]     0x01
    uint8_t  mac[6];    // [1-6]   device MAC
    uint64_t ts_ms;     // [7-14]  timestamp ms since boot
    float    ax;        // [15-18] accel X, m/s²
    float    ay;        // [19-22] accel Y, m/s²
    float    az;        // [23-26] accel Z, m/s²
    float    gx;        // [27-30] gyro X, rad/s
    float    gy;        // [31-34] gyro Y, rad/s
    float    gz;        // [35-38] gyro Z, rad/s
    uint8_t  seq;       // [39]    sequence counter
} imu_packet_t;
#pragma pack(pop)

// ── Type 0x02 — RTT Packet (variable length, little-endian) ──────────────────
#define PKT_RTT_HDR_LEN       16   // header including ap_count byte
#define PKT_RTT_RECORD_LEN    16   // per-AP record
#define PKT_RTT_TOTAL_LEN(n)  (PKT_RTT_HDR_LEN + (n) * PKT_RTT_RECORD_LEN)
#define PKT_RTT_MAX_APS       16

#define PKT_BAND_2G4  0x01
#define PKT_BAND_5G   0x02

#pragma pack(push, 1)
typedef struct {
    uint8_t  bssid[6];   // [0-5]   AP BSSID
    float    d_raw_mean; // [6-9]   mean RTT distance, metres
    float    d_raw_std;  // [10-13] std dev, metres
    int8_t   rssi;       // [14]    RSSI dBm (signed)
    uint8_t  band;       // [15]    0x01=2.4GHz, 0x02=5GHz
} rtt_ap_record_t;
#pragma pack(pop)

#pragma pack(push, 1)
typedef struct {
    uint8_t  type;      // [0]     0x02
    uint8_t  mac[6];    // [1-6]   device MAC
    uint64_t ts_ms;     // [7-14]  timestamp
    uint8_t  ap_count;  // [15]    number of AP records that follow
} rtt_packet_hdr_t;
#pragma pack(pop)

#define rtt_record_ptr(buf, i) \
    ((rtt_ap_record_t*)((uint8_t*)(buf) + PKT_RTT_HDR_LEN + (i) * PKT_RTT_RECORD_LEN))


// ── Self-contained Base64 encoder (no external library needed) ────────────────
static const char _b64_chars[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static String base64_encode(const uint8_t* data, uint16_t len) {
    String out;
    out.reserve(((len + 2) / 3) * 4 + 1);
    for (uint16_t i = 0; i < len; i += 3) {
        uint8_t b0 = data[i];
        uint8_t b1 = (i + 1 < len) ? data[i + 1] : 0;
        uint8_t b2 = (i + 2 < len) ? data[i + 2] : 0;
        out += _b64_chars[ b0 >> 2];
        out += _b64_chars[(b0 & 0x03) << 4 | b1 >> 4];
        out += (i + 1 < len) ? _b64_chars[(b1 & 0x0F) << 2 | b2 >> 6] : '=';
        out += (i + 2 < len) ? _b64_chars[ b2 & 0x3F]                  : '=';
    }
    return out;
}


// ═══════════════════════════════════════════════════════════════════════════════
// SUBSYSTEM 1 — IMU READER (TASK-05B)
// MPU6050 at I2C address 0x68, 400 kHz
//
// Register configuration (LOCKED — workspace rules §6):
//   PWR_MGMT_1  = 0x00  (wake, internal oscillator)
//   GYRO_CONFIG = 0x08  (±500 °/s  → 65.5 LSB/°/s)
//   ACCEL_CONFIG= 0x08  (±4 g      → 8192 LSB/g)
//   CONFIG      = 0x04  (DLPF = 21 Hz)
//
// Conversion constants (LOCKED):
//   Accel: raw × 0.0011978149 m/s²
//   Gyro:  raw × 0.0002663309 rad/s
// ═══════════════════════════════════════════════════════════════════════════════

#define MPU6050_ADDR         0x68
#define MPU6050_REG_CONFIG   0x1A
#define MPU6050_REG_GYROCFG  0x1B
#define MPU6050_REG_ACCELCFG 0x1C
#define MPU6050_REG_PWRMGMT  0x6B
#define MPU6050_REG_DATA     0x3B   // ACCEL_XOUT_H — first of 14 data bytes

static const double ACCEL_SCALE = 0.0011978149;  // raw → m/s²  (LOCKED)
static const double GYRO_SCALE  = 0.0002663309;  // raw → rad/s (LOCKED)

static imu_packet_t _imu_pkt;
static uint8_t      _imu_seq   = 0;
static bool         _imu_ready = false;

static uint8_t _device_mac[6] = {0x24, 0x42, 0xE3, 0x15, 0xE5, 0x72};

static void mpu_write(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(reg);
    Wire.write(val);
    Wire.endTransmission();
}

static void imu_setup() {
    Wire.begin();
    Wire.setClock(400000);
    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(MPU6050_REG_PWRMGMT);
    Wire.write(0x00);
    uint8_t err = Wire.endTransmission();
    if (err != 0) {
        Serial.print("[IMU] FATAL: MPU6050 not found (err=");
        Serial.print(err);
        Serial.println("). Halting.");
        while (true) delay(1000);
    }
    mpu_write(MPU6050_REG_CONFIG,   0x04);  // DLPF = 21 Hz
    mpu_write(MPU6050_REG_GYROCFG,  0x08);  // ±500 °/s
    mpu_write(MPU6050_REG_ACCELCFG, 0x08);  // ±4 g
    Serial.println("[IMU] MPU6050 ok: ±4g/±500dps/21Hz DLPF");
    _imu_pkt.type = 0x01;
    memcpy(_imu_pkt.mac, _device_mac, 6);
}

static void imu_read() {
    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(MPU6050_REG_DATA);
    if (Wire.endTransmission(false) != 0) { return; }
    uint8_t n = Wire.requestFrom((uint8_t)MPU6050_ADDR, (uint8_t)14);
    if (n < 14) { return; }
    int16_t raw[7];
    for (int i = 0; i < 7; i++) {
        raw[i] = (int16_t)((Wire.read() << 8) | Wire.read());
    }
    _imu_pkt.ts_ms = (uint64_t)millis();
    _imu_pkt.ax    = (float)(raw[0] * ACCEL_SCALE);
    _imu_pkt.ay    = (float)(raw[1] * ACCEL_SCALE);
    _imu_pkt.az    = (float)(raw[2] * ACCEL_SCALE);
    _imu_pkt.gx    = (float)(raw[4] * GYRO_SCALE);
    _imu_pkt.gy    = (float)(raw[5] * GYRO_SCALE);
    _imu_pkt.gz    = (float)(raw[6] * GYRO_SCALE);
    _imu_pkt.seq   = _imu_seq++;
    _imu_ready = true;
}


// ═══════════════════════════════════════════════════════════════════════════════
// SUBSYSTEM 2 — WI-FI RTT RANGER (TASK-05B — STUB, OQ-01 unresolved)
//
// [OQ-01] Does the Realtek RTL8720DN SDK expose per-BSSID one-sided FTM RTT?
// Until confirmed, this subsystem sends 0-AP RTT packets.
// ACTION: Inspect Arduino15 packages/realtek/hardware/AmebaD/
//   for rtw_wifi_api.h or FTM references. Replace rtt_read() when resolved.
// ═══════════════════════════════════════════════════════════════════════════════

static const uint8_t KNOWN_APS[][6] = {
    // {0xAA, 0xBB, 0xCC, 0x11, 0x22, 0x33},  // insert real BSSIDs after survey
};
static const int NUM_KNOWN_APS = 0;

static uint8_t   _rtt_buf[PKT_RTT_TOTAL_LEN(PKT_RTT_MAX_APS)];
static uint16_t  _rtt_buf_len = 0;
static bool      _rtt_ready   = false;

static void rtt_setup() {
    Serial.println("[RTT] OQ-01 unresolved — stub active (0-AP packets)");
}

static void rtt_read() {
    rtt_packet_hdr_t* hdr = (rtt_packet_hdr_t*)_rtt_buf;
    hdr->type     = 0x02;
    memcpy(hdr->mac, _device_mac, 6);
    hdr->ts_ms    = (uint64_t)millis();
    hdr->ap_count = 0;
    _rtt_buf_len  = PKT_RTT_HDR_LEN;
    _rtt_ready    = true;
}


// ═══════════════════════════════════════════════════════════════════════════════
// SUBSYSTEM 3 — WI-FI HTTPS SENDER (TASK-05C)
// Connects BW16 to QU-User Wi-Fi, POSTs binary packets to trakn.duckdns.org:443
// ═══════════════════════════════════════════════════════════════════════════════

static const char* WIFI_SSID   = "medhat_nokia";
static const char* WIFI_PASS   = "55055135";   // TEMP: home network — revert to QU-User/"" before QU deployment

static const char* SERVER_HOST = "trakn.duckdns.org";
static const char* SERVER_PATH = "/api/v1/gateway/packet";
static const char* API_KEY     =
    "580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990";
static const char* DEVICE_MAC  = "24:42:E3:15:E5:72";

// Local ring buffer — stores up to 128 packets during Wi-Fi outage
#define BUF_MAX 128
static uint8_t  _buf_data[BUF_MAX][PKT_IMU_LEN];
static uint16_t _buf_len[BUF_MAX];
static int      _buf_head = 0, _buf_tail = 0, _buf_count = 0;

static void buf_push(const uint8_t* data, uint16_t len) {
    if (_buf_count == BUF_MAX) return;
    if (len > PKT_IMU_LEN) len = PKT_IMU_LEN;
    memcpy(_buf_data[_buf_tail], data, len);
    _buf_len[_buf_tail] = len;
    _buf_tail = (_buf_tail + 1) % BUF_MAX;
    _buf_count++;
}

static String iso8601_now() {
    unsigned long ms = millis();
    char buf[32];
    snprintf(buf, sizeof(buf), "2026-01-01T00:00:%02lu.%03luZ",
             (ms / 1000) % 60, ms % 1000);
    return String(buf);
}

static bool post_packet(const uint8_t* data, uint16_t len) {
    if (WiFi.status() != WL_CONNECTED) return false;

    String b64  = base64_encode(data, len);
    String body = "{\"device_mac\":\"";
    body += DEVICE_MAC;
    body += "\",\"rx_ts_utc\":\"";
    body += iso8601_now();
    body += "\",\"payload_b64\":\"";
    body += b64;
    body += "\"}";

    WiFiSSLClient client;
    if (!client.connect(SERVER_HOST, 443)) {
        Serial.println("[HTTP] TLS connect failed");
        return false;
    }

    client.println("POST " + String(SERVER_PATH) + " HTTP/1.1");
    client.println("Host: " + String(SERVER_HOST));
    client.println("Content-Type: application/json");
    client.println("X-API-Key: " + String(API_KEY));
    client.println("Content-Length: " + String(body.length()));
    client.println("Connection: close");
    client.println();
    client.print(body);

    unsigned long deadline = millis() + 5000;
    while (!client.available() && millis() < deadline) delay(10);
    String statusLine = client.readStringUntil('\n');
    client.stop();

    return (statusLine.indexOf(" 200 ") != -1 ||
            statusLine.indexOf(" 201 ") != -1 ||
            statusLine.indexOf(" 202 ") != -1 ||
            statusLine.indexOf(" 204 ") != -1);
}

static unsigned long _last_wifi_attempt = 0;

static void ensure_wifi() {
    if (WiFi.status() == WL_CONNECTED) return;
    if (millis() - _last_wifi_attempt < 5000) return;
    _last_wifi_attempt = millis();
    Serial.println("[WiFi] Reconnecting...");
    WiFi.disconnect();
    WiFi.begin(const_cast<char*>(WIFI_SSID), const_cast<char*>(WIFI_PASS));
}

static void wifi_sender_setup() {
    WiFi.begin(const_cast<char*>(WIFI_SSID), const_cast<char*>(WIFI_PASS));
    Serial.print("[WiFi] Connecting to QU-User");
    unsigned long deadline = millis() + 15000;
    while (WiFi.status() != WL_CONNECTED && millis() < deadline) {
        delay(200); Serial.print('.');
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.print("\n[WiFi] Connected. IP: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("\n[WiFi] Failed — will retry every 5 s");
    }
}

static void wifi_sender_send(const uint8_t* pkt, uint16_t len) {
    ensure_wifi();
    while (_buf_count > 0) {
        if (!post_packet(_buf_data[_buf_head], _buf_len[_buf_head])) {
            buf_push(pkt, len);
            return;
        }
        _buf_head = (_buf_head + 1) % BUF_MAX;
        _buf_count--;
    }
    if (!post_packet(pkt, len)) {
        delay(500);
        if (!post_packet(pkt, len)) buf_push(pkt, len);
    }
}


// ═══════════════════════════════════════════════════════════════════════════════
// ARDUINO ENTRY POINTS
// ═══════════════════════════════════════════════════════════════════════════════

static unsigned long _last_imu_ms = 0;
static unsigned long _last_rtt_ms = 0;

void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.println("[BOOT] BW16 starting...");
    wifi_sender_setup();
    imu_setup();
    rtt_setup();
    _last_imu_ms = _last_rtt_ms = millis();
    Serial.println("[BOOT] All subsystems initialised.");
}

void loop() {
    unsigned long now = millis();

    // IMU at 100 Hz (every 10 ms)
    if (now - _last_imu_ms >= 10) {
        _last_imu_ms = now;
        imu_read();
        if (_imu_ready) {
            wifi_sender_send((const uint8_t*)&_imu_pkt, (uint16_t)sizeof(_imu_pkt));
        }
    }

    // RTT at 2 Hz (every 500 ms) — stub until OQ-01 resolved
    if (now - _last_rtt_ms >= 500) {
        _last_rtt_ms = now;
        rtt_read();
        if (_rtt_ready) {
            wifi_sender_send(_rtt_buf, _rtt_buf_len);
            _rtt_ready = false;
        }
    }
}
