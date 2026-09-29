# Reviewed restart V10-R1 — corrected runtime reference, board confirmation pending

## Frozen-model results

| Check | Result |
|---|---|
| Fresh local test STOP recordings | 4/4 detected at all ten 200 ms timing offsets |
| Fresh local test other-word recordings | 0/4 false activations at all offsets |
| Duplicate triggers on local STOP recordings | 0 |
| Public regression STOP recordings (reference runtime) | 87/101 detected (86.1%) |
| Public regression other-word recordings (reference runtime) | 8/677 false activations |
| Public synthetic background | 0/150 triggers |
| Model | 13,288 bytes, fully integer input/output/operations |
| Fixed threshold | 0.8671875 |

The four negative test recordings contain two shop, one start and one shit. Test membership was fixed before training; checkpoint and threshold were written to frozen_selection.json before scoring these eight recordings. The same eight recordings are replayed at ten offsets, so there are eight recorded utterances, not 80 independent samples. All are from one speaker and one room. This is a promising local sanity check, not evidence of near-zero false activations in general use. The public set is a repeatedly used regression set.

## What changed

Each mel band's temporal mean is subtracted over the latest 49-frame window. This removes its steady level while preserving changes through time. The model is a wider depthwise-separable CNN with 16/24/32 channels, trained from random weights, with the same 49×24 input and three output classes. Parameters: 5,899. No pretrained assistant keyword model is used.

The small raw-feature V7 model, small centered V8 model, and V9 score-temperature variant did not meet combined validation gates and were rejected without opening the new test results. V10 used more diverse public training replay (up to 6,000 examples per class without replacement, with class weights totaling 2,000 each) alongside the reviewed device recordings.

## Training and selection

- 16 reviewed device recordings for gradients, eight separate validation recordings, eight fresh final test recordings. Exact membership: dataset_manifest.json. Earlier device speech recordings, partial sessions and rejected retakes are excluded.
- Public training includes clean and noise-augmented examples from the existing training partition. It includes the earlier fan noise augmentation, not old device speech labels. Original public speaker split is preserved.
- 160 timing/gain/noise variants per device training recording, staying in its original split. Half of negative variants sample the full five-second recording; the rest focus around automatically located speech. Positive crops use a speech-energy estimate. Full recordings were reviewed by the user; crop locations are automatic.
- Seed 20261002; 80 epochs. Selected best weighted-validation-loss checkpoint from epoch 57, then compared with each tenth epoch after integer quantization. Integer calibration uses training examples only.
- Gate: zero triggers on four local negative validation recordings at any scanned alignment; at least three of four local STOP detections at every prediction phase; at least 70% clean public validation STOP recall; at most 1% public other-word false activations separately clean/noisy; zero validation background activations.
- Ranking among passing candidates: worst-phase local STOP detection, mean local STOP detection, average public validation recall, then lower threshold. Selection and unsuccessful candidates are preserved in validation_selection.json.
- Selected model detects 4/4 validation STOP clips at every timing phase, with no validation negative triggers. Public validation: 90/106 STOP detections in both clean and noisy groups; 6/633 clean and 4/633 noisy other-word false activations.
- SHA-256: f4cfb4a730d8318e5239c1cb5c3a234ef904744c5233fbc28d183379fc0d97e0.

## Firmware verification

Sketch: ../live_stop_reviewed_v10/live_stop_reviewed_v10.ino. Includes the matching per-window centering; do not copy only the new model into an older sketch.

Compiled for ESP32 Dev Module (esp32:esp32:esp32): 399,888 bytes flash, 59,916 bytes static RAM. Tensor arena reserves 24 KiB. Static RAM is not whole-application peak RAM. The build has no Wi-Fi or ASR streaming.

Actual C++ frontend and shared centering helper compared with Python across 96 windows from training/validation recordings and rotating ring positions: maximum float difference 1.13e-06; one of 112,896 input features differed by one integer step; model outputs matched exactly in all windows. This is host verification; MCU numerical verification is pending.

At startup, the board runs six reference model inputs (drawn from training data), checks outputs within three integer steps, then starts the microphone. Prediction cadence remains 200 ms. The larger model's physical inference time, idle CPU use and peak RAM have not been measured. Existing work% is timed pipeline wall time, not total CPU utilization. Under-10% CPU and the full under-256-KB RAM requirement are not established. Audio streaming latency remains unimplemented/unmeasured.

## Next small step

Upload the complete V10 sketch folder, open Serial Monitor at 115200, and reset. Share startup PASS/READY and status rows. Then try STOP ten times, followed by SHOP, START and SHIT five times each, leaving three seconds between utterances. Count detections per word. Keep the frozen threshold unchanged during this first live comparison.

## September 29 self-test correction (R1)

User reported maximum reference difference 20 on the board, and inference times 26,622–27,025 microseconds. The sketch stopped before microphone setup. This is not evidence of bad audio data.

Reproduced the exact maximum difference on the desktop: default XNNPACK-accelerated inference returns [112,-112,-128] for reference input 1; both BUILTIN_REF and BUILTIN_WITHOUT_DEFAULT_DELEGATES return [92,-93,-128]. The other five supplied vectors agree across all three desktop modes. The board's individual outputs were not included in the original log, so a matching maximum alone does not prove every MCU result yet.

R1 regenerates expected outputs with BUILTIN_REF and prints all three actual and expected values for each self-test input. The model bytes/hash, inputs, threshold 0.8671875, microphone processing, and maximum allowed difference 3 are unchanged. Original accelerated vectors are preserved in test_vectors_accelerated_original.h. Future reviewed-training scripts now explicitly use the reference interpreter for selection and output generation.

Rechecked frozen-model results without retuning: local validation and test both detect all four STOP recordings and reject all four negative recordings across all timing phases. Public validation: 90/106 clean STOP with 6/633 false activations, 89/106 noisy STOP with 5/633 false activations, zero background triggers. Original validation gates still hold. Public test regression changes to 87/101 STOP and 8/677 false activations, zero synthetic-background triggers. Original accelerated metrics remain in metrics.json; corrected results are in reference_runtime_audit.json. This is a recheck of the same test data, not another independent test.

Repeated host frontend parity under BUILTIN_REF: 96 windows, identical model outputs; frontend_parity_reference.json. R1 compiles successfully. Physical R1 self-test remains pending. Approximately 26.6 ms per inference at five predictions per second is about 133 ms of timed inference wall time per second, before feature processing. This does not establish compliance with the total-CPU requirement, and optimization is still needed.
