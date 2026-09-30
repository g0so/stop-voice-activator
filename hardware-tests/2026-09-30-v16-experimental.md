# V16 experimental physical comparison

- Date: 2026-09-30
- Model: rejected V16 epoch 10
- Model SHA256: `9355159564858cfc5ab219b166e29e4b10385bc90b0fae3d9eecbf105614c5a9`
- Threshold: `0.8671875` (held at V14's value for comparison; not selected for V16)
- Sketch: `outputs/live_stop_expanded_v16_experimental_streaming/live_stop_expanded_v16_experimental_streaming.ino`
- Purpose: qualitative physical comparison only

## Observed detector behavior

- STOP activated **5/5 times** in the owner's final demonstration.
- START did not activate in the final follow-up check.
- STOT still activated.
- Exact repetition counts were not retained for the START and STOT follow-up checks, so this is not a formal general-accuracy result.

The owner considers STOT unlikely in the intended demonstration environment,
but it remains a documented false-activation limitation. V16 failed public
validation because the checkpoint that rejected START-family words lost too
much general STOP recall. This physical observation does not reverse that
rejection or authorize calling V16 an accurate detector.

## Resource observation

- Model size: 13,688 bytes, the same as V14.
- Architecture and inference cadence: unchanged from V14, one inference every
  200 ms.
- Measured inference duration: approximately 26.6-26.9 ms.
- Inference-only duty estimate: approximately 13.3-13.5% of one core's wall
  time (`inference duration / 200 ms`).
- Observed diagnostic `work%`: approximately 13-19%.
- Observed diagnostic `net%` while streaming: up to approximately 23.5%.
- Lowest observed free heap: 125,588 bytes.
- Resets or allocation failures: none observed.

The firmware's `work%` and `net%` fields measure selected timed sections, not
formal total CPU utilization. Inference alone exceeds 10% of one core's wall
time, although an aggregate dual-core definition would differ. No independent
ESP32 profiler was used, so the formal idle-CPU requirement remains unverified.
Free heap and static allocation likewise do not establish whole-application
peak RAM.

The follow-up resource-test firmware now reports per-core FreeRTOS idle-counter
utilization, normalized aggregate dual-core utilization, minimum-ever internal
free heap and a conservative peak-RAM upper bound. The procedure is documented
in `docs/V16_RESOURCE_TEST.md`. Its physical result remains pending; do not
replace this paragraph with a pass until the board prints `RESOURCE RESULT`.

## Transport scope

The V14 integration already established 25 complete physical captures with
zero drops and zero sequence gaps. The final V16 check focused on detector
behavior; a new controlled V16 transport series was not recorded and is not
claimed here.
