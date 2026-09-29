#include "frontend.h"
#include "window_centering.h"
extern "C" void centered_features(const int16_t* pcm, float* output, unsigned first) {
  AudioFrontend frontend;
  float frames[49][24];
  float means[24];
  for (unsigned t=0;t<49;++t) frontend.compute(pcm+t*320,frames[(first+t)%49]);
  windowMeans(frames,first,means);
  for(unsigned t=0;t<49;++t) for(unsigned b=0;b<24;++b)
    output[t*24+b]=frames[(first+t)%49][b]-means[b];
}
