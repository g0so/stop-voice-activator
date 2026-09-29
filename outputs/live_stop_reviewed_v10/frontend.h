#pragma once
#include <stdint.h>

// Streaming PCM16 -> float log-mel features. Matches outputs/audio_features.py.
class AudioFrontend {
 public:
  void compute(const int16_t* pcm480, float* mel24);
 private:
  float real_[512];
  float imag_[512];
  float power_[257];
};
