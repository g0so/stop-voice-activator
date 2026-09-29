#include <Arduino.h>
#include <ESP_I2S.h>

// ESP32 Dev Module, Arduino ESP32 package 3.3.11.
// INMP441: VDD=3.3V, GND=GND, L/R=GND, SCK=26, WS=33, SD=32.
I2SClass microphone;
constexpr uint32_t SAMPLE_RATE = 16000;
constexpr uint32_t RECORD_SAMPLES = SAMPLE_RATE * 5;
constexpr size_t BLOCK_SAMPLES = 256;
int32_t rawAudio[BLOCK_SAMPLES];
int16_t pcmAudio[BLOCK_SAMPLES];
bool recording = false;
uint32_t remaining = 0;

void setup() {
  Serial.begin(921600);
  delay(1000);
  microphone.setPins(26, 33, -1, 32);
  if (!microphone.begin(I2S_MODE_STD, SAMPLE_RATE,
                        I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO,
                        I2S_STD_SLOT_LEFT)) {
    Serial.println("ERROR: microphone initialization failed");
    while (true) delay(1000);
  }
  Serial.println("READY: microphone initialized. Close Serial Monitor before recording.");
}

void loop() {
  // Continuously drain I2S, including while waiting for a recording request.
  if (!recording && Serial.available()) {
    if (Serial.read() == 'r') {
      remaining = RECORD_SAMPLES;
      recording = true;
      Serial.println("AUDIO 16000 160000");
    }
  }

  size_t wanted = BLOCK_SAMPLES;
  if (recording && remaining < wanted) wanted = remaining;
  size_t received = microphone.readBytes((char *)rawAudio, wanted * sizeof(int32_t));
  if (received == 0 || received % sizeof(int32_t) != 0) {
    // A partial binary capture will time out and be rejected by the host.
    Serial.println("ERROR: microphone read failed");
    while (true) delay(1000);
  }
  if (!recording) return;

  const size_t samples = received / sizeof(int32_t);
  for (size_t i = 0; i < samples; ++i) {
    // The microphone's signed 24-bit sample occupies the high bits.
    // Start with unity gain: retain the upper 16 bits, without boosting.
    pcmAudio[i] = (int16_t)(rawAudio[i] >> 16);
  }
  Serial.write((const uint8_t *)pcmAudio, samples * sizeof(int16_t));
  remaining -= samples;
  if (remaining == 0) {
    recording = false;
    Serial.println("DONE");
  }
}
