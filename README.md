# Edge voice activator for ESP32

An open-source edge-to-ASR prototype for **SIH26172: Low Latency and Efficient Voice Activator for Edge Devices**.

The system runs a custom keyword detector locally on an **ESP32-WROOM-32E** with an **INMP441** microphone. When the frozen V14 model detects **STOP**, the ESP32 sends buffered and following audio to a local server. The server reconstructs a WAV file, reports transport telemetry and can transcribe the recording with an open-source Whisper runtime.

This repository contains a working software integration and reproducible model evidence. Physical-board validation of the combined Wi-Fi application is still pending.

## System overview

```text
INMP441 microphone
        |
        v
16 kHz PCM capture on ESP32
        |
        +--> 49 x 24 log-mel frontend --> int8 V14 DS-CNN --> STOP decision
        |                                                        |
        +--> 1.5 s PCM ring buffer                               |
                                                                 v
                                                   750 ms pre-roll + 5 s audio
                                                                 |
                                                                 v
                                               IMA ADPCM over persistent TCP
                                                                 |
                                                                 v
                                           Local server --> WAV --> faster-whisper
```

The persistent TCP connection removes connection setup from the activation path. Audio payloads use 4-bit IMA ADPCM, reducing 256 kbps PCM16 to 64 kbps encoded audio. Including protocol headers, the stream is approximately 88 kbps.

## Current status

| Component | Status |
|---|---|
| V14 keyword model | Frozen and desktop-evaluated; failed the original acceptance gates but improves substantially over V10 on public false activations |
| ESP32 frontend and self-test | Preserved byte-for-byte from packaged V14 |
| Triggered audio transport | Implemented with pre-roll, reconnection, sequence tracking and drop telemetry |
| Compression | Frame-resilient IMA ADPCM implemented and tested |
| Local receiver | Implemented; saves WAV and JSON evidence |
| Local ASR | Implemented with faster-whisper and tested on the host |
| Browser status page | Implemented at port 8080 |
| Firmware compilation | Passed with ESP32 core 3.3.12 and GCC 14.2.0 after moving the 48 KiB audio ring to checked internal-heap allocation |
| Physical V14 board test | Pending on the target core 3.3.11 setup |
| Formal idle CPU and peak RAM | Pending physical measurement |

V14 remains a **baseline-improvement candidate**, not a finished accurate detector. In continuous desktop read-speech replay it produced about 68 false activations per hour. See [model status](docs/STATUS.md) for the complete interpretation.

## Quick start

### 1. Start the local server

```bash
python3 -m venv server/.venv
server/.venv/bin/python -m pip install -r server/requirements.txt
server/.venv/bin/python server/voice_activation_server.py --model tiny.en
```

The first ASR run downloads the selected open-source model. To test transport and WAV creation without ASR:

```bash
python3 server/voice_activation_server.py --no-asr
```

Open `http://127.0.0.1:8080` to view the server state and latest result.

### 2. Configure the ESP32

Edit [`network_config.h`](outputs/live_stop_expanded_v14_streaming/network_config.h):

```cpp
constexpr char WIFI_SSID[] = "YOUR_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";
constexpr char VOICE_SERVER_HOST[] = "192.168.1.100";
```

Use the computer's LAN address, not `127.0.0.1`.

### 3. Upload the integration sketch

Open [`live_stop_expanded_v14_streaming.ino`](outputs/live_stop_expanded_v14_streaming/live_stop_expanded_v14_streaming.ino) in Arduino IDE.

- Board: **ESP32 Dev Module**
- Target ESP32 core: **3.3.11**
- Serial Monitor: **115200 baud**

Keep every file in the sketch folder. The model header, frontend sources, lookup tables and test vectors are all required.

### 4. Test activation

Wait for all of the following:

```text
PASS: model self-test.
Wi-Fi connected
Voice server connected.
READY V14 STREAMING: listening for STOP.
```

Say **STOP**, then speak the sentence that the remote ASR should transcribe. The server writes a WAV and JSON record under `server/captures/`.

See the [complete quick start](docs/QUICKSTART.md) for wiring, firewall notes, expected logs and troubleshooting.

## Hardware wiring

| INMP441 pin | ESP32 connection |
|---|---|
| VDD | 3.3 V |
| GND | GND |
| L/R | GND for left channel |
| SCK / BCLK | GPIO 26 |
| WS / LRCLK | GPIO 33 |
| SD | GPIO 32 |

The firmware reads 32-bit I2S slots at 16 kHz and converts them to signed PCM16 by shifting right 16 bits.

## Verified host results

- Firmware compilation: **1,032,904 bytes flash**, **84,840 bytes static dynamic-memory allocation** with ESP32 core 3.3.12 and GCC 14.2.0. The 48 KiB runtime audio-ring allocation is not included in the static figure.
- Compressed integration test: **80,000/80,000 samples**, zero sequence gaps, zero dropped samples.
- Audio payload: **40,000 encoded bytes** versus **160,000 PCM bytes**, a 75% payload reduction.
- Decoded test-audio SNR: approximately **43.94 dB**.
- Local protocol and codec tests: **4 passed**.
- Local faster-whisper path: completed successfully.

Localhost timing verifies instrumentation only. It is not physical ESP32/Wi-Fi latency evidence. See [validation and evidence](docs/VALIDATION.md).

## Repository guide

| Path | Purpose |
|---|---|
| [`outputs/live_stop_expanded_v14_streaming/`](outputs/live_stop_expanded_v14_streaming/) | Complete V14 integration sketch and build report |
| [`server/`](server/) | TCP receiver, ADPCM decoder, ASR backend, dashboard and tests |
| [`outputs/stop_model_expanded_v14/`](outputs/stop_model_expanded_v14/) | Frozen V14 model evidence and desktop results |
| [`outputs/live_stop_expanded_v14/`](outputs/live_stop_expanded_v14/) | Model-only V14 board candidate |
| [`outputs/live_stop_reviewed_v10/`](outputs/live_stop_reviewed_v10/) | Previously compiled fallback detector |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | End-to-end design and runtime behavior |
| [`docs/PROTOCOL.md`](docs/PROTOCOL.md) | Binary transport specification |
| [`docs/QUICKSTART.md`](docs/QUICKSTART.md) | Installation and first-run guide |
| [`docs/VALIDATION.md`](docs/VALIDATION.md) | Evidence, limitations and board test procedure |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | Model and frontend development details |

## Important limitations

- V14 did not pass the original keyword acceptance gates.
- The combined application has not yet run on the physical ESP32.
- The build's static-memory figure is not whole-application peak RAM.
- Printed `work%` and `net%` values measure selected active sections, not formal total CPU utilization.
- The included same-speaker personal test recordings are small and have been reused during development.
- The `tiny.en` ASR result from the diagnostic clip is pipeline evidence, not an ASR accuracy result.
- STOP is the demonstration keyword. Another assigned keyword requires new training and evaluation.

## Data and licensing

Training data sources and their licenses are documented in [`outputs/PUBLIC_DATA_SOURCES.md`](outputs/PUBLIC_DATA_SOURCES.md). The detector was trained from random weights with open-source tooling. No proprietary wake-word SDK or pre-trained assistant keyword model is used.

No blanket repository license has been assigned. Preserve the notices and terms attached to each upstream dataset and dependency.
