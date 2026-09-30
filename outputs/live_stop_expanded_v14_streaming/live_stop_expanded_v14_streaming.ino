#include <Arduino.h>
#include <ESP_I2S.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <esp_heap_caps.h>
#include <math.h>
#include <string.h>
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "stop_model_data.h"
#include "frontend.h"
#include "window_centering.h"
#include "test_vectors.h"
#include "network_config.h"
// V14 KWS plus a persistent, low-overhead PCM16 stream to a local ASR server.
// The KWS threshold, preprocessing, model, test vectors and tolerance are
// unchanged from the frozen V14 board candidate.
constexpr float STOP_THRESHOLD = 0.8671875f;
constexpr unsigned INFERENCE_EVERY_FRAMES = 10;  // 200 ms.
constexpr uint32_t SAMPLE_RATE = 16000;
constexpr uint32_t PRE_ROLL_MS = 750;
constexpr uint32_t CAPTURE_AFTER_TRIGGER_MS = 5000;
constexpr uint32_t AUDIO_RING_SAMPLES = SAMPLE_RATE * 3 / 2;  // 48 KiB, 1.5 seconds.
constexpr size_t AUDIO_RING_BYTES = AUDIO_RING_SAMPLES * sizeof(int16_t);
constexpr uint16_t STREAM_FRAME_SAMPLES = 160;            // 10 ms / 320 bytes.
constexpr uint8_t PROTOCOL_VERSION = 1;
constexpr uint8_t CODEC_IMA_ADPCM = 1;

enum FrameType : uint8_t {
  FRAME_HELLO = 1,
  FRAME_TRIGGER = 2,
  FRAME_AUDIO = 3,
  FRAME_END = 4,
  FRAME_PING = 5,
};

alignas(16) uint8_t arena[24 * 1024];
I2SClass microphone;
AudioFrontend frontend;
tflite::MicroInterpreter* modelRuntime = nullptr;
TfLiteTensor* modelInput = nullptr;
TfLiteTensor* modelOutput = nullptr;

int32_t rawAudio[160];
int16_t sampleRing[480];
int16_t orderedFrame[480];
float featureRing[49][24];
// Allocate the transport ring at startup instead of placing it in .dram0.bss.
// Recent ESP32 Arduino toolchains reserve more of that fixed linker region and
// otherwise fail before upload, even though sufficient internal heap remains.
int16_t* audioRing = nullptr;

unsigned sampleWrite = 0, featureWrite = 0;
unsigned samplesUntilFrame = 480;
uint32_t framesSeen = 0, workMicros = 0, networkMicros = 0, lastReport = 0;
uint32_t lastInference = 0, lastActivation = 0;
unsigned peakSinceReport = 0, activations = 0, lowScoreCount = 0;
float score = 0, maxScoreSinceReport = 0;
bool latched = false;

WiFiClient serverClient;
uint32_t lastNetworkAttempt = 0, lastPing = 0;
uint64_t totalAudioSamples = 0;
bool streaming = false, triggerSent = false;
uint32_t activationId = 0, triggerDeviceMs = 0, firstSendDeviceMs = 0;
uint64_t streamReadSample = 0, streamEndSample = 0;
uint32_t streamSamplesSent = 0, streamSamplesDropped = 0, streamSequence = 0;
uint16_t triggerScoreQ15 = 0;
int16_t adpcmPredictor = 0;
uint8_t adpcmIndex = 0;

constexpr int16_t ADPCM_STEP_TABLE[89] = {
  7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
  34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143,
  157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544,
  598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
  2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845,
  8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
  27086, 29794, 32767
};
constexpr int8_t ADPCM_INDEX_TABLE[16] = {
  -1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8
};

void fail(const char* message) {
  Serial.println(message);
  while (true) delay(1000);
}

void putU16(uint8_t* out, uint16_t value) {
  out[0] = (uint8_t)(value >> 8);
  out[1] = (uint8_t)value;
}

void putU32(uint8_t* out, uint32_t value) {
  out[0] = (uint8_t)(value >> 24);
  out[1] = (uint8_t)(value >> 16);
  out[2] = (uint8_t)(value >> 8);
  out[3] = (uint8_t)value;
}

bool writeAll(const uint8_t* data, size_t length, uint32_t timeoutMs = 250) {
  const uint32_t started = millis();
  size_t written = 0;
  while (written < length && serverClient.connected()) {
    const size_t count = serverClient.write(data + written, length - written);
    if (count) {
      written += count;
    } else {
      if ((uint32_t)(millis() - started) >= timeoutMs) break;
      delay(0);
    }
  }
  return written == length;
}

bool sendFrame(uint8_t type, const uint8_t* payload, uint32_t length) {
  uint8_t header[8] = {'V', 'A', PROTOCOL_VERSION, type, 0, 0, 0, 0};
  putU32(header + 4, length);
  return writeAll(header, sizeof(header)) && (!length || writeAll(payload, length));
}

bool sendHello() {
  uint8_t payload[12] = {};
  putU32(payload, SAMPLE_RATE);
  putU16(payload + 4, 16);
  payload[6] = 1;   // mono
  payload[7] = 14;  // frozen KWS model version
  putU16(payload + 8, STREAM_FRAME_SAMPLES);
  return sendFrame(FRAME_HELLO, payload, sizeof(payload));
}

bool sendTrigger() {
  uint8_t payload[16] = {};
  putU32(payload, activationId);
  putU32(payload + 4, triggerDeviceMs);
  putU16(payload + 8, triggerScoreQ15);
  putU16(payload + 10, PRE_ROLL_MS);
  putU16(payload + 12, CAPTURE_AFTER_TRIGGER_MS);
  if (!sendFrame(FRAME_TRIGGER, payload, sizeof(payload))) return false;
  triggerSent = true;
  return true;
}

bool networkConfigured() {
  return VOICE_SERVER_ENABLED && strcmp(WIFI_SSID, "YOUR_WIFI_SSID") != 0 &&
         strlen(WIFI_SSID) > 0 && strlen(VOICE_SERVER_HOST) > 0;
}

bool ensureServerConnected(bool force = false) {
  if (!networkConfigured()) return false;
  if (serverClient.connected()) return true;
  const uint32_t now = millis();
  if (!force && (uint32_t)(now - lastNetworkAttempt) < 2000) return false;
  lastNetworkAttempt = now;
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    return false;
  }
  serverClient.stop();
  Serial.printf("Connecting to voice server %s:%u...\n", VOICE_SERVER_HOST, VOICE_SERVER_PORT);
  if (!serverClient.connect(VOICE_SERVER_HOST, VOICE_SERVER_PORT, 250)) {
    Serial.println("Voice server unavailable; local detection continues.");
    return false;
  }
  serverClient.setNoDelay(true);
  if (!sendHello()) {
    serverClient.stop();
    return false;
  }
  triggerSent = false;
  if (streaming && !sendTrigger()) {
    serverClient.stop();
    return false;
  }
  Serial.println("Voice server connected.");
  return true;
}

void connectWifi() {
  if (!networkConfigured()) {
    Serial.println("NETWORK DISABLED: edit network_config.h to enable local ASR streaming.");
    return;
  }
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("Connecting Wi-Fi to %s", WIFI_SSID);
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && (uint32_t)(millis() - started) < 12000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("Wi-Fi connected: %s | RSSI %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
    ensureServerConnected(true);
  } else {
    Serial.println("Wi-Fi unavailable; local detection continues and reconnects in background.");
  }
}

void beginAudioStream(float triggerScore) {
  ++activationId;
  triggerDeviceMs = millis();
  triggerScoreQ15 = (uint16_t)constrain((int)lroundf(triggerScore * 32767.0f), 0, 32767);
  const uint64_t preRollSamples = (uint64_t)SAMPLE_RATE * PRE_ROLL_MS / 1000;
  streamReadSample = totalAudioSamples > preRollSamples ? totalAudioSamples - preRollSamples : 0;
  streamEndSample = totalAudioSamples + (uint64_t)SAMPLE_RATE * CAPTURE_AFTER_TRIGGER_MS / 1000;
  streamSamplesSent = streamSamplesDropped = streamSequence = firstSendDeviceMs = 0;
  adpcmPredictor = 0;
  adpcmIndex = 0;
  streaming = true;
  triggerSent = false;
  // The idle path keeps this connection warm. Do not add a long connection
  // attempt to the activation path; the ring retains audio while the normal
  // background reconnect logic makes a short retry.
  if (ensureServerConnected()) sendTrigger();
  Serial.printf("STREAM #%lu armed: %lu ms pre-roll + %lu ms following audio\n",
                (unsigned long)activationId, (unsigned long)PRE_ROLL_MS,
                (unsigned long)CAPTURE_AFTER_TRIGGER_MS);
}

uint8_t encodeAdpcmSample(int16_t sample) {
  int difference = (int)sample - adpcmPredictor;
  uint8_t nibble = 0;
  if (difference < 0) {
    nibble = 8;
    difference = -difference;
  }
  int step = ADPCM_STEP_TABLE[adpcmIndex];
  int change = step >> 3;
  if (difference >= step) {
    nibble |= 4;
    difference -= step;
    change += step;
  }
  step >>= 1;
  if (difference >= step) {
    nibble |= 2;
    difference -= step;
    change += step;
  }
  step >>= 1;
  if (difference >= step) {
    nibble |= 1;
    change += step;
  }
  int predictor = adpcmPredictor + ((nibble & 8) ? -change : change);
  predictor = predictor < -32768 ? -32768 : (predictor > 32767 ? 32767 : predictor);
  adpcmPredictor = (int16_t)predictor;
  int index = (int)adpcmIndex + ADPCM_INDEX_TABLE[nibble];
  adpcmIndex = (uint8_t)(index < 0 ? 0 : (index > 88 ? 88 : index));
  return nibble;
}

bool sendAudioChunk(uint16_t count) {
  constexpr uint16_t PREFIX_SIZE = 22;
  uint8_t payload[PREFIX_SIZE + (STREAM_FRAME_SAMPLES + 1) / 2] = {};
  putU32(payload, activationId);
  putU32(payload + 4, streamSequence);
  putU32(payload + 8, (uint32_t)streamReadSample);
  const uint32_t sendMs = millis();
  putU32(payload + 12, sendMs);
  const int16_t framePredictor = adpcmPredictor;
  const uint8_t frameIndex = adpcmIndex;
  putU16(payload + 16, (uint16_t)framePredictor);
  payload[18] = frameIndex;
  payload[19] = CODEC_IMA_ADPCM;
  putU16(payload + 20, count);
  for (uint16_t i = 0; i < count; ++i) {
    const uint8_t nibble = encodeAdpcmSample(audioRing[(streamReadSample + i) % AUDIO_RING_SAMPLES]);
    if (i & 1) payload[PREFIX_SIZE + i / 2] |= (uint8_t)(nibble << 4);
    else payload[PREFIX_SIZE + i / 2] = nibble;
  }
  if (!sendFrame(FRAME_AUDIO, payload, PREFIX_SIZE + (count + 1) / 2)) return false;
  if (!firstSendDeviceMs) firstSendDeviceMs = sendMs;
  streamReadSample += count;
  streamSamplesSent += count;
  ++streamSequence;
  return true;
}

void finishAudioStream() {
  uint8_t payload[20] = {};
  putU32(payload, activationId);
  putU32(payload + 4, streamSamplesSent);
  putU32(payload + 8, streamSamplesDropped);
  putU32(payload + 12, triggerDeviceMs);
  putU32(payload + 16, firstSendDeviceMs);
  if (serverClient.connected()) sendFrame(FRAME_END, payload, sizeof(payload));
  const uint32_t triggerToSend = firstSendDeviceMs ? firstSendDeviceMs - triggerDeviceMs : 0;
  Serial.printf("STREAM #%lu complete: %lu samples, %lu dropped, trigger-to-first-send=%lu ms\n",
                (unsigned long)activationId, (unsigned long)streamSamplesSent,
                (unsigned long)streamSamplesDropped, (unsigned long)triggerToSend);
  streaming = false;
  triggerSent = false;
}

void serviceAudioStream() {
  if (!streaming) return;
  const uint64_t oldestAvailable = totalAudioSamples > AUDIO_RING_SAMPLES
                                       ? totalAudioSamples - AUDIO_RING_SAMPLES
                                       : 0;
  if (streamReadSample < oldestAvailable) {
    streamSamplesDropped += (uint32_t)(oldestAvailable - streamReadSample);
    streamReadSample = oldestAvailable;
  }
  if (!ensureServerConnected()) return;
  if (!triggerSent && !sendTrigger()) return;

  const uint32_t started = micros();
  unsigned framesThisLoop = 0;
  while (framesThisLoop < 12 && streamReadSample < totalAudioSamples &&
         streamReadSample < streamEndSample) {
    const uint64_t newestNeeded = totalAudioSamples < streamEndSample ? totalAudioSamples : streamEndSample;
    const uint64_t available = newestNeeded - streamReadSample;
    const uint16_t count = (uint16_t)(available < STREAM_FRAME_SAMPLES ? available : STREAM_FRAME_SAMPLES);
    if (!sendAudioChunk(count)) {
      serverClient.stop();
      break;
    }
    ++framesThisLoop;
  }
  networkMicros += micros() - started;
  if (streamReadSample >= streamEndSample && totalAudioSamples >= streamEndSample)
    finishAudioStream();
}

void serviceIdleNetwork() {
  if (!networkConfigured()) return;
  ensureServerConnected();
  if (serverClient.connected() && (uint32_t)(millis() - lastPing) >= 5000) {
    uint8_t payload[4];
    putU32(payload, millis());
    if (!sendFrame(FRAME_PING, payload, sizeof(payload))) serverClient.stop();
    lastPing = millis();
  }
}

void runPrediction() {
  float means[24];
  windowMeans(featureRing, featureWrite, means);
  unsigned outIndex = 0;
  for (unsigned t = 0; t < 49; ++t) {
    const unsigned row = (featureWrite + t) % 49;
    for (unsigned band = 0; band < 24; ++band) {
      int q = (int)nearbyintf((featureRing[row][band] - means[band]) / modelInput->params.scale)
              + modelInput->params.zero_point;
      q = q < -128 ? -128 : (q > 127 ? 127 : q);
      modelInput->data.int8[outIndex++] = (int8_t)q;
    }
  }
  const uint32_t start = micros();
  if (modelRuntime->Invoke() != kTfLiteOk) fail("ERROR: model inference failed");
  lastInference = micros() - start;
  score = (modelOutput->data.int8[2] - modelOutput->params.zero_point) * modelOutput->params.scale;
  if (score > maxScoreSinceReport) maxScoreSinceReport = score;
  if (score < 0.30f) ++lowScoreCount; else lowScoreCount = 0;
  if (latched && lowScoreCount >= 2 && (uint32_t)(millis() - lastActivation) >= 1000)
    latched = false;
  if (score >= STOP_THRESHOLD && !latched) {
    latched = true;
    lastActivation = millis();
    ++activations;
    Serial.printf("*** STOP DETECTED #%u | score %.4f ***\n", activations, score);
    if (!streaming) beginAudioStream(score);
  }
}

void setupModel() {
  const tflite::Model* model = tflite::GetModel(g_stop_model);
  if (model->version() != TFLITE_SCHEMA_VERSION) fail("ERROR: model schema mismatch");
  static tflite::MicroMutableOpResolver<5> resolver;
  if (resolver.AddConv2D() != kTfLiteOk || resolver.AddDepthwiseConv2D() != kTfLiteOk ||
      resolver.AddReshape() != kTfLiteOk || resolver.AddFullyConnected() != kTfLiteOk ||
      resolver.AddSoftmax() != kTfLiteOk) fail("ERROR: model operations");
  static tflite::MicroInterpreter runtime(model, resolver, arena, sizeof(arena));
  modelRuntime = &runtime;
  if (runtime.AllocateTensors() != kTfLiteOk) fail("ERROR: model arena too small");
  modelInput = runtime.input(0);
  modelOutput = runtime.output(0);
  if (modelInput->type != kTfLiteInt8 || modelInput->bytes != 1176 ||
      modelOutput->type != kTfLiteInt8 || modelOutput->bytes != 3)
    fail("ERROR: model input/output mismatch");

  Serial.println("EXPANDED MODEL V14: checking reference inputs");
  int worstDifference = 0;
  for (unsigned v = 0; v < g_test_count; ++v) {
    memcpy(modelInput->data.int8, g_test_inputs + v * g_input_size, g_input_size);
    const uint32_t started = micros();
    if (runtime.Invoke() != kTfLiteOk) fail("ERROR: self-test inference");
    const uint32_t elapsed = micros() - started;
    for (unsigned c = 0; c < 3; ++c) {
      const int difference = abs((int)modelOutput->data.int8[c] - (int)g_test_outputs[v * 3 + c]);
      if (difference > worstDifference) worstDifference = difference;
    }
    Serial.printf("Self-test %u: %lu us | actual [%d,%d,%d] | expected [%d,%d,%d]\n",
                  v + 1, (unsigned long)elapsed,
                  (int)modelOutput->data.int8[0], (int)modelOutput->data.int8[1], (int)modelOutput->data.int8[2],
                  (int)g_test_outputs[v * 3], (int)g_test_outputs[v * 3 + 1], (int)g_test_outputs[v * 3 + 2]);
  }
  Serial.printf("Maximum reference difference: %d\n", worstDifference);
  if (worstDifference > 3) fail("ERROR: model self-test mismatch; share this log");
  Serial.println("PASS: model self-test.");
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  setupModel();
  audioRing = static_cast<int16_t*>(
      heap_caps_malloc(AUDIO_RING_BYTES, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  if (!audioRing) fail("ERROR: unable to allocate 48 KiB audio ring");
  memset(audioRing, 0, AUDIO_RING_BYTES);
  connectWifi();
  microphone.setPins(26, 33, -1, 32);
  if (!microphone.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_32BIT,
                        I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT))
    fail("ERROR: microphone initialization");
  Serial.printf("Model: %u bytes | Arena: %u reserved, %u used | Audio ring: %u | Free heap: %u\n",
                g_stop_model_len, (unsigned)sizeof(arena), (unsigned)modelRuntime->arena_used_bytes(),
                (unsigned)AUDIO_RING_BYTES, (unsigned)ESP.getFreeHeap());
  Serial.println("READY V14 STREAMING: listening for STOP.");
  Serial.println("Scores every 2 seconds. work% is pipeline wall time, not total CPU utilization.");
  lastReport = millis();
}

void loop() {
  const size_t received = microphone.readBytes((char*)rawAudio, sizeof(rawAudio));
  if (!received || received % sizeof(int32_t)) fail("ERROR: microphone read");
  const uint32_t workStart = micros();
  for (unsigned n = 0; n < received / sizeof(int32_t); ++n) {
    const int16_t pcm = (int16_t)(rawAudio[n] >> 16);
    const unsigned magnitude = pcm < 0 ? -(int)pcm : pcm;
    if (magnitude > peakSinceReport) peakSinceReport = magnitude;
    audioRing[totalAudioSamples % AUDIO_RING_SAMPLES] = pcm;
    ++totalAudioSamples;
    sampleRing[sampleWrite] = pcm;
    sampleWrite = (sampleWrite + 1) % 480;
    if (--samplesUntilFrame == 0) {
      samplesUntilFrame = 320;
      for (unsigned i = 0; i < 480; ++i) orderedFrame[i] = sampleRing[(sampleWrite + i) % 480];
      frontend.compute(orderedFrame, featureRing[featureWrite]);
      featureWrite = (featureWrite + 1) % 49;
      ++framesSeen;
      if (framesSeen >= 49 && (framesSeen - 49) % INFERENCE_EVERY_FRAMES == 0) runPrediction();
    }
  }
  workMicros += micros() - workStart;

  serviceAudioStream();
  if (!streaming) serviceIdleNetwork();

  const uint32_t now = millis();
  if ((uint32_t)(now - lastReport) >= 2000) {
    const float workPercent = workMicros / ((now - lastReport) * 10.0f);
    const float networkPercent = networkMicros / ((now - lastReport) * 10.0f);
    Serial.printf("score=%.4f | max=%.4f | peak=%u | inference=%lu us | work=%.1f%% | net=%.1f%% | heap=%u | wifi=%d | stream=%d\n",
                  score, maxScoreSinceReport, peakSinceReport, (unsigned long)lastInference,
                  workPercent, networkPercent, (unsigned)ESP.getFreeHeap(),
                  (int)WiFi.status(), streaming ? 1 : 0);
    workMicros = networkMicros = 0;
    peakSinceReport = 0;
    maxScoreSinceReport = 0;
    lastReport = now;
  }
}
