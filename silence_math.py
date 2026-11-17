"""Clear Silence: a single conservative-to-aggressive control, and reversible regions.

The source WAV is never edited. Regions reference sample positions in that WAV.
"""
from __future__ import annotations
import math


def settings_for_strength(strength):
    x = float(strength)
    if not math.isfinite(x) or not 0 <= x <= 100:
        raise ValueError('Чувствительность должна быть от 0 до 100')
    t = x / 100.0
    return {
        'threshold': round(-62 + 37 * t, 2),
        'min_silence_ms': round(320 - 230 * t),
        'padding_ms': round(75 - 60 * t),
    }


def regions_with_muted_gaps(kept, start_frame, end_frame, min_region_frames=0):
    """Return source-frame regions covering the original clip without holes/overlap.

    Each tuple is (start_frame, end_frame, muted), with gaps muted.
    All ranges are bounded by the original clip, so a user can reveal them
    later by unmuting or expanding the edge of an audio clip in Live.
    """
    start_frame, end_frame = int(start_frame), int(end_frame)
    if start_frame < 0 or end_frame <= start_frame:
        raise ValueError('Некорректные границы аудиоклипа')
    raw = []
    current = start_frame
    for a, b in kept:
        a, b = int(a), int(b)
        if a < current or b <= a or b > end_frame:
            raise ValueError('Неверные или пересекающиеся участки звука')
        if a > current:
            raw.append((current, a, True))
        raw.append((a, b, False))
        current = b
    if current < end_frame:
        raw.append((current, end_frame, True))
    if not raw:
        raw = [(start_frame, end_frame, True)]

    # Ableton may reject pathological sub-millisecond clips at the edges.
    # Always favor keeping sound when absorbing very short intervals.
    min_region_frames = max(0, int(min_region_frames))
    if min_region_frames:
        while len(raw) > 1:
            idx = next((i for i,(a,b,_) in enumerate(raw) if b-a < min_region_frames), None)
            if idx is None:
                break
            if idx == 0:
                a,b,muted = raw[0]
                c,d,muted_right=raw[1]
                raw[:2]=[(a,d,muted and muted_right)]
            else:
                a,b,muted_left=raw[idx-1]
                c,d,muted=raw[idx]
                raw[idx-1:idx+1]=[(a,d,muted_left and muted)]
    if raw[0][0] != start_frame or raw[-1][1] != end_frame:
        raise AssertionError('regions must cover source')
    if any(raw[i][1] != raw[i+1][0] for i in range(len(raw)-1)):
        raise AssertionError('regions are not contiguous')
    return raw
