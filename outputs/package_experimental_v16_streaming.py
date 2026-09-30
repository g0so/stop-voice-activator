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
    source_code = source_code.replace(
        "#include <esp_heap_caps.h>",
        "#include <esp_heap_caps.h>\n#include <freertos/idf_additions.h>",
    )
    source_code = source_code.replace(
        "constexpr uint8_t CODEC_IMA_ADPCM = 1;",
        "constexpr uint8_t CODEC_IMA_ADPCM = 1;\n"
        "constexpr uint32_t RESOURCE_WARMUP_MS = 30000;\n"
        "constexpr uint64_t RESOURCE_WINDOW_US = 60000000ULL;\n"
        "constexpr uint32_t APP_DRAM_BUDGET_BYTES = 327680;\n"
        "constexpr uint32_t RAM_LIMIT_BYTES = 256 * 1024;",
    )
    source_code = source_code.replace(
        "bool latched = false;",
        "bool latched = false;\n"
        "uint32_t lastCpuSampleUs = 0;\n"
        "configRUN_TIME_COUNTER_TYPE lastIdle0Us = 0, lastIdle1Us = 0;\n"
        "uint64_t resourceElapsedUs = 0, resourceIdle0Us = 0, resourceIdle1Us = 0;\n"
        "bool resourceIntervalIdle = true, resourceResultPrinted = false;",
    )
    source_code = source_code.replace(
        "void beginAudioStream(float triggerScore) {",
        "void beginAudioStream(float triggerScore) {\n  resourceIntervalIdle = false;",
    )
    source_code = source_code.replace(
        'Serial.println("Scores every 2 seconds. work% is pipeline wall time, not total CPU utilization.");\n'
        "  lastReport = millis();",
        'Serial.println("Scores every 2 seconds. cpu0/cpu1/cpu_total use FreeRTOS idle counters.");\n'
        '  Serial.println("RESOURCE TEST: keep the device listening without triggering for 90 seconds.");\n'
        "  lastReport = millis();\n"
        "  lastCpuSampleUs = micros();\n"
        "  lastIdle0Us = ulTaskGetIdleRunTimeCounterForCore(0);\n"
        "  lastIdle1Us = ulTaskGetIdleRunTimeCounterForCore(1);",
    )
    report_start = "    const float workPercent = workMicros / ((now - lastReport) * 10.0f);"
    report_end = "    workMicros = networkMicros = 0;"
    start = source_code.index(report_start)
    end = source_code.index(report_end, start)
    resource_report = '''    const uint32_t cpuNowUs = micros();
    const configRUN_TIME_COUNTER_TYPE idle0Now = ulTaskGetIdleRunTimeCounterForCore(0);
    const configRUN_TIME_COUNTER_TYPE idle1Now = ulTaskGetIdleRunTimeCounterForCore(1);
    const uint32_t cpuElapsedUs = cpuNowUs - lastCpuSampleUs;
    uint32_t idle0DeltaUs = (uint32_t)(idle0Now - lastIdle0Us);
    uint32_t idle1DeltaUs = (uint32_t)(idle1Now - lastIdle1Us);
    if (idle0DeltaUs > cpuElapsedUs) idle0DeltaUs = cpuElapsedUs;
    if (idle1DeltaUs > cpuElapsedUs) idle1DeltaUs = cpuElapsedUs;
    const float cpu0Percent = 100.0f * (1.0f - (float)idle0DeltaUs / cpuElapsedUs);
    const float cpu1Percent = 100.0f * (1.0f - (float)idle1DeltaUs / cpuElapsedUs);
    const float totalCpuPercent = (cpu0Percent + cpu1Percent) * 0.5f;
    const float workPercent = workMicros / ((now - lastReport) * 10.0f);
    const float networkPercent = networkMicros / ((now - lastReport) * 10.0f);
    Serial.printf("score=%.4f | max=%.4f | peak=%u | inference=%lu us | work=%.1f%% | net=%.1f%% | cpu0=%.1f%% | cpu1=%.1f%% | cpu_total=%.1f%% | heap=%u | min_heap=%u | wifi=%d | stream=%d\\n",
                  score, maxScoreSinceReport, peakSinceReport, (unsigned long)lastInference,
                  workPercent, networkPercent, cpu0Percent, cpu1Percent, totalCpuPercent,
                  (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap(),
                  (int)WiFi.status(), streaming ? 1 : 0);

    if (!resourceResultPrinted && now >= RESOURCE_WARMUP_MS && resourceIntervalIdle) {
      resourceElapsedUs += cpuElapsedUs;
      resourceIdle0Us += idle0DeltaUs;
      resourceIdle1Us += idle1DeltaUs;
      if (resourceElapsedUs >= RESOURCE_WINDOW_US) {
        const float measuredCpu0 = 100.0f * (1.0f - (double)resourceIdle0Us / resourceElapsedUs);
        const float measuredCpu1 = 100.0f * (1.0f - (double)resourceIdle1Us / resourceElapsedUs);
        const float measuredTotal = (measuredCpu0 + measuredCpu1) * 0.5f;
        const uint32_t minimumFree = ESP.getMinFreeHeap();
        const uint32_t peakRam = minimumFree < APP_DRAM_BUDGET_BYTES
                                     ? APP_DRAM_BUDGET_BYTES - minimumFree
                                     : 0;
        Serial.printf("RESOURCE RESULT | idle_window=%.1f s | cpu0=%.2f%% | cpu1=%.2f%% | cpu_total=%.2f%% | CPU_%s (<10%%) | min_heap=%u | peak_ram_upper=%u | RAM_%s (<262144)\\n",
                      resourceElapsedUs / 1000000.0, measuredCpu0, measuredCpu1,
                      measuredTotal, measuredTotal < 10.0f ? "PASS" : "FAIL",
                      (unsigned)minimumFree, (unsigned)peakRam,
                      peakRam < RAM_LIMIT_BYTES ? "PASS" : "FAIL");
        resourceResultPrinted = true;
      }
    }
    lastCpuSampleUs = cpuNowUs;
    lastIdle0Us = idle0Now;
    lastIdle1Us = idle1Now;
    resourceIntervalIdle = !streaming;
'''
    source_code = source_code[:start] + resource_report + source_code[end:]
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
