# Quick start

The final physical demonstration used
`outputs/live_stop_expanded_v16_experimental_streaming/`: STOP activated 5/5
times and START did not activate in the final follow-up check. STOT remained a
known synthetic false trigger. The V14 instructions later in this document are
retained as the transport-verified baseline procedure.

## Requirements

### Hardware

- ESP32-WROOM-32E development board
- INMP441 I2S microphone
- USB data cable
- Computer and ESP32 on the same Wi-Fi network

### Computer

- Python 3.12 or another version supported by the dependencies
- Arduino IDE or Arduino CLI
- ESP32 board package 3.3.11 for the target test
- Enough disk space for the optional Whisper model

## Wiring

Disconnect power before changing wiring.

| INMP441 | ESP32 |
|---|---|
| VDD | 3.3 V |
| GND | GND |
| L/R | GND |
| SCK | GPIO 26 |
| WS | GPIO 33 |
| SD | GPIO 32 |

Do not power the microphone from 5 V.

## Server setup

From the repository root:

```bash
python3 -m venv server/.venv
server/.venv/bin/python -m pip install -r server/requirements.txt
```

Start with transport-only mode:

```bash
server/.venv/bin/python server/voice_activation_server.py --no-asr
```

Expected output:

```text
Voice receiver: 0.0.0.0:8765
Dashboard: http://127.0.0.1:8080
Captures: .../server/captures
ASR: disabled
```

After transport works, stop the server and enable ASR:

```bash
server/.venv/bin/python server/voice_activation_server.py --model tiny.en
```

The first run downloads the selected model. A larger model such as `base.en` may improve transcription at the cost of download size and CPU time.

## Find the server address

Linux:

```bash
hostname -I
```

Windows PowerShell:

```powershell
ipconfig
```

Choose the LAN IPv4 address on the same network as the ESP32, commonly an address beginning with `192.168` or `10`. Do not use `127.0.0.1`.

## Firmware configuration

Edit `outputs/live_stop_expanded_v14_streaming/network_config.h`:

```cpp
constexpr char WIFI_SSID[] = "your-network";
constexpr char WIFI_PASSWORD[] = "your-password";
constexpr char VOICE_SERVER_HOST[] = "192.168.1.100";
constexpr uint16_t VOICE_SERVER_PORT = 8765;
```

Do not commit real Wi-Fi credentials.

## Arduino upload

1. Open `outputs/live_stop_expanded_v14_streaming/live_stop_expanded_v14_streaming.ino`.
2. Select **ESP32 Dev Module**.
3. Confirm the ESP32 board package version is 3.3.11.
4. Select the board's serial port.
5. Upload.
6. Open Serial Monitor at 115200 baud.
7. Press EN/Reset once.

Do not copy only the `.ino`. Arduino needs every file in the sketch folder.

## Startup checks

The model runs nine reference vectors before microphone listening begins. Stop if the output contains `ERROR`.

Successful startup should include:

```text
Maximum reference difference: 3
PASS: model self-test.
Wi-Fi connected
Voice server connected.
READY V14 STREAMING: listening for STOP.
```

The maximum difference can be lower than 3. It must not exceed 3.

## First activation test

1. Keep the room quiet for ten seconds.
2. Say STOP once.
3. Immediately speak a clear sentence such as “turn on the laboratory light.”
4. Watch Serial Monitor for `STOP DETECTED`, `STREAM armed` and `STREAM complete`.
5. Watch the server for `TRIGGER`, `FIRST AUDIO`, `END` and `TRANSCRIPT`.
6. Open `http://127.0.0.1:8080`.
7. Confirm a WAV and JSON file appear in `server/captures/`.

## Formal comparison test

Run the same room, distance and speaking style for both the V14 integration and V10-R1.

| Word | Repetitions |
|---|---:|
| STOP | 10 |
| START | 5 |
| SHORT | 5 |
| STARK | 5 |
| STOT | 5 |
| SHOP | 5 |

Record detections, misses, duplicate triggers, unexpected streams and server telemetry. Use [`hardware-tests/STREAMING_TEMPLATE.md`](../hardware-tests/STREAMING_TEMPLATE.md).

## Host-only transport test

This checks the server without an ESP32:

```bash
python3 server/voice_activation_server.py --no-asr
```

In another terminal:

```bash
python3 server/send_test_audio.py outputs/stop_check.wav --realtime
```

This is a protocol test, not board evidence.

## Troubleshooting

### `NETWORK DISABLED`

Replace the placeholder SSID in `network_config.h` and upload again.

### ESP32 has Wi-Fi but no server connection

- Start the server before resetting the board.
- Verify the LAN IP.
- Confirm both devices use the same network.
- Allow inbound TCP port 8765 in the computer firewall.
- Avoid guest Wi-Fi that isolates clients.

### Model self-test fails

Do not change the tolerance. Confirm every V14 integration file is present and use the target board/core configuration. Save the entire log.

### WAV exists but transcription fails

The transport is still usable. Check the adjacent JSON for `asr_error`, confirm `server/requirements.txt` is installed, and retry with `--no-asr` to isolate transport from ASR.

### Dropped samples are nonzero

Improve Wi-Fi signal, keep the server on the same LAN, stop other heavy network activity and repeat. Do not present the capture as loss-free.
