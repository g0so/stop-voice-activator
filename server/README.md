# Local triggered-audio and ASR server

This server implements the missing edge-to-ASR part of SIH26172. The ESP32 keeps a TCP connection open while V14 listens locally. After STOP crosses the frozen threshold, the firmware sends 750 ms of pre-roll followed by five seconds of frame-resilient IMA ADPCM audio. The server decodes and records a PCM16 WAV file, reports timing and packet-loss telemetry, and optionally transcribes it with the open-source `faster-whisper` runtime.

## Run the receiver

From the repository root:

```bash
python3 -m venv server/.venv
server/.venv/bin/python -m pip install -r server/requirements.txt
server/.venv/bin/python server/voice_activation_server.py --model tiny.en
```

The first ASR run downloads the selected Whisper model. `requirements.txt` pins PyAV below version 19 because PyAV 19 removed an argument currently used by faster-whisper 1.2.1. To validate networking and WAV capture without installing or downloading an ASR model:

```bash
python3 server/voice_activation_server.py --no-asr
```

Open `http://127.0.0.1:8080` for the live status page. WAV and JSON evidence is stored under `server/captures/`.

## Configure and upload the ESP32

1. Edit `outputs/live_stop_expanded_v14_streaming/network_config.h`.
2. Put the computer's LAN IPv4 address in `VOICE_SERVER_HOST`. Do not use `127.0.0.1` for the ESP32.
3. Keep the computer and ESP32 on the same Wi-Fi network and allow inbound TCP port 8765.
4. Open `live_stop_expanded_v14_streaming.ino` in Arduino IDE with every file in its folder.
5. Select **ESP32 Dev Module**, ESP32 core **3.3.11**, upload, and open Serial Monitor at 115200.

If Wi-Fi or the server is unavailable, V14 continues detecting locally and retries the connection. The frozen model, threshold and self-test tolerance are unchanged.

## End-to-end check without hardware

Start the server with `--no-asr`, then in another terminal run:

```bash
python3 server/send_test_audio.py outputs/stop_check.wav --realtime
```

The receiver should create one WAV and one JSON file. The JSON includes:

- device trigger-to-first-send time;
- server trigger-frame-to-first-audio time;
- sent, received and dropped sample counts;
- sequence-gap count;
- the ASR result or error when ASR is enabled.

The server timing begins when it receives the trigger frame. For the formal SIH latency figure, record the ESP32's device trigger-to-first-send value alongside the server value and state that the KWS threshold crossing approximates keyword end.

## Verified local result

The included `outputs/stop_check.wav` completed both receiver modes:

- 80,000 of 80,000 samples arrived through the compressed path;
- zero sequence gaps and zero dropped samples;
- the encoded audio payload was 40,000 bytes versus 160,000 PCM bytes, a 75% payload reduction;
- the local `tiny.en` faster-whisper model completed transcription;
- the measured localhost values were 1 ms device trigger-to-send and about 0.3 ms server trigger-frame-to-first-audio.

The decoded test audio measured about 43.9 dB SNR against the source, and the ASR path completed. Those localhost values verify the protocol, codec and telemetry only. They are not Wi-Fi or physical-board latency claims.
