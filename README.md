# STOP Voice Activator for ESP32

An open edge-to-ASR prototype for **SIH26172: Low Latency and Efficient Voice Activator for Edge Devices**.

An ESP32-WROOM-32E listens locally for **STOP** using a custom int8 keyword model. After activation, it sends 750 ms of buffered pre-roll plus five seconds of live microphone audio to a local server, which reconstructs a WAV file and can transcribe it with faster-whisper.

The complete pipeline now runs on physical hardware. Audio transport is reliable; keyword accuracy is still experimental and the current V14 model is **not** a finished detector.

## What works today

- Local 16 kHz keyword inference on ESP32 with a 49 × 24 log-mel frontend.
- Frozen V14 DS-CNN model with an on-device nine-vector numerical self-test.
- Persistent TCP connection, 750 ms pre-roll and five seconds of post-trigger audio.
- Frame-resilient 4-bit IMA ADPCM with sequence and dropped-sample telemetry.
- Local Python receiver, WAV/JSON evidence, browser dashboard and optional faster-whisper ASR.
- Physical end-to-end capture: **2,300,000/2,300,000 samples received**, with zero dropped samples and zero sequence gaps across 25 captures.
- A clear physical capture transcribed as: “Stop, turn on the laboratory light, stop.”

## Known limitation: detector accuracy

V14 reduced false activations substantially relative to V10 in public desktop evaluation, but it failed the original acceptance gates and performed poorly in the first controlled live test:

| Spoken word | Activations | Interpretation |
|---|---:|---|
| STOP | 3/10 | Seven misses |
| START | 4/5 | Four false activations |
| SHORT | 0/5 | No natural-pronunciation activation |
| STARK | 2/5 | Two false activations |
| STOT | 5/5 | Five false activations |
| SHOP | 0/5 | No activation |

This repository reports those failures deliberately. Do not present V14 as an accurate production wake-word model. See the [physical test report](hardware-tests/2026-09-30-v14-streaming.md) and [model status](docs/STATUS.md).

## Architecture

```text
INMP441 microphone
        |
        v
16 kHz PCM capture on ESP32
        |
        +--> log-mel frontend --> int8 V14 DS-CNN --> STOP decision
        |                                                |
        +--> 1.5 s PCM ring buffer                       |
                                                         v
                                      750 ms pre-roll + 5 s live audio
                                                         |
                                                         v
                                      IMA ADPCM over persistent TCP
                                                         |
                                                         v
                                      local server --> WAV/JSON --> ASR
```

The encoded audio payload is 64 kbps instead of 256 kbps PCM16. With protocol headers, the stream is approximately 88 kbps.

## Hardware

- ESP32-WROOM-32E development board
- INMP441 I2S microphone
- Computer and ESP32 on the same Wi-Fi network

| INMP441 | ESP32 |
|---|---|
| VDD | 3.3 V |
| GND | GND |
| L/R | GND |
| SCK / BCLK | GPIO 26 |
| WS / LRCLK | GPIO 33 |
| SD | GPIO 32 |

Do not power the microphone from 5 V.

## Quick start

### 1. Start the receiver

```bash
python3 -m venv server/.venv
server/.venv/bin/python -m pip install -r server/requirements.txt
server/.venv/bin/python server/voice_activation_server.py --no-asr
```

Open `http://127.0.0.1:8080` for the dashboard. Once transport works, enable transcription:

```bash
server/.venv/bin/python server/voice_activation_server.py --model tiny.en
```

The first ASR run downloads the selected open-source model.

### 2. Configure the board

Edit [`network_config.h`](outputs/live_stop_expanded_v14_streaming/network_config.h):

```cpp
constexpr char WIFI_SSID[] = "YOUR_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";
constexpr char VOICE_SERVER_HOST[] = "192.168.1.100";
```

Use the receiver computer's LAN address, not `127.0.0.1`, and never commit real credentials.

### 3. Upload the complete sketch

Open [`live_stop_expanded_v14_streaming.ino`](outputs/live_stop_expanded_v14_streaming/live_stop_expanded_v14_streaming.ino) in Arduino IDE.

- Board: **ESP32 Dev Module**
- Target ESP32 core: **3.3.11**
- Serial Monitor: **115200 baud**

Keep every file in the sketch directory. The model header, frontend sources, lookup tables and self-test vectors are all required.

Successful startup includes:

```text
PASS: model self-test.
Wi-Fi connected
Voice server connected.
READY V14 STREAMING: listening for STOP.
```

Stop if any self-test line reports `ERROR` or if the maximum reference difference exceeds 3. Continue with the [full quick start and troubleshooting guide](docs/QUICKSTART.md).

## Verified measurements

| Measurement | Result |
|---|---:|
| Physical model self-test | PASS, maximum difference 0 |
| Physical inference time | approximately 26.6–26.9 ms |
| Physical captures | 25 |
| Physical samples | 2,300,000 sent / 2,300,000 received |
| Dropped samples / sequence gaps | 0 / 0 |
| Device trigger-to-first-send | 2–3 ms |
| Server trigger-frame-to-first-audio | 0.514–7.585 ms |
| Encoded payload reduction | 75% versus PCM16 |
| Host decoded-audio SNR | approximately 43.94 dB |
| Firmware build | 1,032,904 bytes flash; 84,840 bytes static allocation |

The firmware build used ESP32 core 3.3.12 and GCC 14.2.0. The exact core version used for the physical upload was not independently recorded. Static allocation and free-heap readings do not prove whole-application peak RAM. Printed `work%` and `net%` values are selected active-section timings, not formal total CPU utilization.

## Repository map

| Path | Contents |
|---|---|
| [`outputs/live_stop_expanded_v14_streaming/`](outputs/live_stop_expanded_v14_streaming/) | Complete physical streaming candidate |
| [`server/`](server/) | Receiver, ADPCM decoder, ASR adapter, dashboard and tests |
| [`outputs/stop_model_expanded_v14/`](outputs/stop_model_expanded_v14/) | Frozen V14 model and evaluation evidence |
| [`outputs/live_stop_reviewed_v10/`](outputs/live_stop_reviewed_v10/) | Earlier physically reported fallback detector |
| [`hardware-tests/`](hardware-tests/) | Physical test template and retained result |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Runtime design |
| [`docs/PROTOCOL.md`](docs/PROTOCOL.md) | Binary transport protocol |
| [`docs/VALIDATION.md`](docs/VALIDATION.md) | Evidence and claim boundaries |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | Training, frontend and reproducibility notes |
| [`docs/COLLABORATION.md`](docs/COLLABORATION.md) | Git and board-test workflow |

Historical experiment directories are retained as provenance. V11 and V12 were rejected, V13 was interrupted, V14 was physically tested but remains inaccurate, V15 was rejected, and the final V16 hard-negative reweighting experiment was rejected because improved confusable-word rejection cost too much STOP recall. New experiments must use a new versioned directory and preserve the evaluation split discipline.

## Development checks

```bash
PYTHONPATH=server python3 -m unittest discover -s server/tests -v
python3 -m py_compile server/*.py
python3 tools/check_handoff.py
```

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before changing the detector or protocol.

## Data and licensing

Public training sources, URLs, checksums and source-specific license notes are recorded in [`outputs/PUBLIC_DATA_SOURCES.md`](outputs/PUBLIC_DATA_SOURCES.md). The detector was trained from random weights with open-source tooling; it does not use a proprietary wake-word SDK or a pretrained assistant-keyword model.

The small personal recording set is included intentionally for collaborator reproducibility. Do not upload it to third-party processing services without explicit permission.

No blanket repository license has been assigned. Preserve the notices and terms attached to each upstream dataset and dependency.
