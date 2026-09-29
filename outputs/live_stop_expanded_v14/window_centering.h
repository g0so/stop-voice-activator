#pragma once
// V10 requires per-band temporal centering over the complete 49-frame window.
// Shared by the sketch and host parity check. Leaves the rolling features intact.
inline void windowMeans(const float (&frames)[49][24], unsigned first, float (&means)[24]) {
  for (unsigned band = 0; band < 24; ++band) {
    float total = 0.0f;
    for (unsigned t = 0; t < 49; ++t) total += frames[(first + t) % 49][band];
    means[band] = total / 49.0f;
  }
}
