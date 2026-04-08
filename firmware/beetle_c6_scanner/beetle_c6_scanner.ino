// firmware/beetle_c6/beetle_c6_scanner.ino
// Beetle ESP32-C6 (DFR1117) — TRAKN Wi-Fi Scanner
//
// Role: dedicated Wi-Fi RSSI scanner in the two-board TRAKN architecture
//
// This board does ONE thing only:
//   1. Put radio in station mode (no connection needed)
//   2. Scan for nearby APs every SCAN_INTERVAL_MS
//   3. Send results as a single JSON line to ESP32-C5 over UART
//
// No Wi-Fi credentials needed — scanning does not require association.
// The ESP32 radio in WIFI_STA mode performs passive channel sweeps and
// collects beacon frames from all APs in range without joining any network.
// This also means no reconnection logic, no IP, no network dependency.
//
// UART wiring:
//   Beetle ESP32-C6 GPIO16 (TX) → XIAO ESP32-C5 GPIO20 (D7 / RX)
//   Beetle ESP32-C6 GND         → XIAO ESP32-C5 GND
//   (RX not wired — Beetle never receives data from ESP32-C5)
//
// Board setup in Arduino IDE:
//   Board:              ESP32C6 Dev Module
//   USB CDC On Boot:    Enabled
//   Flash Size:         4MB
//   Partition Scheme:   Default 4MB with spiffs
//
// Output format — one newline-terminated JSON line per scan:
//   {"wifi":[{"bssid":"AA:BB:CC:DD:EE:FF","ssid":"Name","rssi":-46,"ch":6},...]}
//
// Serial  = USB debug output (Arduino Serial Monitor)
// Serial1 = UART TX to ESP32-C5 on GPIO16

#include <WiFi.h>

// ── Config ────────────────────────────────────────────────────────────────────
#define SCAN_INTERVAL_MS  10000   // ms between scans
#define MAX_APS           30      // cap on APs included in output
#define UART_TX_PIN       16      // GPIO16 = TX on Beetle ESP32-C6
#define UART_RX_PIN       17      // GPIO17 = RX (unused)
#define UART_BAUD         115200

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("[C6] TRAKN scanner starting...");

    // UART to ESP32-C5
    Serial1.begin(UART_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);
    Serial.println("[C6] UART TX ready on GPIO16");

    // Station mode — no credentials, no connection, just enables the radio
    // Scanning works without being associated to any AP
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();  // ensure not connected to anything
    delay(100);

    Serial.println("[C6] radio ready, scanning...");
}

// ── Loop — scan, build JSON, send over UART ───────────────────────────────────
void loop() {
    Serial.println("[C6] scanning...");

    // Blocking scan — collects beacon frames from all APs in range
    // No association required — works anywhere, any network
    int n = WiFi.scanNetworks();

    if (n <= 0) {
        Serial.println("[C6] no results");
        delay(SCAN_INTERVAL_MS);
        return;
    }

    Serial.printf("[C6] %d APs found\n", n);

    int count = (n > MAX_APS) ? MAX_APS : n;

    // Build JSON line
    String json = "{\"wifi\":[";

    for (int i = 0; i < count; i++) {
        String bssid = WiFi.BSSIDstr(i);
        String ssid  = WiFi.SSID(i);
        int    rssi  = WiFi.RSSI(i);
        int    ch    = WiFi.channel(i);

        // Sanitise SSID — escape backslashes then double quotes
        ssid.replace("\\", "\\\\");
        ssid.replace("\"", "\\\"");

        json += "{\"bssid\":\"" + bssid + "\",";
        json += "\"ssid\":\""   + ssid  + "\",";
        json += "\"rssi\":"     + String(rssi) + ",";
        json += "\"ch\":"       + String(ch)   + "}";

        if (i < count - 1) json += ",";
    }

    json += "]}";

    // Send to ESP32-C5 — single newline-terminated line
    Serial1.println(json);

    // Free scan memory
    WiFi.scanDelete();

    // Debug
    Serial.printf("[C6] sent %d bytes to ESP32-C5\n", json.length());
    if (json.length() > 100) {
        Serial.println(json.substring(0, 100) + "...");
    } else {
        Serial.println(json);
    }

    delay(SCAN_INTERVAL_MS);
}
