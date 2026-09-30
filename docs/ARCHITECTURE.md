# Architecture

## Design goals

The system separates always-on work from expensive speech recognition:

1. The ESP32 captures microphone audio continuously.
2. A small int8 model evaluates STOP locally.
3. Audio remains local until activation.
4. A persistent TCP session carries buffered and following audio to a server.
5. The server reconstructs PCM audio and invokes open-source ASR.

This structure addresses the SIH26172 edge-to-remote-ASR requirement without running a transformer on the microcontroller.

## Edge pipeline

### Capture

- Microphone: INMP441 in left-channel I2S mode.
- Sample rate: 16,000 Hz.
- Input slots: signed 32-bit.
- PCM conversion: arithmetic shift right by 16 bits to signed PCM16.
- DMA read block: 160 samples, or 10 ms.

### Feature extraction

The frontend is unchanged from the frozen V14 package:

- 480-sample frame;
- 320-sample hop;
- 512-point FFT;
- 24 mel bands from 80 Hz to 7,600 Hz;
- 49 frames per model window;
- per-frame mean removal;
- symmetric Hann window;
- log-power features;
- per-band temporal mean subtraction over the model window.

The model input is `[1, 49, 24, 1]` int8. Output classes are background, other speech and STOP.

### Activation logic

- Frozen STOP threshold: `0.8671875`.
- Inference cadence: once every 200 ms.
- A trigger latches until the score remains below 0.30 for two predictions and at least one second has elapsed.
- The keyword threshold crossing begins one capture session. A second trigger does not start another session while one is active.

### Audio retention

The sketch maintains a 1.5-second, 48 KiB PCM ring buffer. At activation it begins reading 750 ms before the current write position, then continues until five seconds of post-trigger audio have been collected.

The original two-second ring did not fit after Wi-Fi was linked. It overflowed ESP32 internal DRAM by 7,872 bytes. The 1.5-second ring leaves 750 ms of pre-roll plus 750 ms of network catch-up capacity.

### Network behavior

- Wi-Fi and TCP connect during startup.
- The TCP connection stays open during idle listening.
- A four-byte ping is sent every five seconds.
- Connection loss does not stop local KWS.
- The device retries every two seconds.
- A failed or slow network can overtake the bounded ring. The firmware reports every skipped sample rather than hiding the loss.

## Audio compression

Each 10 ms PCM frame contains 160 samples or 320 bytes. The firmware encodes it as 80 bytes of 4-bit IMA ADPCM.

Each frame also includes its starting predictor and step index. This adds a few bytes but allows the server to decode later frames even if an earlier frame is lost or a connection restarts.

| Representation | Audio payload rate |
|---|---:|
| PCM16 mono at 16 kHz | 256 kbps |
| IMA ADPCM | 64 kbps |
| IMA ADPCM plus this protocol's headers | approximately 88 kbps |

## Server pipeline

The server uses only local components:

```text
TCP receiver
    |
    +--> protocol validation
    +--> sequence and loss accounting
    +--> IMA ADPCM decoder
    +--> PCM16 WAV writer
    +--> JSON telemetry record
    +--> faster-whisper CPU int8 transcription
    +--> terminal and browser status output
```

The receiver handles each ESP32 connection on its own thread. ASR runs in a single-worker executor so model work cannot block receipt of a transport frame on the connection thread.

## Latency instrumentation

The firmware records:

- device time at threshold crossing;
- device time at the first transmitted audio frame;
- trigger-to-first-send delta.

The server records:

- monotonic time when the trigger frame arrives;
- monotonic time when the first audio frame arrives;
- trigger-frame-to-first-audio delta.

These are complementary measurements. The server clock is not synchronized to the ESP32, so the implementation does not subtract timestamps across devices. For the formal result, report both deltas and state that threshold crossing approximates keyword end.

## Failure behavior

| Failure | Behavior |
|---|---|
| Wi-Fi unavailable at boot | Local KWS starts and reconnects in the background |
| Server unavailable | Local KWS continues; bounded audio remains available during short reconnect attempts |
| TCP write failure | Socket closes and the reconnect path retries |
| Ring overrun | Read position advances; dropped sample count increases |
| Sequence gap at server | WAV continues; JSON reports the gap |
| ASR import/model failure | WAV and transport metadata remain available; JSON records the ASR error |
| V14 self-test difference above 3 | Firmware stops before listening or streaming |

## Trust boundaries

The transport is intended for a trusted local network demonstration. It does not implement encryption or authentication. Do not expose port 8765 directly to the public internet. Production deployment should add TLS, device authentication, capture limits and server-side authorization.
