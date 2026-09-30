"""Small IMA ADPCM codec used by the ESP32 transport."""

from __future__ import annotations

import struct
from collections.abc import Iterable

STEP_TABLE = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143,
    157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544,
    598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845,
    8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
    27086, 29794, 32767,
)
INDEX_TABLE = (-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8)
CODEC_PCM16 = 0
CODEC_IMA_ADPCM = 1


def _advance(nibble: int, predictor: int, index: int) -> tuple[int, int]:
    step = STEP_TABLE[index]
    change = step >> 3
    if nibble & 4:
        change += step
    if nibble & 2:
        change += step >> 1
    if nibble & 1:
        change += step >> 2
    predictor += -change if nibble & 8 else change
    predictor = max(-32768, min(32767, predictor))
    index = max(0, min(88, index + INDEX_TABLE[nibble & 0xF]))
    return predictor, index


def decode_ima_adpcm(data: bytes, predictor: int, index: int, sample_count: int) -> bytes:
    if not 0 <= index <= 88:
        raise ValueError("invalid ADPCM step index")
    if len(data) != (sample_count + 1) // 2:
        raise ValueError("ADPCM payload length does not match sample count")
    samples: list[int] = []
    for packed in data:
        for nibble in (packed & 0xF, packed >> 4):
            predictor, index = _advance(nibble, predictor, index)
            samples.append(predictor)
            if len(samples) == sample_count:
                return struct.pack(f"<{sample_count}h", *samples)
    return struct.pack(f"<{sample_count}h", *samples)


def encode_ima_adpcm(samples: Iterable[int], predictor: int = 0, index: int = 0) -> tuple[bytes, int, int]:
    packed = bytearray()
    pending: int | None = None
    for sample in samples:
        difference = int(sample) - predictor
        nibble = 0
        if difference < 0:
            nibble = 8
            difference = -difference
        step = STEP_TABLE[index]
        change = step >> 3
        if difference >= step:
            nibble |= 4
            difference -= step
            change += step
        if difference >= step >> 1:
            nibble |= 2
            difference -= step >> 1
            change += step >> 1
        if difference >= step >> 2:
            nibble |= 1
            change += step >> 2
        predictor += -change if nibble & 8 else change
        predictor = max(-32768, min(32767, predictor))
        index = max(0, min(88, index + INDEX_TABLE[nibble]))
        if pending is None:
            pending = nibble
        else:
            packed.append(pending | (nibble << 4))
            pending = None
    if pending is not None:
        packed.append(pending)
    return bytes(packed), predictor, index
