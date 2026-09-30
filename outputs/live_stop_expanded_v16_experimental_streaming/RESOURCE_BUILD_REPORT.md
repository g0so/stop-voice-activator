# V16 resource-test build report

- Date: 2026-09-30
- Target: `esp32:esp32:esp32` (ESP32 Dev Module)
- ESP32 Arduino core: 3.3.12
- Arduino CLI: 1.5.1
- Result: PASS
- Flash: 520,360 / 1,310,720 bytes (39%)
- Static dynamic-memory allocation: 68,508 / 327,680 bytes (20%)
- Build-reported space remaining before runtime allocations: 259,172 bytes

This build validates that the FreeRTOS idle-counter and minimum-free-heap
instrumentation compiles with the complete V16 experimental streaming sketch.
It does not prove physical CPU utilization or peak runtime RAM by itself; those
values must be copied from the board's `RESOURCE RESULT` serial line.
