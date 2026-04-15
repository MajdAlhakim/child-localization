// firmware/esp32c5/trakn_tag.ino
// XIAO ESP32-C5 — TRAKN Tag Firmware (two-board architecture)
//
// Hardware: XIAO ESP32-C5 + MPU6050 IMU + Beetle ESP32-C6 (via UART)
// Board package: esp32 by Espressif Systems v3.3.5+
// Board selection: Tools → Board → esp32 → XIAO_ESP32C5
// USB CDC On Boot: Enabled
//
// Two-board architecture:
//   Beetle ESP32-C6 (beetle_c6_scanner.ino) — dedicated Wi-Fi scanner
//     → scans every 10s, no radio contention with TCP
//     → sends {"wifi":[{"bssid":"...","ssid":"...","rssi":-46,"ch":6},...]}
//     over UART
//   This board — IMU sampling + HTTP POST only
//     → radio 100% dedicated to TCP/TLS, never scans
//     → zero scan blackouts, zero TLS timeouts
//
// UART wiring:
//   Beetle ESP32-C6 GPIO16 (TX) → XIAO ESP32-C5 GPIO12 (D7 / RX)
//   Beetle ESP32-C6 GND         → XIAO ESP32-C5 GND
//
// FreeRTOS tasks (single-core ESP32-C5 — xTaskCreate only):
//   imu_task   (priority 5) — MPU6050 at 100Hz, fills ring buffer
//   uart_task  (priority 3) — reads JSON from Beetle C6, updates ap_list
//   wifi_task  (priority 3) — maintains Wi-Fi station connection
//   post_task  (priority 2) — drains IMU, POSTs JSON every 200ms

#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>

// ── Network config
// ────────────────────────────────────────────────────────────
#define WIFI_SSID "QU User"   // actual SSID — verify with scan (may be "QU User" with space)
#define WIFI_PASS ""          
#define SERVER_URL "https://35.238.189.188/api/v1/gateway/packet"
#define DEVICE_MAC "24:42:E3:15:E5:72"
#define API_KEY                                                                \
  "580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990"

// ── IMU constants (LOCKED — verified in SDP1, never change) ──────────────────
#define MPU6050_ADDR 0x68
#define PWR_MGMT_1 0x6B
#define GYRO_CONFIG 0x1B
#define ACCEL_CONFIG 0x1C
#define CONFIG_REG 0x1A
#define ACCEL_XOUT_H 0x3B
#define ACCEL_SCALE 0.0011978149f
#define GYRO_SCALE 0.0002663309f

// ── Sizing
// ────────────────────────────────────────────────────────────────────
#define MAX_APS 30
#define IMU_BATCH_SIZE 25
#define IMU_DRAIN_SIZE 25
#define POST_INTERVAL_MS 200

// ── UART (from Beetle ESP32-C6)
// ───────────────────────────────────────────────
#define UART_RX_PIN 12 // GPIO12 = D7 on XIAO ESP32-C5
#define UART_TX_PIN 11 // GPIO11 = D6 (unused — C6 never receives)
#define UART_BAUD 115200
#define UART_BUF_SIZE 3072 // 30 APs × ~80 bytes each = ~2400 bytes max line

// ── Structs
// ───────────────────────────────────────────────────────────────────
struct APRecord {
  char bssid[18]; // "AA:BB:CC:DD:EE:FF\0"
  char ssid[33];  // up to 32 chars + null
  int32_t rssi;
  int32_t channel;
};

struct ImuSample {
  unsigned long ts;
  float ax, ay, az;
  float gx, gy, gz;
};

// ── Shared state
// ──────────────────────────────────────────────────────────────
static APRecord ap_list[MAX_APS];
static int ap_count = 0;
static bool ap_fresh = false;
static SemaphoreHandle_t ap_mutex = NULL;

static ImuSample imu_batch[IMU_BATCH_SIZE];
static int imu_batch_idx = 0;
static SemaphoreHandle_t imu_mutex = NULL;

static bool wifi_connected = false;

// ── IMU helpers
// ───────────────────────────────────────────────────────────────
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
  writeReg(PWR_MGMT_1, 0x00);
  delay(100);
  writeReg(GYRO_CONFIG, 0x08);
  writeReg(ACCEL_CONFIG, 0x08);
  writeReg(CONFIG_REG, 0x04);
  delay(100);
  Serial.println("[IMU] ready");
}

// ── IMU task — 100 Hz
// ─────────────────────────────────────────────────────────
static void imu_task(void *arg) {
  TickType_t last = xTaskGetTickCount();
  while (1) {
    Wire.beginTransmission((uint8_t)MPU6050_ADDR);
    Wire.write(ACCEL_XOUT_H);
    Wire.endTransmission(false);
    uint8_t n =
        Wire.requestFrom((uint8_t)MPU6050_ADDR, (uint8_t)14, (bool)true);

    if (n == 14) {
      int16_t ax_r = (int16_t)((Wire.read() << 8) | Wire.read());
      int16_t ay_r = (int16_t)((Wire.read() << 8) | Wire.read());
      int16_t az_r = (int16_t)((Wire.read() << 8) | Wire.read());
      Wire.read();
      Wire.read();
      int16_t gx_r = (int16_t)((Wire.read() << 8) | Wire.read());
      int16_t gy_r = (int16_t)((Wire.read() << 8) | Wire.read());
      int16_t gz_r = (int16_t)((Wire.read() << 8) | Wire.read());

      if (xSemaphoreTake(imu_mutex, 0) == pdTRUE) {
        if (imu_batch_idx < IMU_BATCH_SIZE) {
          imu_batch[imu_batch_idx] = {millis(),           ax_r * ACCEL_SCALE,
                                      ay_r * ACCEL_SCALE, az_r * ACCEL_SCALE,
                                      gx_r * GYRO_SCALE,  gy_r * GYRO_SCALE,
                                      gz_r * GYRO_SCALE};
          imu_batch_idx++;
        }
        xSemaphoreGive(imu_mutex);
      }
    }
    vTaskDelayUntil(&last, pdMS_TO_TICKS(10));
  }
}

// ── UART task — reads JSON lines from Beetle ESP32-C6 ────────────────────────
//
// Parses:
// {"wifi":[{"bssid":"AA:BB:CC:DD:EE:FF","ssid":"Name","rssi":-46,"ch":6},...]}
//
// Uses plain C string parsing — no JSON library needed.
// All fields are present and in fixed order as generated by
// beetle_c6_scanner.ino.

static void uart_task(void *arg) {
  Serial1.begin(UART_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);
  Serial.println("[UART] listening on GPIO20 (from Beetle C6)");
  Serial.printf("[UART] Serial1 begun on RX=GPIO%d TX=GPIO%d\n", UART_RX_PIN,
                UART_TX_PIN);

  char buf[UART_BUF_SIZE];
  int buf_idx = 0;

  while (1) {
    while (Serial1.available()) {
      char c = (char)Serial1.read();
      // Serial.printf("[UART] raw byte: 0x%02X '%c'\n", (uint8_t)c, isprint(c)
      // ? c : '.');

      if (c == '\n') {
        buf[buf_idx] = '\0';
        buf_idx = 0;

        // Validate this is a wifi packet
        if (strncmp(buf, "{\"wifi\":[", 9) != 0)
          continue;

        APRecord parsed[MAX_APS];
        int parsed_count = 0;
        char *p = buf;

        // Parse each AP record — find "bssid": blocks
        while ((p = strstr(p, "\"bssid\":\"")) != NULL &&
               parsed_count < MAX_APS) {
          p += 9; // skip past "bssid":"

          // Extract bssid — always exactly 17 chars (AA:BB:CC:DD:EE:FF)
          strncpy(parsed[parsed_count].bssid, p, 17);
          parsed[parsed_count].bssid[17] = '\0';
          p += 17;

          // Extract ssid
          char *ssid_start = strstr(p, "\"ssid\":\"");
          if (!ssid_start)
            break;
          ssid_start += 8;

          // Find closing unescaped quote
          int ssid_len = 0;
          while (ssid_start[ssid_len] != '\0' && ssid_len < 32) {
            if (ssid_start[ssid_len] == '"' &&
                (ssid_len == 0 || ssid_start[ssid_len - 1] != '\\'))
              break;
            ssid_len++;
          }
          strncpy(parsed[parsed_count].ssid, ssid_start, ssid_len);
          parsed[parsed_count].ssid[ssid_len] = '\0';
          p = ssid_start + ssid_len;

          // Extract rssi
          char *rssi_p = strstr(p, "\"rssi\":");
          if (!rssi_p)
            break;
          parsed[parsed_count].rssi = (int32_t)atoi(rssi_p + 7);
          p = rssi_p + 7;

          // Extract channel
          char *ch_p = strstr(p, "\"ch\":");
          if (!ch_p)
            break;
          parsed[parsed_count].channel = (int32_t)atoi(ch_p + 5);
          p = ch_p + 5;

          parsed_count++;
        }

        if (parsed_count > 0) {
          if (xSemaphoreTake(ap_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            memcpy(ap_list, parsed, sizeof(APRecord) * parsed_count);
            ap_count = parsed_count;
            ap_fresh = true;
            xSemaphoreGive(ap_mutex);
          }
          Serial.printf("[UART] %d APs from Beetle C6\n", parsed_count);
        }

      } else if (c != '\r') {
        if (buf_idx < UART_BUF_SIZE - 1) {
          buf[buf_idx++] = c;
        } else {
          buf_idx = 0;
          Serial.println("[UART] overflow — discarded");
        }
      }
    }
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

// ── Wi-Fi task — connection maintenance
// ───────────────────────────────────────
static void wifi_task(void *arg) {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

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
    Serial.println("[WIFI] initial connect failed — retrying");
  }

  while (1) {
    if (WiFi.status() != WL_CONNECTED) {
      wifi_connected = false;
      Serial.println("[WIFI] disconnected — restarting connection...");
      WiFi.disconnect(true);
      vTaskDelay(pdMS_TO_TICKS(500));
      WiFi.begin(WIFI_SSID, WIFI_PASS);
      // Wait up to 15s for connection
      int attempts = 0;
      while (WiFi.status() != WL_CONNECTED && attempts < 150) {
        vTaskDelay(pdMS_TO_TICKS(100));
        attempts++;
      }
      if (WiFi.status() == WL_CONNECTED) {
        wifi_connected = true;
        Serial.print("[WIFI] reconnected, IP: ");
        Serial.println(WiFi.localIP());
      } else {
        Serial.println("[WIFI] reconnect failed — will retry");
      }
    } else {
      wifi_connected = true;
    }
    vTaskDelay(pdMS_TO_TICKS(5000));
  }
}

// ── POST task
// ─────────────────────────────────────────────────────────────────
static void post_task(void *arg) {
  while (!wifi_connected)
    vTaskDelay(pdMS_TO_TICKS(500));
  Serial.println("[POST] task started");

  WiFiClientSecure client;
  client.setInsecure();

  while (1) {
    vTaskDelay(pdMS_TO_TICKS(POST_INTERVAL_MS));
    if (!wifi_connected)
      continue;

    // Drain IMU_DRAIN_SIZE samples from front of buffer
    ImuSample batch_copy[IMU_DRAIN_SIZE];
    int drain_size = 0;

    if (xSemaphoreTake(imu_mutex, pdMS_TO_TICKS(20)) == pdTRUE) {
      drain_size = min(imu_batch_idx, IMU_DRAIN_SIZE);
      if (drain_size > 0) {
        memcpy(batch_copy, imu_batch, sizeof(ImuSample) * drain_size);
        int remaining = imu_batch_idx - drain_size;
        if (remaining > 0) {
          memmove(imu_batch, imu_batch + drain_size,
                  sizeof(ImuSample) * remaining);
        }
        imu_batch_idx = remaining;
      }
      xSemaphoreGive(imu_mutex);
    }

    if (drain_size == 0)
      continue;

    // Snapshot AP list if fresh data from Beetle C6
    APRecord ap_copy[MAX_APS];
    int ap_copy_count = 0;
    bool has_wifi = false;

    if (xSemaphoreTake(ap_mutex, pdMS_TO_TICKS(20)) == pdTRUE) {
      if (ap_fresh) {
        memcpy(ap_copy, ap_list, sizeof(APRecord) * ap_count);
        ap_copy_count = ap_count;
        has_wifi = true;
        ap_fresh = false;
      }
      xSemaphoreGive(ap_mutex);
    }

    // Build JSON packet — full bssid+ssid+rssi+ch per AP
    String json = "{";
    json += "\"mac\":\"" DEVICE_MAC "\",";
    json += "\"ts\":" + String(millis()) + ",";

    json += "\"imu\":[";
    for (int i = 0; i < drain_size; i++) {
      json += "{\"ts\":" + String(batch_copy[i].ts) + ",";
      json += "\"ax\":" + String(batch_copy[i].ax, 4) + ",";
      json += "\"ay\":" + String(batch_copy[i].ay, 4) + ",";
      json += "\"az\":" + String(batch_copy[i].az, 4) + ",";
      json += "\"gx\":" + String(batch_copy[i].gx, 4) + ",";
      json += "\"gy\":" + String(batch_copy[i].gy, 4) + ",";
      json += "\"gz\":" + String(batch_copy[i].gz, 4) + "}";
      if (i < drain_size - 1)
        json += ",";
    }
    json += "],";

    json += "\"wifi\":[";
    if (has_wifi) {
      for (int i = 0; i < ap_copy_count; i++) {
        json += "{\"bssid\":\"" + String(ap_copy[i].bssid) + "\",";
        json += "\"ssid\":\"" + String(ap_copy[i].ssid) + "\",";
        json += "\"rssi\":" + String(ap_copy[i].rssi) + ",";
        json += "\"ch\":" + String(ap_copy[i].channel) + "}";
        if (i < ap_copy_count - 1)
          json += ",";
      }
    }
    json += "]}";

    // POST
    HTTPClient http;
    http.begin(client, SERVER_URL);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-Key", API_KEY);
    http.setTimeout(3000);

    int code = http.POST(json);

    if (code > 0) {
      Serial.printf("[POST] %d — %d bytes, wifi=%s, buf=%d\n", code,
                    json.length(), has_wifi ? "yes" : "no", imu_batch_idx);
    } else {
      Serial.printf("[POST] failed: %s (buf=%d)\n",
                    http.errorToString(code).c_str(), imu_batch_idx);
    }

    http.end();
  }
}

// ── Setup
// ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("[TRAKN] starting (ESP32-C5 + Beetle C6)...");

  ap_mutex = xSemaphoreCreateMutex();
  imu_mutex = xSemaphoreCreateMutex();
  configASSERT(ap_mutex);
  configASSERT(imu_mutex);

  imu_init();

  // Single-core ESP32-C5: xTaskCreate only, never xTaskCreatePinnedToCore
  xTaskCreate(imu_task, "imu", 8192, NULL, 5, NULL);
  xTaskCreate(uart_task, "uart", 8192, NULL, 3, NULL);
  xTaskCreate(wifi_task, "wifi", 8192, NULL, 3, NULL);
  xTaskCreate(post_task, "post", 16384, NULL, 2, NULL);
}

void loop() { vTaskDelay(portMAX_DELAY); }
