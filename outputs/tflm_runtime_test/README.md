# ESP32 TensorFlow Lite Micro runtime check

Open `tflm_runtime_test.ino` in Arduino IDE with all three source files in this folder.
Select **ESP32 Dev Module**, upload, then open Serial Monitor at **115200 baud** and press EN/Reset.

This sketch uses the TensorFlow Lite Micro headers and precompiled runtime already installed by ESP32 board package **3.3.11**. No additional Arduino library is required with this package.

Expected behavior:

- `READY: model loaded`
- Rows comparing the model prediction with `sin(x)`, plus inference time in microseconds
- `PASS: 12 model inferences completed`

The model approximates a sine wave. Predictions should be close to the reference, but need not match exactly. PASS indicates successful execution of 12 inferences, not a measured accuracy threshold.

The test reports the model's flash size, reserved and used tensor arena, and free heap. The tensor arena is working memory for the neural network; it is not total application RAM. This tiny model does not establish the future keyword model's RAM, CPU, or accuracy. It uses neither the microphone nor Wi-Fi.

## Model source and license

The 2,488-byte int8 model is from Espressif's TensorFlow Lite Micro hello_world example:
https://github.com/espressif/esp-tflite-micro/tree/master/examples/hello_world

Downloaded model source:
https://raw.githubusercontent.com/espressif/esp-tflite-micro/master/examples/hello_world/main/model.cc

Saved as `model.cpp` for Arduino compilation. SHA-256 of the downloaded source:
`91c2d2359902b97ee940ef4df310c1d05c59910349891f17d2d79f4a14833073`

The upstream model source and header retain their Apache-2.0 copyright/license notices. This is a mathematical example, with no pre-trained wake keyword.
