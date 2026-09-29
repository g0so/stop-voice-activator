"""Reference audio frontend. Keep these exact constants for the ESP32 port."""
from pathlib import Path
import wave
import numpy as np

SAMPLE_RATE = 16000
FRAME_SAMPLES = 480
HOP_SAMPLES = 320
FFT_SIZE = 512
MEL_BINS = 24
CLIP_SAMPLES = 16000
FEATURE_SHAPE = (49, 24, 1)
WINDOW = np.hanning(FRAME_SAMPLES).astype(np.float32)  # symmetric Hann


def mel_filters():
    def mel(hz):
        return 2595.0 * np.log10(1.0 + hz / 700.0)
    edges = 700.0 * (10.0 ** (np.linspace(mel(80), mel(7600), MEL_BINS + 2) / 2595.0) - 1.0)
    frequencies = np.arange(FFT_SIZE // 2 + 1) * SAMPLE_RATE / FFT_SIZE
    filters = np.zeros((MEL_BINS, len(frequencies)), np.float32)
    for i in range(MEL_BINS):
        filters[i] = np.maximum(0, np.minimum((frequencies - edges[i]) / (edges[i+1] - edges[i]),
                                              (edges[i+2] - frequencies) / (edges[i+2] - edges[i+1])))
        filters[i] /= filters[i].sum()
    return filters


MEL_FILTERS = mel_filters()


def read_audio(path):
    with wave.open(str(path), 'rb') as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
            raise ValueError(f'Expected 16 kHz mono PCM16: {path}')
        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype(np.float32) / 32768.0
    if len(audio) > CLIP_SAMPLES:
        raise ValueError(f'Clip needs annotation/cropping before training: {path}')
    return np.pad(audio, (0, CLIP_SAMPLES - len(audio)))


def features(audio):
    audio = np.asarray(audio, dtype=np.float32)
    if audio.shape != (CLIP_SAMPLES,):
        raise ValueError('Expected exactly 16000 samples')
    frames = np.lib.stride_tricks.sliding_window_view(audio, FRAME_SAMPLES)[::HOP_SAMPLES].copy()
    frames -= frames.mean(axis=1, keepdims=True)
    spectrum = np.fft.rfft(frames * WINDOW, n=FFT_SIZE, axis=1)
    power = (spectrum.real**2 + spectrum.imag**2) / FFT_SIZE
    energy = power @ MEL_FILTERS.T
    db = 10.0 * np.log10(np.maximum(energy, 1e-10))
    return ((np.clip(db, -80.0, 0.0) + 40.0) / 40.0).astype(np.float32)[..., None]


def synthetic_background(rng):
    # Distinct seeds by split. Synthetic examples are not real-noise evaluation.
    white = rng.normal(size=CLIP_SAMPLES).astype(np.float32)
    spectrum = np.fft.rfft(white)
    spectrum /= np.maximum(1, np.arange(len(spectrum))) ** rng.uniform(0.0, 0.8)
    noise = np.fft.irfft(spectrum, n=CLIP_SAMPLES).astype(np.float32)
    noise /= max(float(np.std(noise)), 1e-6)
    t = np.arange(CLIP_SAMPLES) / SAMPLE_RATE
    hum = np.sin(2 * np.pi * rng.choice([50, 60, 100, 120]) * t + rng.uniform(0, 6.28))
    noise += hum.astype(np.float32) * rng.uniform(0, 1)
    noise *= 10.0 ** rng.uniform(-4.5, -1.6)
    if rng.random() < 0.1:
        noise[:] = 0
    return np.clip(noise, -1, 1)


def augment(audio, rng):
    # Move only when both original margins remain, avoiding keyword truncation.
    active = np.flatnonzero(np.abs(audio) > max(0.005, float(np.max(np.abs(audio))) * 0.08))
    shifted = audio.copy()
    if len(active):
        low = -min(int(active[0]), 1600)
        high = min(CLIP_SAMPLES - 1 - int(active[-1]), 1600)
        shift = int(rng.integers(low, high + 1))
        shifted = np.roll(audio, shift)
        if shift > 0:
            shifted[:shift] = 0
        elif shift < 0:
            shifted[shift:] = 0
    shifted *= 10 ** rng.uniform(-0.5, 0.3)
    noise = rng.normal(size=CLIP_SAMPLES).astype(np.float32)
    signal_rms = max(float(np.sqrt(np.mean(shifted**2))), 0.0001)
    noise *= signal_rms * 10 ** (-rng.uniform(12, 35) / 20)
    return np.clip(shifted + noise, -1, 1)
