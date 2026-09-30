# V14 triggered-audio integration

This sketch keeps the frozen V14 detector unchanged and adds the missing SIH26172 edge-to-ASR handoff.

## Behavior

- V14 continues listening locally at 16 kHz and evaluates one window every 200 ms.
- The TCP connection to the local server is opened before activation and kept alive with a small ping every five seconds.
- On a STOP activation, the device sends 750 ms of buffered pre-roll plus five seconds of following mono audio.
- Audio uses frame-resilient 4-bit IMA ADPCM in 10 ms frames. The encoded audio payload is 64 kbps instead of 256 kbps PCM16. Including all protocol headers, the stream is about 88 kbps.
- Each frame carries its own decoder state plus the activation ID, sequence number, sample index and device send time, so the receiver can recover after a gap.
- Network or server failure does not stop local KWS. The device reconnects and reports samples lost if the bounded ring buffer is overtaken.
- The model threshold remains `0.8671875`; the V14 model, frontend, self-test inputs and tolerance remain unchanged.

## Before upload

Edit `network_config.h` with the Wi-Fi credentials and the computer's LAN IPv4 address. Start the server first:

```bash
python3 server/voice_activation_server.py --no-asr
```

For transcription, install `server/requirements.txt` and omit `--no-asr`.

Open `live_stop_expanded_v14_streaming.ino` with all files in this folder. Select **ESP32 Dev Module** and upload. The established microphone wiring remains BCLK 26, WS 33, DIN 32 and L/R to GND.

## Current verification

- Copied model/frontend/test-vector assets are byte-identical to the packaged V14 candidate.
- Protocol and ADPCM unit tests pass.
- A five-second, 16 kHz PCM16 local WAV completed the compressed end-to-end receiver and ASR path with 80,000/80,000 decoded samples, no sequence gaps and no dropped samples. The compressed audio payload was 40,000 bytes versus 160,000 PCM bytes, a 75% payload reduction.
- The sketch compiles with ESP32 core 3.3.12 and GCC 14.2.0: 1,032,904 bytes flash and 84,840 bytes static dynamic-memory allocation, leaving 242,840 bytes before runtime allocations. The checked 48 KiB internal-heap audio ring is allocated during startup and is not included in the static figure.

The project target remains ESP32 core 3.3.11. Core 3.3.11 was not present for this compile, so strict target-version validation still requires that version. Static allocation is not whole-application peak RAM. The printed `work%` and `net%` values are timed active sections, not formal total CPU utilization.
