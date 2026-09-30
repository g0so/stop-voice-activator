# Local integration test report

Date: 2026-09-30

## Receiver-only test

- Input: `outputs/stop_check.wav`, mono 16 kHz PCM16, 80,000 samples
- Transport: localhost TCP using the same framed protocol as the ESP32 sketch
- Received: 80,000 samples
- PCM equality: byte-identical
- Sequence gaps: 0
- Dropped samples: 0
- Server trigger-frame-to-first-audio: 0.300 ms

## Local ASR test

- Runtime: faster-whisper 1.2.1, CTranslate2 CPU int8
- Model: `tiny.en`
- Received: 80,000 samples
- Encoded audio: 40,000 bytes
- Decoded PCM audio: 160,000 bytes
- Encoded-payload reduction: 75%
- Decoded-audio SNR against source: 43.94 dB
- Sequence gaps: 0
- Dropped samples: 0
- Device test-client trigger-to-first-send: 1 ms
- Server trigger-frame-to-first-audio: 0.25 ms
- ASR completed successfully
- Transcript returned for this short test clip: `Let's go.`

The transcript is not treated as an accuracy result. The clip was originally collected for keyword diagnostics, and the small ASR model did not reproduce the expected word. The test establishes that the triggered transport, WAV creation, ASR invocation and result path execute end to end.

All timing above is localhost test-client timing. A real ESP32/Wi-Fi run is still required for SIH latency evidence.
