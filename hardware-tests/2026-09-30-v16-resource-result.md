# V16 physical CPU and peak-RAM result

- Tested commit:
- Board: ESP32-WROOM-32E / ESP32 Dev Module
- ESP32 Arduino core version:
- Build flash line:
- Build static RAM line:
- Test state: idle listening, no trigger or manual `T`
- Serial `RESOURCE RESULT` line:

## Result

- Aggregate dual-core idle CPU:
- Core 0 CPU:
- Core 1 CPU:
- Minimum-ever internal free heap:
- Conservative peak application RAM upper bound:
- CPU below 10%: pending
- Peak RAM below 256 KiB: pending

This report must be filled from a physical run. Do not infer a pass from model
inference timing, `work%`, current free heap, or a desktop build alone.
