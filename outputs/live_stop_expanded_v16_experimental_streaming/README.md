# V16 experimental streaming comparison

This sketch packages the rejected V16 epoch-10 checkpoint for one controlled physical comparison at V14's unchanged threshold `0.8671875`. It is not a deployment candidate. V16 reduced validation START false activations but lost too much STOP recall; its held-out test was not evaluated.

Edit `network_config.h`, upload the complete folder, and stop immediately if the nine-vector self-test exceeds the unchanged tolerance of three quantization steps. Compare the same STOP/START/STARK/STOT sequence against the retained V14 physical report. Do not overwrite or relabel V14 evidence.

Qualitative board follow-up: STOP worked and START did not activate, while STOT still activated. Exact repetition counts were not retained. See `hardware-tests/2026-09-30-v16-experimental.md`; this observation does not reverse V16's validation rejection.
