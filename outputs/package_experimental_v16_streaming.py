#!/usr/bin/env python3
"""Package rejected V16 epoch 10 for an explicitly experimental board comparison."""
import hashlib
import json
import re
import shutil
from pathlib import Path

import numpy as np

from train_keyword import emit_array, quantized_predictions
from train_reviewed_wider import runtime

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
MODEL_DIR = BASE / "stop_model_expanded_v16"
SOURCE = BASE / "live_stop_expanded_v14_streaming"
DEST = BASE / "live_stop_expanded_v16_experimental_streaming"
THRESHOLD = 0.8671875


def main():
    status = json.loads((MODEL_DIR / "status.json").read_text())
    assert status["status"] == "rejected on validation"
    assert status["test_evaluated"] is False
    assert not (MODEL_DIR / "metrics.json").exists()
    assert not (MODEL_DIR / "frozen_selection.json").exists()
    assert not DEST.exists(), f"Refusing to overwrite {DEST}"

    DEST.mkdir()
    for name in [
        "frontend.cpp",
        "frontend.h",
        "frontend_tables.h",
        "window_centering.h",
        "network_config.h",
    ]:
        shutil.copy2(SOURCE / name, DEST / name)

    blob = (MODEL_DIR / "epoch_10.tflite").read_bytes()
    model_hash = hashlib.sha256(blob).hexdigest()
    (DEST / "stop_model_data.h").write_text(
        "#pragma once\n#include <stdint.h>\n"
        + emit_array("g_stop_model", np.frombuffer(blob, np.uint8), "unsigned char")
        + f"const unsigned int g_stop_model_len = {len(blob)};\n"
    )

    cache = ROOT / "work" / "expanded_features_v11"
    x_train = np.load(cache / "x_train.npy", mmap_mode="r")
    y_train = np.load(cache / "y_train.npy")
    rows = json.loads((cache / "rows_train.json").read_text())
    ids = [int(np.flatnonzero(y_train == c)[j]) for c in range(3) for j in range(2)]
    for word in ["short", "start", "stark"]:
        candidates = [
            i
            for i, row in enumerate(rows)
            if row["source"] == "mswc" and row["word"] == word
        ]
        assert candidates, word
        ids.append(candidates[0])

    reference = runtime(blob)
    input_detail = reference.get_input_details()[0]
    output_detail = reference.get_output_details()[0]
    inputs = x_train[ids]
    predictions = quantized_predictions(reference, inputs)
    quantized_inputs = np.clip(
        np.rint(inputs / input_detail["quantization"][0])
        + input_detail["quantization"][1],
        -128,
        127,
    ).astype(np.int8)
    quantized_outputs = np.rint(
        predictions / output_detail["quantization"][0]
        + output_detail["quantization"][1]
    ).astype(np.int8)
    (DEST / "test_vectors.h").write_text(
        "#pragma once\n#include <stdint.h>\n"
        "// Expected outputs from TFLite BUILTIN_REF.\n"
        + emit_array("g_test_inputs", quantized_inputs, "int8_t")
        + emit_array("g_test_outputs", quantized_outputs, "int8_t")
        + f"const unsigned int g_test_count = {len(ids)};\n"
        "const unsigned int g_input_size = 1176;\n"
    )

    source_code = (SOURCE / "live_stop_expanded_v14_streaming.ino").read_text()
    source_code = source_code.replace(
        "// V14 KWS plus a persistent, low-overhead PCM16 stream to a local ASR server.\n"
        "// The KWS threshold, preprocessing, model, test vectors and tolerance are\n"
        "// unchanged from the frozen V14 board candidate.",
        "// REJECTED V16 epoch-10 experiment for controlled comparison only.\n"
        "// This model failed validation and must not be presented as a deployment candidate.\n"
        "// Threshold is held at V14's value for a direct physical comparison.",
    )
    source_code = source_code.replace("payload[7] = 14;", "payload[7] = 16;")
    source_code = source_code.replace(
        'Serial.println("EXPANDED MODEL V14: checking reference inputs");',
        'Serial.println("REJECTED V16 EXPERIMENT: checking reference inputs");',
    )
    source_code = source_code.replace(
        'Serial.println("READY V14 STREAMING: listening for STOP.");',
        'Serial.println("READY V16 EXPERIMENTAL: rejected model, test only.");',
    )
    source_code = re.sub(
        r"constexpr float STOP_THRESHOLD = [0-9.]+f;",
        f"constexpr float STOP_THRESHOLD = {THRESHOLD}f;",
        source_code,
    )
    (DEST / "live_stop_expanded_v16_experimental_streaming.ino").write_text(source_code)

    provenance = {
        "model_sha256": model_hash,
        "threshold": THRESHOLD,
        "threshold_basis": "V14 comparison threshold; not selected or approved for V16",
        "source_checkpoint": "outputs/stop_model_expanded_v16/epoch_10.tflite",
        "validation_status": "rejected",
        "held_out_test_evaluated": False,
        "reference_outputs": "TFLite BUILTIN_REF",
        "purpose": "controlled physical comparison only",
    }
    (DEST / "MODEL_PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n")
    (DEST / "README.md").write_text(
        "# V16 experimental streaming comparison\n\n"
        "This sketch packages the rejected V16 epoch-10 checkpoint for one controlled "
        "physical comparison at V14's unchanged threshold `0.8671875`. It is not a "
        "deployment candidate. V16 reduced validation START false activations but lost "
        "too much STOP recall; its held-out test was not evaluated.\n\n"
        "Edit `network_config.h`, upload the complete folder, and stop immediately if "
        "the nine-vector self-test exceeds the unchanged tolerance of three quantization "
        "steps. Compare the same STOP/START/STARK/STOT sequence against the retained V14 "
        "physical report. Do not overwrite or relabel V14 evidence.\n"
    )
    print(DEST / "live_stop_expanded_v16_experimental_streaming.ino")


if __name__ == "__main__":
    main()
