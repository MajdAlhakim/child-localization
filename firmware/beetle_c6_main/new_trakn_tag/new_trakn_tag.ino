// firmware/beetle_c6_main/new_trakn_tag/new_trakn_tag.ino
// Beetle ESP32-C6 (DFR1117) — TRAKN Tag Firmware (two-board architecture)
//
// Hardware: Beetle ESP32-C6 + MPU6050 IMU + BMP180 barometer
//           + Beetle ESP32-C6 scanner (via UART)
// Board package: esp32 by Espressif Systems v3.3.5+
// Board selection: Tools → Board → esp32 → ESP32C6 Dev Module
// USB CDC On Boot: Enabled
//
// Two-board architecture:
//   Beetle ESP32-C6 (beetle_c6_scanner.ino) — dedicated Wi-Fi scanner
//     → scans every 10s, no radio contention with TCP
//     → sends {"wifi":[{"bssid":"...","ssid":"...","rssi":-46,"ch":6},...]}
//     over UART
//   This board — IMU sampling + barometer + HTTP POST only
//     → radio 100% dedicated to TCP/TLS, never scans
//     → zero scan blackouts, zero TLS timeouts
//
// UART wiring:
//   Beetle ESP32-C6 scanner GPIO16 (TX) → Beetle ESP32-C6 tag GPIO17 (RX)
//   Shared GND
//
// I2C wiring (shared bus, GPIO19=SDA, GPIO20=SCL):
//   MPU6050: addr 0x68
//   BMP180:  addr 0x77
//
// FreeRTOS tasks (single-core Beetle C6 — xTaskCreate only):
//   imu_task   (priority 5) — MPU6050 at 100Hz, fills ring buffer
//   uart_task  (priority 3) — reads JSON from scanner Beetle, updates ap_list
//   wifi_task  (priority 3) — maintains Wi-Fi station connection
//   post_task  (priority 2) — drains IMU, POSTs JSON every 1000ms
//   baro_task  (priority 1) — BMP180 floor detection, ~1 Hz

#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <Adafruit_BMP085.h>
#include <math.h>

// ── Network config ────────────────────────────────────────────────────────────
#define WIFI_SSID   "QU User"
#define WIFI_PASS   ""
#define SERVER_URL  "https://35.238.189.188/api/v1/gateway/packet"
#define DEVICE_MAC  "9C:9E:6E:77:17:50"
#define API_KEY     "580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990"

// ── IMU constants (LOCKED — verified in SDP1, never change) ──────────────────
#define MPU6050_ADDR  0x68
#define PWR_MGMT_1    0x6B
#define GYRO_CONFIG   0x1B
#define ACCEL_CONFIG  0x1C
#define CONFIG_REG    0x1A
#define ACCEL_XOUT_H  0x3B
#define ACCEL_SCALE   0.0011978149f
#define GYRO_SCALE    0.0002663309f

// ── Sizing ────────────────────────────────────────────────────────────────────
#define MAX_APS           30
#define IMU_BATCH_SIZE    25
#define IMU_DRAIN_SIZE    25
#define POST_INTERVAL_MS  1000

// ── UART (from scanner Beetle ESP32-C6) ──────────────────────────────────────
#define UART_RX_PIN   17
#define UART_TX_PIN   16
#define UART_BAUD     115200
#define UART_BUF_SIZE 3072

// ── Barometer (BMP180) ────────────────────────────────────────────────────────
// BARO_CONFIRM_THRESHOLD: consecutive ~1 Hz readings all showing the same floor
// before estimatedFloor commits. 10 = ~10 s stability required, which absorbs
// jumps, stair bounces, and HVAC-induced pressure spikes near floor boundaries.
#define BARO_CONFIRM_THRESHOLD  10
// Floor-to-floor height of H07. Tune after on-site measurement if needed.
#define FLOOR_HEIGHT_M          3.5f

// ── Structs ───────────────────────────────────────────────────────────────────
struct APRecord {
  char    bssid[18];
  char    ssid[33];
  int32_t rssi;
  int32_t channel;
};

struct ImuSample {
  unsigned long ts;
  float ax, ay, az;
  float gx, gy, gz;
};

// ── Shared state ──────────────────────────────────────────────────────────────
static APRecord  ap_list[MAX_APS];
static int       ap_count          = 0;
static bool      ap_fresh          = false;
static uint32_t  ap_scan_seq       = 0;

static ImuSample imu_batch[IMU_BATCH_SIZE];
static int       imu_batch_idx     = 0;

static bool     wifi_connected      = false;
static volatile bool wifi_reassociated = false;

// Barometer state (written only by baro_task, read by post_task via baro_mutex)
static Adafruit_BMP085 bmp;
static bool  baro_ok          = false;
static float baselinePressure = 0.0f;  // Pa, measured at Ground Floor on boot
static int   estimatedFloor   = 0;
static int   pendingFloor     = 0;
static int   floorVoteCount   = 0;

// ── Semaphores ────────────────────────────────────────────────────────────────
static SemaphoreHandle_t ap_mutex   = NULL;
static SemaphoreHandle_t imu_mutex  = NULL;
// i2c_mutex protects the shared Wire bus between imu_task and baro_task.
// imu_task holds it for ~0.5 ms per read; baro_task holds it for ~0.5 ms
// per phase (releasing during BMP180 conversion delays so IMU can interleave).
static SemaphoreHandle_t i2c_mutex  = NULL;
// baro_mutex protects estimatedFloor reads from post_task.
static SemaphoreHandle_t baro_mutex = NULL;

// ── IMU helpers ───────────────────────────────────────────────────────────────
static void writeReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission((uint8_t)MPU6050_ADDR);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission(true);
}

// Called from setup() before any tasks start — no mutex needed.
static void imu_init() {
  Wire.begin(19, 20);
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

// ── IMU task — 100 Hz ─────────────────────────────────────────────────────────
static void imu_task(void *arg) {
  TickType_t     last      = xTaskGetTickCount();
  static uint32_t ok_count  = 0, err_count = 0;

  while (1) {
    int16_t ax_r = 0, ay_r = 0, az_r = 0;
    int16_t gx_r = 0, gy_r = 0, gz_r = 0;
    uint8_t n = 0;

    // Hold i2c_mutex only for the actual Wire transaction (~0.5 ms).
    // Timeout 5 ms: if baro_task is mid-phase, we skip one IMU sample rather
    // than blocking past the 10 ms deadline.
    if (xSemaphoreTake(i2c_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
      Wire.beginTransmission((uint8_t)MPU6050_ADDR);
      Wire.write(ACCEL_XOUT_H);
      Wire.endTransmission(false);
      Wire.setTimeout(50);
      n = Wire.requestFrom((uint8_t)MPU6050_ADDR, (uint8_t)14, (bool)true);
      if (n == 14) {
        ax_r = (int16_t)((Wire.read() << 8) | Wire.read());
        ay_r = (int16_t)((Wire.read() << 8) | Wire.read());
        az_r = (int16_t)((Wire.read() << 8) | Wire.read());
        Wire.read(); Wire.read();  // skip temperature registers
        gx_r = (int16_t)((Wire.read() << 8) | Wire.read());
        gy_r = (int16_t)((Wire.read() << 8) | Wire.read());
        gz_r = (int16_t)((Wire.read() << 8) | Wire.read());
      }
      xSemaphoreGive(i2c_mutex);
    }

    if (n == 14) ok_count++; else err_count++;
    if ((ok_count + err_count) % 200 == 0)
      Serial.printf("[IMU] ok=%lu err=%lu batch=%d\n",
                    (unsigned long)ok_count, (unsigned long)err_count,
                    imu_batch_idx);

    if (n == 14) {
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

// ── Barometer helpers ─────────────────────────────────────────────────────────

// Called from setup() before tasks start — no mutex needed.
static void baro_init() {
  if (!bmp.begin()) {
    Serial.println("[BARO] BMP180 not found — check wiring");
    return;
  }
  baro_ok = true;

  // Collect 10 readings for a stable Ground Floor baseline.
  // readPressure() returns Pascals; readTemperature() returns °C.
  // Both use delay() internally (~13 ms total), which yields in FreeRTOS.
  float sum   = 0.0f;
  int   count = 0;
  for (int i = 0; i < 10; i++) {
    int32_t P = bmp.readPressure();  // Pa
    if (P > 0) {
      sum += (float)P;
      count++;
    }
    delay(100);
  }

  if (count > 0) {
    baselinePressure = sum / (float)count;
    estimatedFloor   = 0;
    pendingFloor     = 0;
    floorVoteCount   = 0;
    Serial.printf("[BARO] baseline=%.2f Pa, starting floor=G\n", baselinePressure);
  } else {
    baro_ok = false;
    Serial.println("[BARO] baseline calibration failed — floor detection disabled");
  }
}

// ── Barometer task — floor detection ~1 Hz ───────────────────────────────────
//
// Adafruit_BMP085::readPressure() returns Pa; readTemperature() returns °C.
// Both use delay() internally (~13 ms total). In FreeRTOS, delay() calls
// vTaskDelay(), so the CPU yields to other tasks during the conversion wait —
// but i2c_mutex stays held. The IMU task may miss 1 sample per baro reading
// (every ~865 ms), which is <0.2% loss and has no meaningful effect on PDR.
//
// Floor thresholds (altitude delta above Ground Floor baseline):
//   < -2.0 m : Basement (-1)
//   -2.0 to +2.5 m : Ground (0)
//   +2.5 to +5.5 m : Floor 1 (1)
//   > +5.5 m  : Floor 2 (2)
//
// BARO_CONFIRM_THRESHOLD consecutive readings (~10 s) at the same floor are
// required before estimatedFloor commits.
static void baro_task(void *arg) {
  if (!baro_ok) {
    Serial.println("[BARO] sensor absent — floor detection disabled");
    vTaskDelete(NULL);
    return;
  }

  while (1) {
    float  altDelta = 0.0f;
    bool   ok       = false;

    // Hold i2c_mutex for the full read cycle (~13 ms).
    // delay() inside readPressure() yields the CPU but keeps the mutex.
    if (xSemaphoreTake(i2c_mutex, pdMS_TO_TICKS(30)) == pdTRUE) {
      int32_t P = bmp.readPressure();  // Pa; internally takes ~13 ms
      xSemaphoreGive(i2c_mutex);

      if (P > 0 && baselinePressure > 0.0f) {
        altDelta = 44330.0f *
                   (1.0f - powf((float)P / baselinePressure, 0.1903f));
        ok = true;
      }
    }

    if (ok) {
      int newFloor;
      if      (altDelta < -2.0f)                   newFloor = -1;  // Basement
      else if (altDelta <  2.5f)                   newFloor =  0;  // Ground
      else if (altDelta < FLOOR_HEIGHT_M + 3.0f && altDelta > 2.5f)   newFloor =  1;  // Floor 1
      else                                         newFloor =  2;  // Floor 2

      if (xSemaphoreTake(baro_mutex, pdMS_TO_TICKS(20)) == pdTRUE) {
        if (newFloor == pendingFloor) {
          if (++floorVoteCount >= BARO_CONFIRM_THRESHOLD)
            estimatedFloor = newFloor;
        } else {
          pendingFloor   = newFloor;
          floorVoteCount = 1;
        }
        xSemaphoreGive(baro_mutex);
      }

      Serial.printf("[BARO] dAlt=%.2fm floor=%d (pending=%d votes=%d/%d)\n",
                    altDelta, estimatedFloor, pendingFloor,
                    floorVoteCount, BARO_CONFIRM_THRESHOLD);
    }

    // Total cycle: ~13 ms read + 850 ms delay ≈ 863 ms (~1 Hz)
    vTaskDelay(pdMS_TO_TICKS(850));
  }
}

// ── UART task — reads JSON lines from scanner Beetle ESP32-C6 ────────────────
//
// Parses:
// {"wifi":[{"bssid":"AA:BB:CC:DD:EE:FF","ssid":"Name","rssi":-46,"ch":6},...]}
//
// Uses plain C string parsing — no JSON library needed.
// All fields are present and in fixed order as generated by beetle_c6_scanner.ino.

static void uart_task(void *arg) {
  Serial1.begin(UART_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);
  Serial.printf("[UART] Serial1 begun on RX=GPIO%d TX=GPIO%d\n",
                UART_RX_PIN, UART_TX_PIN);

  char buf[UART_BUF_SIZE];
  int  buf_idx = 0;

  while (1) {
    while (Serial1.available()) {
      char c = (char)Serial1.read();

      if (c == '\n') {
        buf[buf_idx] = '\0';
        buf_idx = 0;

        if (strncmp(buf, "{\"wifi\":[", 9) != 0)
          continue;

        APRecord parsed[MAX_APS];
        int      parsed_count = 0;
        char    *p = buf;

        while ((p = strstr(p, "\"bssid\":\"")) != NULL &&
               parsed_count < MAX_APS) {
          p += 9;

          strncpy(parsed[parsed_count].bssid, p, 17);
          parsed[parsed_count].bssid[17] = '\0';
          p += 17;

          char *ssid_start = strstr(p, "\"ssid\":\"");
          if (!ssid_start) break;
          ssid_start += 8;

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

          char *rssi_p = strstr(p, "\"rssi\":");
          if (!rssi_p) break;
          parsed[parsed_count].rssi = (int32_t)atoi(rssi_p + 7);
          p = rssi_p + 7;

          char *ch_p = strstr(p, "\"ch\":");
          if (!ch_p) break;
          parsed[parsed_count].channel = (int32_t)atoi(ch_p + 5);
          p = ch_p + 5;

          parsed_count++;
        }

        if (parsed_count > 0) {
          if (xSemaphoreTake(ap_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            memcpy(ap_list, parsed, sizeof(APRecord) * parsed_count);
            ap_count = parsed_count;
            ap_fresh = true;
            ap_scan_seq++;
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

// Pick the strongest BSSID from the scanner's list that matches WIFI_SSID and
// initiate a direct association (no ESP32 scan).
static void connect_to_best_ap() {
  // Force-reset any stuck state (WL_CONNECT_FAILED, WL_NO_SSID_AVAIL,
  // WL_CONNECTION_LOST) before calling begin().  Without this the old guard
  // returned early on every retry loop, causing 60-90 s blackouts.
  // false = keep saved credentials; does not erase SSID/pass.
  WiFi.disconnect(false);

  APRecord best;
  int  best_rssi = -1000;
  bool found     = false;

  if (xSemaphoreTake(ap_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
    for (int i = 0; i < ap_count; i++) {
      if (strcmp(ap_list[i].ssid, WIFI_SSID) != 0) continue;
      if (ap_list[i].rssi > best_rssi) {
        best      = ap_list[i];
        best_rssi = ap_list[i].rssi;
        found = true;
      }
    }
    xSemaphoreGive(ap_mutex);
  }

  if (!found) {
    Serial.println("[WIFI] no scanner data for SSID yet — SSID-only connect");
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    wifi_reassociated = true;
    return;
  }

  uint8_t bssid[6];
  sscanf(best.bssid, "%hhx:%hhx:%hhx:%hhx:%hhx:%hhx",
         &bssid[0], &bssid[1], &bssid[2],
         &bssid[3], &bssid[4], &bssid[5]);

  Serial.printf("[WIFI] targeting bssid=%s rssi=%d ch=%d\n",
                best.bssid, best.rssi, best.channel);
  WiFi.begin(WIFI_SSID, WIFI_PASS, best.channel, bssid, true);
  wifi_reassociated = true;
}

static bool current_bssid_in_scan() {
  uint8_t *cur = WiFi.BSSID();
  if (cur == NULL) return false;

  char cur_str[18];
  snprintf(cur_str, sizeof(cur_str), "%02X:%02X:%02X:%02X:%02X:%02X",
           cur[0], cur[1], cur[2], cur[3], cur[4], cur[5]);

  bool found = false;
  if (xSemaphoreTake(ap_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
    for (int i = 0; i < ap_count; i++) {
      if (strcasecmp(ap_list[i].bssid, cur_str) == 0) {
        found = true;
        break;
      }
    }
    xSemaphoreGive(ap_mutex);
  }
  return found;
}

// ── Wi-Fi task — scan-driven BSSID selection ─────────────────────────────────
static void wifi_task(void *arg) {
  WiFi.mode(WIFI_STA);

  Serial.print("[WIFI] connecting to ");
  Serial.println(WIFI_SSID);

  for (int i = 0; i < 120; i++) {
    if (ap_fresh) break;
    vTaskDelay(pdMS_TO_TICKS(100));
  }
  connect_to_best_ap();

  uint32_t      last_processed_scan_seq = 0;
  unsigned long last_reconnect_ms       = 0;

  while (1) {
    wifi_connected = (WiFi.status() == WL_CONNECTED);

    if (!wifi_connected) {
      if (millis() - last_reconnect_ms < 3000) {
        vTaskDelay(pdMS_TO_TICKS(500));
        continue;
      }
      last_reconnect_ms = millis();
      Serial.println("[WIFI] disconnected — reconnecting to best AP");
      connect_to_best_ap();

      int tries = 0;
      while (WiFi.status() != WL_CONNECTED && tries < 30) {
        vTaskDelay(pdMS_TO_TICKS(100));
        tries++;
      }
      if (WiFi.status() == WL_CONNECTED) {
        wifi_connected = true;
        Serial.printf("[WIFI] reconnected IP=%s rssi=%d\n",
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
      }
    } else {
      uint32_t seq;
      if (xSemaphoreTake(ap_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        seq = ap_scan_seq;
        xSemaphoreGive(ap_mutex);
      } else {
        seq = last_processed_scan_seq;
      }

      if (seq != last_processed_scan_seq) {
        last_processed_scan_seq = seq;
        if (!current_bssid_in_scan()) {
          Serial.println("[WIFI] current BSSID missing from new scan — jumping to strongest");
          connect_to_best_ap();
        }
      }
    }
    vTaskDelay(pdMS_TO_TICKS(500));
  }
}

// ── POST task ─────────────────────────────────────────────────────────────────
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

    if (wifi_reassociated) {
      wifi_reassociated = false;
      client.stop();
      Serial.println("[POST] client reset after Wi-Fi re-association");
    }

    // Drain IMU samples
    ImuSample batch_copy[IMU_DRAIN_SIZE];
    int drain_size = 0;

    if (xSemaphoreTake(imu_mutex, pdMS_TO_TICKS(20)) == pdTRUE) {
      drain_size = min(imu_batch_idx, IMU_DRAIN_SIZE);
      if (drain_size > 0) {
        memcpy(batch_copy, imu_batch, sizeof(ImuSample) * drain_size);
        int remaining = imu_batch_idx - drain_size;
        if (remaining > 0)
          memmove(imu_batch, imu_batch + drain_size,
                  sizeof(ImuSample) * remaining);
        imu_batch_idx = remaining;
      }
      xSemaphoreGive(imu_mutex);
    }

    if (drain_size == 0) {
      static uint32_t silent_ticks = 0;
      if (++silent_ticks % 25 == 0)
        Serial.printf("[POST] idle — imu_batch_idx=%d (IMU not producing)\n",
                      imu_batch_idx);
      continue;
    }

    // Snapshot AP list if fresh scan arrived
    APRecord ap_copy[MAX_APS];
    int  ap_copy_count = 0;
    bool has_wifi      = false;

    if (xSemaphoreTake(ap_mutex, pdMS_TO_TICKS(20)) == pdTRUE) {
      if (ap_fresh) {
        memcpy(ap_copy, ap_list, sizeof(APRecord) * ap_count);
        ap_copy_count = ap_count;
        has_wifi      = true;
        ap_fresh      = false;
      }
      xSemaphoreGive(ap_mutex);
    }

    // Read current floor estimate
    int current_floor = 0;
    if (baro_ok && xSemaphoreTake(baro_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
      current_floor = estimatedFloor;
      xSemaphoreGive(baro_mutex);
    }

    // Build JSON packet
    String json = "{";
    json += "\"mac\":\"" DEVICE_MAC "\",";
    json += "\"ts\":" + String(millis()) + ",";
    json += "\"floor\":" + String(current_floor) + ",";

    json += "\"imu\":[";
    for (int i = 0; i < drain_size; i++) {
      json += "{\"ts\":" + String(batch_copy[i].ts) + ",";
      json += "\"ax\":" + String(batch_copy[i].ax, 4) + ",";
      json += "\"ay\":" + String(batch_copy[i].ay, 4) + ",";
      json += "\"az\":" + String(batch_copy[i].az, 4) + ",";
      json += "\"gx\":" + String(batch_copy[i].gx, 4) + ",";
      json += "\"gy\":" + String(batch_copy[i].gy, 4) + ",";
      json += "\"gz\":" + String(batch_copy[i].gz, 4) + "}";
      if (i < drain_size - 1) json += ",";
    }
    json += "],";

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

    Serial.printf("[POST] RSSI=%d IP=%s floor=%d\n",
                  WiFi.RSSI(), WiFi.localIP().toString().c_str(), current_floor);

    HTTPClient http;
    http.begin(client, SERVER_URL);
    http.setReuse(false);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-Key", API_KEY);
    http.addHeader("Connection", "close");
    http.setTimeout(5000);

    int code = http.POST(json);

    if (code > 0) {
      Serial.printf("[POST] %d — %d bytes, wifi=%s, buf=%d\n",
                    code, json.length(), has_wifi ? "yes" : "no", imu_batch_idx);
    } else {
      Serial.printf("[POST] failed: %s (buf=%d)\n",
                    http.errorToString(code).c_str(), imu_batch_idx);
      http.end();
      client.stop();
      continue;
    }

    http.end();
  }
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("[TRAKN] starting (Beetle ESP32-C6 + BMP180)...");

  ap_mutex   = xSemaphoreCreateMutex();
  imu_mutex  = xSemaphoreCreateMutex();
  i2c_mutex  = xSemaphoreCreateMutex();
  baro_mutex = xSemaphoreCreateMutex();
  configASSERT(ap_mutex);
  configASSERT(imu_mutex);
  configASSERT(i2c_mutex);
  configASSERT(baro_mutex);

  imu_init();   // Wire.begin(19,20), MPU6050 config — no tasks yet, no mutex needed
  baro_init();  // BMP180 init + Ground Floor baseline — no tasks yet, no mutex needed

  // Single-core ESP32-C6: xTaskCreate only, never xTaskCreatePinnedToCore
  xTaskCreate(imu_task,  "imu",  8192,  NULL, 5, NULL);
  xTaskCreate(uart_task, "uart", 8192,  NULL, 3, NULL);
  xTaskCreate(wifi_task, "wifi", 8192,  NULL, 3, NULL);
  xTaskCreate(post_task, "post", 16384, NULL, 2, NULL);
  xTaskCreate(baro_task, "baro", 4096,  NULL, 1, NULL);
}

void loop() { vTaskDelay(portMAX_DELAY); }
