#include <Arduino.h>
#include <math.h>
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "model.h"

// Uses the TFLite Micro runtime bundled with ESP32 Arduino 3.3.11.
// This model approximates sin(x). It is only a runtime check.
constexpr size_t ARENA_BYTES = 16 * 1024;
alignas(16) uint8_t tensorArena[ARENA_BYTES];
tflite::MicroInterpreter *interpreter = nullptr;
TfLiteTensor *input = nullptr;
TfLiteTensor *output = nullptr;

void halt(const char *message) {
  Serial.println(message);
  while (true) delay(1000);
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println("TFLite Micro: starting sine model test");
  const tflite::Model *model = tflite::GetModel(g_model);
  if (model->version() != TFLITE_SCHEMA_VERSION)
    halt("FAIL: incompatible model schema");
  static tflite::MicroMutableOpResolver<1> resolver;
  if (resolver.AddFullyConnected() != kTfLiteOk)
    halt("FAIL: could not register model operation");
  static tflite::MicroInterpreter runtime(model, resolver, tensorArena, ARENA_BYTES);
  interpreter = &runtime;
  if (interpreter->AllocateTensors() != kTfLiteOk)
    halt("FAIL: tensor allocation failed");
  input = interpreter->input(0);
  output = interpreter->output(0);
  if (input->type != kTfLiteInt8 || output->type != kTfLiteInt8)
    halt("FAIL: expected int8 input and output");
  if (input->params.scale <= 0 || output->params.scale <= 0)
    halt("FAIL: invalid quantization scale");
  Serial.printf("Model: %d bytes\n", g_model_len);
  Serial.printf("Tensor arena: %u reserved, %u used bytes\n",
                (unsigned)ARENA_BYTES, (unsigned)interpreter->arena_used_bytes());
  Serial.printf("Free heap after setup: %u bytes\n", (unsigned)ESP.getFreeHeap());
  Serial.println("READY: model loaded");
}

void loop() {
  static unsigned step = 0;
  const float x = 0.5f + 0.5f * (step % 12);
  int quantized = (int)roundf(x / input->params.scale) + input->params.zero_point;
  if (quantized < -128) quantized = -128;
  if (quantized > 127) quantized = 127;
  input->data.int8[0] = (int8_t)quantized;
  uint32_t start = micros();
  if (interpreter->Invoke() != kTfLiteOk) halt("FAIL: inference failed");
  uint32_t elapsed = micros() - start;
  const float predicted = (output->data.int8[0] - output->params.zero_point)
                          * output->params.scale;
  Serial.printf("x=%.2f | model=%.3f | sin(x)=%.3f | inference=%lu us\n",
                x, predicted, sinf(x), (unsigned long)elapsed);
  if (++step == 12) Serial.println("PASS: 12 model inferences completed");
  delay(1000);
}
