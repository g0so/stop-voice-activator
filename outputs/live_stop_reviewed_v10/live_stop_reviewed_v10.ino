#include <Arduino.h>
#include <ESP_I2S.h>
#include <math.h>
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "stop_model_data.h"
#include "frontend.h"
#include "window_centering.h"
#include "test_vectors.h"
#include <string.h>

// Same working microphone wiring and PCM scaling as mic_recorder.
// No Wi-Fi yet: this sketch tests continuous local keyword detection.
constexpr float STOP_THRESHOLD = 0.8671875f;  // Chosen on validation data.
constexpr unsigned INFERENCE_EVERY_FRAMES = 10;  // 10 * 20 ms = 200 ms.
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
unsigned sampleWrite = 0, featureWrite = 0;
unsigned samplesUntilFrame = 480;
uint32_t framesSeen = 0, workMicros = 0, lastReport = 0;
uint32_t lastInference = 0, lastActivation = 0;
unsigned peakSinceReport = 0, activations = 0, lowScoreCount = 0;
float score = 0, maxScoreSinceReport = 0;
bool latched = false;

void fail(const char* message) {
  Serial.println(message);
  while (true) delay(1000);
}

void runPrediction() {
  float means[24];
  windowMeans(featureRing, featureWrite, means);
  unsigned outIndex = 0;
  for (unsigned t = 0; t < 49; ++t) {
    unsigned row = (featureWrite + t) % 49;
    for (unsigned band = 0; band < 24; ++band) {
      // nearbyintf is round-to-nearest-even, matching NumPy rint.
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
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  const tflite::Model* model = tflite::GetModel(g_stop_model);
  if (model->version() != TFLITE_SCHEMA_VERSION) fail("ERROR: model schema mismatch");
  static tflite::MicroMutableOpResolver<5> resolver;
  if (resolver.AddConv2D() != kTfLiteOk || resolver.AddDepthwiseConv2D() != kTfLiteOk ||
      resolver.AddReshape() != kTfLiteOk || resolver.AddFullyConnected() != kTfLiteOk ||
      resolver.AddSoftmax() != kTfLiteOk) fail("ERROR: model operations");
  static tflite::MicroInterpreter runtime(model, resolver, arena, sizeof(arena));
  modelRuntime = &runtime;
  if (runtime.AllocateTensors() != kTfLiteOk) fail("ERROR: model arena too small");
  modelInput = runtime.input(0); modelOutput = runtime.output(0);
  if (modelInput->type != kTfLiteInt8 || modelInput->bytes != 1176 ||
      modelOutput->type != kTfLiteInt8 || modelOutput->bytes != 3)
    fail("ERROR: model input/output mismatch");
  Serial.println("REVIEWED MODEL V10-R1: checking six reference inputs");
  int worstDifference = 0;
  for (unsigned v = 0; v < g_test_count; ++v) {
    memcpy(modelInput->data.int8, g_test_inputs + v * g_input_size, g_input_size);
    uint32_t started = micros();
    if (runtime.Invoke() != kTfLiteOk) fail("ERROR: self-test inference");
    uint32_t elapsed = micros() - started;
    for (unsigned c = 0; c < 3; ++c) {
      int difference = abs((int)modelOutput->data.int8[c] - (int)g_test_outputs[v * 3 + c]);
      if (difference > worstDifference) worstDifference = difference;
    }
    Serial.printf("Self-test %u: %lu us | actual [%d,%d,%d] | expected [%d,%d,%d]\n",
                  v + 1, (unsigned long)elapsed,
                  (int)modelOutput->data.int8[0], (int)modelOutput->data.int8[1], (int)modelOutput->data.int8[2],
                  (int)g_test_outputs[v * 3], (int)g_test_outputs[v * 3 + 1], (int)g_test_outputs[v * 3 + 2]);
  }
  Serial.printf("Maximum reference difference: %d\n", worstDifference);
  if (worstDifference > 3) fail("ERROR: model self-test mismatch; share this log");
  Serial.println("PASS: model self-test. Starting microphone.");
  microphone.setPins(26, 33, -1, 32);
  if (!microphone.begin(I2S_MODE_STD, 16000, I2S_DATA_BIT_WIDTH_32BIT,
                        I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT)) fail("ERROR: microphone initialization");
  Serial.printf("Model: %u bytes | Arena: %u reserved, %u used | Free heap: %u\n",
                g_stop_model_len, (unsigned)sizeof(arena), (unsigned)runtime.arena_used_bytes(),
                (unsigned)ESP.getFreeHeap());
  Serial.println("READY V10-R1: listening for STOP. Wait two seconds, then say stop naturally.");
  Serial.println("Scores every 2 seconds. work% is timed pipeline wall time, NOT total CPU utilization.");
  lastReport = millis();
}

void loop() {
  // Block while DMA gathers samples; no busy polling.
  size_t received = microphone.readBytes((char*)rawAudio, sizeof(rawAudio));
  if (!received || received % sizeof(int32_t)) fail("ERROR: microphone read");
  uint32_t workStart = micros();
  for (unsigned n = 0; n < received / sizeof(int32_t); ++n) {
    const int16_t pcm = (int16_t)(rawAudio[n] >> 16);
    unsigned magnitude = pcm < 0 ? -(int)pcm : pcm;
    if (magnitude > peakSinceReport) peakSinceReport = magnitude;
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
  const uint32_t now = millis();
  if ((uint32_t)(now - lastReport) >= 2000) {
    const float workPercent = workMicros / ((now - lastReport) * 10.0f);
    Serial.printf("score=%.4f | max=%.4f | peak=%u | inference=%lu us | work=%.1f%% | heap=%u\n",
                  score, maxScoreSinceReport, peakSinceReport, (unsigned long)lastInference,
                  workPercent, (unsigned)ESP.getFreeHeap());
    workMicros = 0; peakSinceReport = 0; maxScoreSinceReport = 0; lastReport = now;
  }
}
