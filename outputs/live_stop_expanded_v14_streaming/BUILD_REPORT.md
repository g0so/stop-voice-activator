# Integration build report

- Date: 2026-09-30
- Board FQBN: `esp32:esp32:esp32` (ESP32 Dev Module)
- Locally available ESP32 core: 3.3.12
- Arduino CLI: 1.5.1, official Linux x86-64 release, SHA256 `28a8e119c498a25607821c36cb2dc49e8463941b261a0d99091baa7bc692dd2b`
- Current result after the internal-heap ring fix: compilation passed
- Flash: 1,032,904 / 1,310,720 bytes (78%)
- Static dynamic-memory allocation: 84,840 / 327,680 bytes (25%)
- Build-reported space remaining before runtime allocations: 242,840 bytes

The first integration attempt used a two-second, 64 KiB audio ring and exceeded ESP32 internal DRAM by 7,872 bytes after Wi-Fi was linked. The final sketch uses a 1.5-second, 48 KiB ring. This preserves the 750 ms pre-roll and provides 750 ms of catch-up capacity while the local network drains the buffer.

On the owner's GCC 14.2.0 ESP32 toolchain, placing that ring in global
`.dram0.bss` overflowed the fixed linker region by 8,264 bytes. The ring is now
allocated from checked internal 8-bit heap before Wi-Fi starts. Its size and
capture behavior are unchanged; startup stops with an explicit error if the
48 KiB allocation is unavailable. Recompilation with ESP32 core 3.3.12 and
that toolchain passed with the current figures above.

This compile does not establish whole-application peak RAM, idle CPU below 10%, loss-free I2S capture during live Wi-Fi transmission, or physical-board timing. Those require the serial log and receiver JSON from a real test.
