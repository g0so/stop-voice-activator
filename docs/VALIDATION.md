# Validation and evidence

## What has been verified

### Frozen-model integrity

The integration folder's model header, frontend implementation, frontend tables and self-test vectors are byte-identical to the packaged V14 candidate. The integration changes transport behavior only.

### Firmware compilation

The original combined sketch compiled for `esp32:esp32:esp32` with the locally available ESP32 core 3.3.12. A GCC 14.2.0 build then exposed a `.dram0.bss` overflow of 8,264 bytes. The unchanged 48 KiB audio ring was moved from global BSS to checked internal-heap allocation, and the revised sketch compiles successfully with that toolchain.

| Measurement | Result |
|---|---:|
| Flash | 1,032,904 / 1,310,720 bytes |
| Static dynamic-memory allocation | 84,840 / 327,680 bytes |
| Build-reported space remaining before runtime allocations | 242,840 bytes |

The project target remains core 3.3.11, which still needs separate compilation if strict target-version parity is required. The owner's installed core 3.3.12 build now passes; physical upload remains pending.

### Protocol and codec

Four unit tests cover protocol framing, invalid magic rejection, ADPCM length handling and ADPCM reconstruction error. All pass.

### Host integration

The included five-second diagnostic WAV passed through the framed ADPCM transport, server decoder, WAV writer and faster-whisper invocation.

| Measurement | Result |
|---|---:|
| Source samples | 80,000 |
| Received samples | 80,000 |
| Sequence gaps | 0 |
| Dropped samples | 0 |
| PCM bytes | 160,000 |
| Encoded audio bytes | 40,000 |
| Encoded-payload reduction | 75% |
| Decoded-audio SNR | 43.94 dB |

The tiny ASR model returned “Let's go.” for the diagnostic clip. This establishes execution of the ASR path but does not establish transcription accuracy.

## Keyword model evidence

V14 uses the same threshold as V10-R1: `0.8671875`.

Public test comparison:

| Measure | V14 | V10-R1 |
|---|---:|---:|
| Speech Commands STOP recall | 285/354, 80.5% | 305/354, 86.2% |
| Speech Commands other-word false positives | 70/9,391 | 578/9,391 |
| MSWC STOP recall | 115/191, 60.2% | 101/191, 52.9% |
| MSWC other-word false positives | 76/2,274 | 937/2,274 |
| LibriSpeech false positives | 2/1,173 | 86/1,173 |
| Continuous read-speech replay | 68 false activations/hour | 956 false activations/hour |

V14 failed the original gates. It lost Speech Commands recall, remained above acceptable false-activation targets and regressed on two reused local recordings at some timing offsets. These limitations must remain in demonstrations and reports.

## What remains unverified

- V14 self-test on the actual ESP32.
- ESP32 core 3.3.11 compilation of the combined application.
- Loss-free I2S capture while Wi-Fi sends compressed audio.
- Real trigger-to-server latency over Wi-Fi.
- Total idle CPU utilization below 10%.
- Whole-application peak RAM below 256 KB.
- Sustained false activations in the actual demo environment.
- ASR quality on spoken post-trigger commands.

## Required physical test

### Startup

Save the complete serial log, including:

- nine self-test results;
- maximum reference difference;
- model and arena bytes;
- audio-ring bytes;
- free heap;
- IP address and RSSI;
- server connection status.

### Activation and confusable words

Use the repetitions in [`QUICKSTART.md`](QUICKSTART.md). Do not change the threshold between V14 and V10.

### Transport

For every V14 activation, retain the server JSON and check:

- received samples equal sent samples minus declared dropped samples;
- zero sequence gaps;
- zero dropped samples;
- non-null device and server latency values;
- WAV duration matches pre-roll plus following capture within framing tolerance.

### Resource measurements

Build output may support a static-allocation claim. It cannot support peak RAM. `work%` and `net%` are diagnostic active-section timings and cannot support a total CPU claim. Use platform-level runtime measurement or profiling before marking the formal limits passed.

## Claim boundary

Safe current claim:

> The repository implements and host-tests an open-source V14 edge-to-ASR pipeline with persistent triggered transport, 4-bit audio compression, loss telemetry and local transcription. The combined sketch compiles for ESP32, while physical accuracy, Wi-Fi latency, idle CPU and peak RAM remain pending.

Do not claim that V14 is a finished accurate detector or that the full system already satisfies the physical resource limits.
