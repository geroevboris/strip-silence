"""Zero-dependency, sample-preserving WAV inspection & slicing (prototype)."""
import math
import os
import struct

SUPPORTED_PCM = (1, 3)  # integer PCM and IEEE float


class WavFile:
    def __init__(self, path):
        self.path = os.path.abspath(os.path.expanduser(path))
        if os.path.splitext(self.path)[1].lower() != '.wav':
            raise ValueError('v0.1 supports uncompressed WAV files only (not AIFF, MP3 or FLAC)')
        with open(self.path, 'rb') as f:
            header = f.read(12)
            if len(header) != 12 or header[:4] != b'RIFF' or header[8:] != b'WAVE':
                raise ValueError('Expected standard RIFF/WAVE file')
            fmt = None
            data_offset = None
            data_bytes = None
            file_size = os.fstat(f.fileno()).st_size
            while f.tell() + 8 <= file_size:
                ch = f.read(8)
                if len(ch) != 8:
                    break
                name, sz = struct.unpack('<4sI', ch)
                pos = f.tell()
                if name == b'fmt ':
                    fmt = f.read(sz)
                elif name == b'data':
                    data_offset = pos
                    data_bytes = sz
                f.seek(pos + sz + (sz % 2))
        if fmt is None or data_offset is None or data_bytes is None:
            raise ValueError('WAV is missing fmt or data chunk')
        if len(fmt) < 16:
            raise ValueError('Truncated WAV format chunk')
        tag, channels, rate, byte_rate, align, bits = struct.unpack_from('<HHIIHH', fmt)
        if tag == 0xfffe and len(fmt) >= 40:
            tag = struct.unpack_from('<H', fmt, 24)[0]  # subformat GUID begins with a uint32 code
        if tag not in SUPPORTED_PCM or channels < 1 or channels > 32:
            raise ValueError('Unsupported WAV encoding or channels')
        if bits not in (8, 16, 24, 32, 64) or bits == 64 and tag != 3:
            raise ValueError('Unsupported WAV sample depth')
        if tag == 3 and bits not in (32, 64):
            raise ValueError('Only float32/float64 are supported')
        if align != channels * (bits // 8) or rate < 8000 or rate > 384000:
            raise ValueError('Unsupported WAV format alignment or rate')
        if data_offset + data_bytes > file_size:
            raise ValueError('WAV data chunk exceeds file length')
        self.fmt = fmt
        self.tag, self.channels, self.rate = tag, channels, rate
        self.align, self.bits = align, bits
        self.data_offset = data_offset
        self.frames = data_bytes // align

    def _max_norm(self, pcm):
        width = self.bits // 8
        if not pcm:
            return 0.0
        frame_bytes = self.align
        if self.tag == 3:
            unpack = struct.Struct('<f' if self.bits == 32 else '<d').unpack_from
            peak = 0.0
            for i in range(0, len(pcm) - frame_bytes + 1, frame_bytes * 2):
                for ch in range(self.channels):
                    value = abs(unpack(pcm, i + ch * width)[0])
                    if math.isfinite(value) and value > peak:
                        peak = value
            return peak
        peak = 0
        scale = float(1 << (self.bits - 1))
        # Every second frame keeps scanning reasonably responsive on long multitracks.
        for i in range(0, len(pcm) - frame_bytes + 1, frame_bytes * 2):
            for ch in range(self.channels):
                offset = i + ch * width
                if self.bits == 8:
                    v = abs(pcm[offset] - 128)
                else:
                    v = abs(int.from_bytes(pcm[offset:offset + width], 'little', signed=True))
                if v > peak:
                    peak = v
        return peak / scale

    def detect(self, start_seconds, duration_seconds, threshold_db=-45.0, min_silence_ms=150, padding_ms=30):
        if not (-90 <= threshold_db <= -1):
            raise ValueError('Threshold must be -90 to -1 dBFS')
        if not (30 <= min_silence_ms <= 5000) or not (0 <= padding_ms <= 1000):
            raise ValueError('Invalid silence/padding parameters')
        start = round(start_seconds * self.rate)
        end = round((start_seconds + duration_seconds) * self.rate)
        if end > self.frames and end - self.frames <= 2:
            end = self.frames  # tolerate sub-frame rounding from beat conversion
        if start < 0 or end <= start or end > self.frames:
            raise ValueError('Clip file range is outside WAV sample content')
        hop = max(1, round(self.rate * 0.01))  # ~10 ms blocks
        threshold = 10 ** (threshold_db / 20)
        activity = []
        with open(self.path, 'rb') as f:
            f.seek(self.data_offset + start * self.align)
            pos = start
            while pos < end:
                frames = min(hop, end - pos)
                activity.append(self._max_norm(f.read(frames * self.align)) >= threshold)
                pos += frames
        if not any(activity):
            return []
        # Separate active islands only if the gap is genuinely long enough.
        active_ranges = []
        first = last = None
        for k, active in enumerate(activity):
            if active:
                if first is None:
                    first = k
                last = k + 1
            elif first is not None and (k - last + 1) * hop * 1000 / self.rate >= min_silence_ms:
                active_ranges.append((first, last))
                first = last = None
        if first is not None:
            active_ranges.append((first, last))
        pad_frames = round(self.rate * padding_ms / 1000)
        padded = []
        for a, b in active_ranges:
            left = max(start, start + a * hop - pad_frames)
            right = min(end, start + b * hop + pad_frames)
            if padded and left <= padded[-1][1]:
                padded[-1] = (padded[-1][0], max(padded[-1][1], right))
            else:
                padded.append((left, right))
        return padded

    def write_slice(self, left_frame, right_frame, output_path):
        if not (0 <= left_frame < right_frame <= self.frames):
            raise ValueError('Invalid frame range')
        nbytes = (right_frame - left_frame) * self.align
        if nbytes > 0xffffffff - 100:
            raise ValueError('Fragment exceeds classic WAV 4GB limit')
        chunks = [(b'fmt ', self.fmt)]
        if self.tag == 3:
            chunks.append((b'fact', struct.pack('<I', right_frame - left_frame)))
        riff_size = 4 + sum(8 + len(data) + len(data) % 2 for _name, data in chunks) + 8 + nbytes + nbytes % 2
        with open(output_path, 'wb') as out, open(self.path, 'rb') as src:
            out.write(b'RIFF' + struct.pack('<I', riff_size) + b'WAVE')
            for name, data in chunks:
                out.write(name + struct.pack('<I', len(data)) + data)
                if len(data) % 2:
                    out.write(b'\0')
            out.write(b'data' + struct.pack('<I', nbytes))
            src.seek(self.data_offset + left_frame * self.align)
            remaining = nbytes
            while remaining:
                b = src.read(min(1024 * 1024, remaining))
                if not b:
                    raise ValueError('Source WAV truncated while copying')
                out.write(b)
                remaining -= len(b)
            if nbytes % 2:
                out.write(b'\0')
