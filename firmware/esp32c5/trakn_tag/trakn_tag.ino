// firmware/esp32c5/trakn_tag.ino
// XIAO ESP32-C5 — Unified TRAKN Tag Firmware
//
// Hardware: XIAO ESP32-C5 + MPU6050 IMU
// Board package: esp32 by Espressif Systems v3.3.5+
// Board selection: Tools → Board → esp32 → XIAO_ESP32C5
// USB CDC On Boot: Enabled
//
// Architecture: 3 FreeRTOS tasks
//   1. imu_task      (priority 5) — reads MPU6050 at 100 Hz, batches samples
//   2. wifi_scan_task (priority 3) — connects to Wi-Fi, async RSSI scan ~11s
//   3. post_task     (priority 2) — drains IMU batch every 50ms, POSTs JSON
//
// Packet format (JSON over HTTPS POST):
// {
//   "mac":  "24:42:E3:15:E5:72",
//   "ts":   12450,
//   "imu":  [{"ts":...,"ax":...,"ay":...,"az":...,"gx":...,"gy":...,"gz":...},...],
//   "wifi": [{"bssid":"...","ssid":"...","rssi":-46,"ch":6},...]
// }
// imu[] contains up to 5 samples per packet (sent every 50 ms = 20 packets/sec)
// wifi[] contains latest RSSI scan results (~every 11 s), empty [] between scans

#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

// ── Network config ────────────────────────────────────────────────────────────
#define WIFI_SSID       "QU User"          // MAC already registered with QU IT
#define SERVER_URL      "https://35.238.189.188/api/v1/gateway/packet"
#define DEVICE_MAC      "24:42:E3:15:E5:72"
#define API_KEY         "580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990"

// ── IMU constants (LOCKED — verified in SDP1, never change) ──────────────────
#define MPU6050_ADDR   0x68
#define PWR_MGMT_1     0x6B
#define GYRO_CONFIG    0x1B
#define ACCEL_CONFIG   0x1C
#define CONFIG_REG     0x1A
#define ACCEL_XOUT_H   0x3B
#define ACCEL_SCALE    0.0011978149f   // raw → m/s²  (= raw × 9.81 / 8192, ±4g)
#define GYRO_SCALE     0.0002663309f   // raw → rad/s (= raw × π / (180 × 65.5))

// ── Shared state ──────────────────────────────────────────────────────────────
struct APRecord {
  char    ssid[33];
  char    bssid[18];
  int32_t rssi;
  int32_t channel;
};

struct ImuSample {
  unsigned long ts;
  float ax, ay, az;
  float gx, gy, gz;
};

#define MAX_APS        20
#define IMU_BATCH_SIZE 5    // 5 samples per packet at 50ms = 20 packets/sec

static APRecord          ap_list[MAX_APS];
static int               ap_count   = 0;
static bool              scan_ready = false;
static SemaphoreHandle_t scan_mutex  = NULL;

static ImuSample         imu_batch[IMU_BATCH_SIZE];
static int               imu_batch_idx = 0;
static SemaphoreHandle_t imu_mutex  = NULL;

static bool              wifi_connected = false;

// ── IMU helpers ───────────────────────────────────────────────────────────────
static void writeReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission((uint8_t)MPU6050_ADDR);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission(true);
}

static void imu_init() {
  Wire.begin();
  Wire.setClock(400000);
  delay(200);
  writeReg(PWR_MGMT_1,   0x00); delay(100);
  writeReg(GYRO_CONFIG,  0x08);
  writeReg(ACCEL_CONFIG, 0x08);
  writeReg(CONFIG_REG,   0x04);
  delay(100);
  Serial.println("[IMU] ready");
}

// ── IMU task — 100 Hz, batches 5 samples ─────────────────────────────────────
static void imu_task(void *arg) {
  TickType_t last = xTaskGetTickCount();
  while (1) {
    Wire.beginTransmission((uint8_t)MPU6050_ADDR);
    Wire.write(ACCEL_XOUT_H);
    Wire.endTransmission(false);
    uint8_t n = Wire.requestFrom((uint8_t)MPU6050_ADDR, (uint8_t)14, (bool)true);

    if (n == 14) {
      int16_t ax_r = (int16_t)((Wire.read() << 8) | Wire.read());
      int16_t ay_r = (int16_t)((Wire.read() << 8) | Wire.read());
      int16_t az_r = (int16_t)((Wire.read() << 8) | Wire.read());
      Wire.read(); Wire.read();  // skip temp
      int16_t gx_r = (int16_t)((Wire.read() << 8) | Wire.read());
      int16_t gy_r = (int16_t)((Wire.read() << 8) | Wire.read());
      int16_t gz_r = (int16_t)((Wire.read() << 8) | Wire.read());

      if (xSemaphoreTake(imu_mutex, 0) == pdTRUE) {
        if (imu_batch_idx < IMU_BATCH_SIZE) {
          imu_batch[imu_batch_idx] = {
            millis(),
            ax_r * ACCEL_SCALE, ay_r * ACCEL_SCALE, az_r * ACCEL_SCALE,
            gx_r * GYRO_SCALE,  gy_r * GYRO_SCALE,  gz_r * GYRO_SCALE
          };
          imu_batch_idx++;
        }
        xSemaphoreGive(imu_mutex);
      }
    }
    vTaskDelayUntil(&last, pdMS_TO_TICKS(10));
  }
}

// ── Wi-Fi scan task ───────────────────────────────────────────────────────────
static void wifi_scan_task(void *arg) {
  // Connect to QU User (open network, MAC-authenticated, no password)
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID);

  Serial.print("[WIFI] connecting to ");
  Serial.println(WIFI_SSID);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 150) {
    vTaskDelay(pdMS_TO_TICKS(100));
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    wifi_connected = true;
    Serial.print("[WIFI] connected, IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[WIFI] connection failed — will retry");
  }

  // Kick off first async scan immediately
  WiFi.scanNetworks(/*async=*/true);

  while (1) {
    // Reconnect if dropped
    if (WiFi.status() != WL_CONNECTED) {
      wifi_connected = false;
      Serial.println("[WIFI] reconnecting...");
      WiFi.reconnect();
      vTaskDelay(pdMS_TO_TICKS(3000));
      continue;
    }
    wifi_connected = true;

    int n = WiFi.scanComplete();

    if (n == WIFI_SCAN_RUNNING) {
      vTaskDelay(pdMS_TO_TICKS(500));
      continue;
    }

    if (n == WIFI_SCAN_FAILED || n < 0) {
      WiFi.scanNetworks(/*async=*/true);
      vTaskDelay(pdMS_TO_TICKS(500));
      continue;
    }

    // Scan done — store results
    if (xSemaphoreTake(scan_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
      ap_count   = (n > MAX_APS) ? MAX_APS : n;
      scan_ready = false;
      for (int i = 0; i < ap_count; i++) {
        strncpy(ap_list[i].ssid,  WiFi.SSID(i).c_str(), 32);
        ap_list[i].ssid[32] = '\0';
        strncpy(ap_list[i].bssid, WiFi.BSSIDstr(i).c_str(), 17);
        ap_list[i].bssid[17] = '\0';
        ap_list[i].rssi    = WiFi.RSSI(i);
        ap_list[i].channel = WiFi.channel(i);
      }
      WiFi.scanDelete();
      scan_ready = true;
      xSemaphoreGive(scan_mutex);
    }

    // Immediately start next scan — takes ~11s naturally
    WiFi.scanNetworks(/*async=*/true);
  }
}

// ── POST task — sends batched IMU + latest WiFi scan ──────────────────────────
static void post_task(void *arg) {
  while (!wifi_connected) {
    vTaskDelay(pdMS_TO_TICKS(500));
  }
  Serial.println("[POST] task started");

  // Persistent TLS client — one handshake, many requests
  WiFiClientSecure client;
  client.setInsecure();   // skip cert verification (self-signed cert on server)

  while (1) {
    vTaskDelay(pdMS_TO_TICKS(50));   // 50ms = up to 20 packets/sec

    if (!wifi_connected) continue;

    // Drain whatever IMU samples exist
    ImuSample batch_copy[IMU_BATCH_SIZE];
    int batch_size = 0;

    if (xSemaphoreTake(imu_mutex, pdMS_TO_TICKS(20)) == pdTRUE) {
      batch_size = imu_batch_idx;
      memcpy(batch_copy, imu_batch, sizeof(ImuSample) * batch_size);
      imu_batch_idx = 0;
      xSemaphoreGive(imu_mutex);
    }

    if (batch_size == 0) continue;

    // Snapshot WiFi scan (only when fresh scan available)
    APRecord ap_copy[MAX_APS];
    int ap_copy_count = 0;
    bool has_wifi = false;

    if (xSemaphoreTake(scan_mutex, pdMS_TO_TICKS(20)) == pdTRUE) {
      if (scan_ready) {
        memcpy(ap_copy, ap_list, sizeof(APRecord) * ap_count);
        ap_copy_count = ap_count;
        has_wifi = true;
        scan_ready = false;  // consume it
      }
      xSemaphoreGive(scan_mutex);
    }

    // Build JSON packet
    String json = "{";
    json += "\"mac\":\"" DEVICE_MAC "\",";
    json += "\"ts\":" + String(millis()) + ",";

    // IMU array
    json += "\"imu\":[";
    for (int i = 0; i < batch_size; i++) {
      json += "{\"ts\":" + String(batch_copy[i].ts) + ",";
      json += "\"ax\":" + String(batch_copy[i].ax, 4) + ",";
      json += "\"ay\":" + String(batch_copy[i].ay, 4) + ",";
      json += "\"az\":" + String(batch_copy[i].az, 4) + ",";
      json += "\"gx\":" + String(batch_copy[i].gx, 4) + ",";
      json += "\"gy\":" + String(batch_copy[i].gy, 4) + ",";
      json += "\"gz\":" + String(batch_copy[i].gz, 4) + "}";
      if (i < batch_size - 1) json += ",";
    }
    json += "],";

    // WiFi array (only populated when fresh scan is available)
    json += "\"wifi\":[";
    if (has_wifi) {
      for (int i = 0; i < ap_copy_count; i++) {
        json += "{\"bssid\":\"" + String(ap_copy[i].bssid) + "\",";
        json += "\"ssid\":\"" + String(ap_copy[i].ssid) + "\",";
        json += "\"rssi\":" + String(ap_copy[i].rssi) + ",";
        json += "\"ch\":" + String(ap_copy[i].channel) + "}";
        if (i < ap_copy_count - 1) json += ",";
      }
    }
    json += "]}";

    // POST with persistent TLS client + keep-alive
    HTTPClient http;
    http.begin(client, SERVER_URL);
    http.setReuse(true);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-Key", API_KEY);
    http.addHeader("Connection", "keep-alive");
    http.setTimeout(2000);

    int code = http.POST(json);

    if (code > 0) {
      Serial.printf("[POST] %d — %d bytes, wifi=%s\n",
        code, json.length(), has_wifi ? "yes" : "no");
    } else {
      Serial.printf("[POST] failed: %s\n", http.errorToString(code).c_str());
    }

    http.end();
  }
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("[TRAKN] starting...");

  scan_mutex = xSemaphoreCreateMutex();
  imu_mutex  = xSemaphoreCreateMutex();
  configASSERT(scan_mutex);
  configASSERT(imu_mutex);

  imu_init();

  // Single-core ESP32-C5: use xTaskCreate, NOT xTaskCreatePinnedToCore
  xTaskCreate(imu_task,       "imu",    8192,  NULL, 5, NULL);
  xTaskCreate(wifi_scan_task, "wscan",  16384, NULL, 3, NULL);
  xTaskCreate(post_task,      "post",   16384, NULL, 2, NULL);
}

void loop() {
  vTaskDelay(portMAX_DELAY);
}
