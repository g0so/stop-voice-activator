#pragma once
#include <stdint.h>

// Replace these three values before uploading the sketch.
constexpr char WIFI_SSID[] = "YOUR_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";
constexpr char VOICE_SERVER_HOST[] = "192.168.1.100";
constexpr uint16_t VOICE_SERVER_PORT = 8765;

// The connection stays open while the detector is idle. This avoids a TCP
// handshake after the wake word and gives a meaningful trigger-to-server
// latency measurement.
constexpr bool VOICE_SERVER_ENABLED = true;
