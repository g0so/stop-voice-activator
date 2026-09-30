# ESP32 V14 streaming test report

- Date/time:
- Tester:
- Git commit:
- Sketch: `outputs/live_stop_expanded_v14_streaming/live_stop_expanded_v14_streaming.ino`
- Model SHA256: `4be984725547bc3702a6ef3c455a151096eb8138a400fa284b8fb670a5248429`
- Board: ESP32 Dev Module
- ESP32 core:
- Server computer / operating system:
- Server command:
- Distance / room / fan / noise:

## Startup

- Self-test PASS or ERROR:
- Maximum reference difference:
- Model bytes:
- Arena reserved / used:
- Audio-ring bytes:
- Free heap after startup:
- Wi-Fi IP / RSSI:
- Server connection successful:
- Full serial log file:

## Detection test

| Word | Times spoken | Detections | Extra triggers | Streams created |
|---|---:|---:|---:|---:|
| STOP | 10 | | | |
| START | 5 | | | |
| SHORT | 5 | | | |
| STARK | 5 | | | |
| STOT | 5 | | | |
| SHOP | 5 | | | |

## Transport evidence

| Activation | Sent samples | Received samples | Dropped | Sequence gaps | Device trigger-to-send ms | Server trigger-to-audio ms | Transcript |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | | | | | | | |

- WAV and JSON folder:
- Unexpected disconnects or reconnects:
- Audible clipping at the start:
- Audible gaps or corruption:

## Runtime observations

- Inference time:
- Printed work% range:
- Printed net% range while streaming:
- Lowest observed free heap:
- Independent total CPU measurement method/result:
- Peak RAM measurement method/result:

The printed percentages are selected active-section timings, not formal total CPU utilization. Free heap and static allocation do not establish whole-application peak RAM.
