# V16 physical CPU and peak-RAM test

This test measures the rejected V16 comparison firmware in its normal
always-listening state. It does not change the model, threshold, frontend or
inference cadence.

## Method

- CPU: FreeRTOS per-core idle runtime counters, sampled over a 60-second
  listening window after a 30-second startup warm-up.
- `cpu_total`: mean utilization across both ESP32 cores. This is the value
  compared with the project's total-idle-CPU limit of 10%.
- RAM: the minimum-ever internal free heap since boot is subtracted from the
  ESP32 Dev Module application's 327,680-byte DRAM budget. This is a
  conservative upper bound because the minimum-free API combines per-region
  low-water marks that may have occurred at different times.
- Limit: CPU below 10%; peak RAM below 262,144 bytes (256 KiB).

The sketch also prints `cpu0` and `cpu1`. Do not describe `cpu_total` as a
single-core result: inference alone takes about 26.7 ms every 200 ms and can
therefore exceed 10% on the core running it.

## Board procedure

1. Upload the complete
   `outputs/live_stop_expanded_v16_experimental_streaming/` sketch folder.
2. Open Serial Monitor at 115200 baud.
3. Do not speak the trigger word and do not press `T` for 90 seconds.
4. Copy the complete line beginning `RESOURCE RESULT` into
   `hardware-tests/2026-09-30-v16-resource-result.md`.
5. Also record the Arduino build's flash and static RAM lines and the ESP32
   core version.

Any activation marks that two-second interval as non-idle and excludes it from
the 60-second window, so an accidental trigger only delays the result.

Do not claim a pass unless the physical line contains both `CPU_PASS` and
`RAM_PASS`. Preserve a failure exactly as printed.
