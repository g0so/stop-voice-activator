#include "frontend.h"
#include "frontend_tables.h"
#include <cmath>

void AudioFrontend::compute(const int16_t* pcm480, float* mel24) {
  // Sum in integer precision, then convert. Mean removal is per frame.
  int32_t total = 0;
  for (int i = 0; i < 480; ++i) total += pcm480[i];
  const float mean = (float)total / (480.0f * 32768.0f);
  for (int i = 0; i < 512; ++i) {
    real_[i] = i < 480 ? ((float)pcm480[i] / 32768.0f - mean) * kHann[i] : 0.0f;
    imag_[i] = 0.0f;
  }
  // In-place radix-2 FFT, using flash-resident twiddles.
  for (unsigned i = 1, j = 0; i < 512; ++i) {
    unsigned bit = 256;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      float t = real_[i]; real_[i] = real_[j]; real_[j] = t;
      t = imag_[i]; imag_[i] = imag_[j]; imag_[j] = t;
    }
  }
  for (int length = 2; length <= 512; length <<= 1) {
    const int half = length / 2;
    const int stride = 512 / length;
    for (int base = 0; base < 512; base += length) {
      for (int j = 0; j < half; ++j) {
        const int a = base + j, b = a + half, tw = j * stride;
        const float tr = kCos[tw] * real_[b] - kSin[tw] * imag_[b];
        const float ti = kCos[tw] * imag_[b] + kSin[tw] * real_[b];
        real_[b] = real_[a] - tr; imag_[b] = imag_[a] - ti;
        real_[a] += tr; imag_[a] += ti;
      }
    }
  }
  for (int i = 0; i < 257; ++i)
    power_[i] = (real_[i] * real_[i] + imag_[i] * imag_[i]) / 512.0f;
  for (int band = 0; band < 24; ++band) {
    float energy = 0.0f;
    for (int j = 0; j < kMelCount[band]; ++j)
      energy += power_[kMelStart[band] + j] * kMelWeights[kMelOffset[band] + j];
    if (energy < 1e-10f) energy = 1e-10f;
    float db = 10.0f * log10f(energy);
    if (db < -80.0f) db = -80.0f;
    if (db > 0.0f) db = 0.0f;
    mel24[band] = (db + 40.0f) / 40.0f;
  }
}
