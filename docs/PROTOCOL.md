# Voice activation transport protocol

## Transport

- TCP port: `8765` by default.
- Byte stream: ordered and reliable while connected.
- Metadata integers: big-endian.
- Decoded PCM: signed 16-bit little-endian.
- Protocol version: 1.

The ESP32 keeps one connection open while idle. Frames may be split or combined by TCP; receivers must read the declared number of bytes and must not rely on socket read boundaries.

## Common frame header

Every frame begins with eight bytes:

| Offset | Size | Field | Value |
|---:|---:|---|---|
| 0 | 2 | Magic | ASCII `VA` |
| 2 | 1 | Version | `1` |
| 3 | 1 | Type | See frame types below |
| 4 | 4 | Payload length | Unsigned big-endian byte count |

The server rejects a wrong magic value, unsupported version or payload above 65,536 bytes.

## Frame types

### 1: HELLO

Sent after each TCP connection.

| Field | Type | Current value |
|---|---|---:|
| Sample rate | `uint32` | 16000 |
| Sample bits | `uint16` | 16 |
| Channels | `uint8` | 1 |
| Model version | `uint8` | 14 |
| Nominal frame samples | `uint16` | 160 |
| Reserved | `uint16` | 0 |

Payload size: 12 bytes.

### 2: TRIGGER

Begins one capture.

| Field | Type | Meaning |
|---|---|---|
| Activation ID | `uint32` | Increments for each local activation |
| Device trigger time | `uint32` | ESP32 `millis()` at threshold crossing |
| Score Q15 | `uint16` | STOP score scaled by 32767 |
| Pre-roll | `uint16` | Buffered audio duration in milliseconds |
| Following capture | `uint16` | Post-trigger duration in milliseconds |
| Reserved | `uint16` | 0 |

Payload size: 16 bytes.

### 3: AUDIO

Carries one independently decodable audio frame.

| Field | Type | Meaning |
|---|---|---|
| Activation ID | `uint32` | Must match the active trigger |
| Sequence | `uint32` | Monotonically increasing frame number |
| Sample index | `uint32` | Low 32 bits of absolute device sample index |
| Client send time | `uint32` | ESP32 `millis()` before frame transmission |
| Predictor | `int16` | IMA ADPCM predictor before the first nibble |
| Step index | `uint8` | IMA ADPCM step-table index, 0 through 88 |
| Codec | `uint8` | 0 for PCM16, 1 for IMA ADPCM |
| Sample count | `uint16` | Number of decoded samples in the frame |
| Encoded audio | variable | Codec payload |

Prefix size: 22 bytes.

For codec 1, the first sample uses the low nibble of the first encoded byte and the second sample uses the high nibble. The encoded length must equal `ceil(sample_count / 2)`.

For codec 0, the payload contains `sample_count * 2` bytes of little-endian PCM16.

### 4: END

Completes one capture.

| Field | Type | Meaning |
|---|---|---|
| Activation ID | `uint32` | Capture being completed |
| Sent samples | `uint32` | Samples submitted to transport |
| Dropped samples | `uint32` | Samples skipped after ring overrun |
| Device trigger time | `uint32` | Repeated trigger timestamp |
| First send time | `uint32` | Device time of first successful audio send |

Payload size: 20 bytes.

### 5: PING

Maintains the idle connection. Payload is one `uint32` device millisecond value.

## Server output record

Each completed capture produces a WAV file and an adjacent JSON file. The JSON includes:

- activation and model version;
- trigger score;
- audio format and capture durations;
- sent and received sample counts;
- encoded and decoded byte counts;
- payload reduction;
- dropped samples and sequence gaps;
- device trigger-to-first-send time;
- server trigger-frame-to-first-audio time;
- ASR result or ASR error.

## Compatibility

Protocol version must change if a field is removed, reordered, resized or assigned a different meaning. Adding a new frame type does not require a version change when older receivers can reject it cleanly.
