"""合成最小可用音频 fixture（纯 Python 手写字节，无需 ffmpeg / 编码器）。

- ``make_flac``：手写 STREAMINFO 元数据块 → 覆盖 Vorbis Comment 容器
- ``make_wav`` ：手写 RIFF 头 + 静音 PCM → 覆盖 ID3 容器
"""

from __future__ import annotations

import struct
from pathlib import Path

# 一张极小的合法 JPEG（仅头部 + EOI），用于封面读写测试
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\xff\xd9"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def make_flac(
    path: str | Path,
    *,
    sample_rate: int = 44100,
    channels: int = 2,
    bits_per_sample: int = 16,
    samples: int = 44100,
) -> Path:
    """生成一个仅含 STREAMINFO 的合法 FLAC 文件。"""
    streaminfo = bytearray()
    streaminfo += struct.pack(">HH", 4096, 4096)  # min/max block size
    streaminfo += (0).to_bytes(3, "big")  # min frame size
    streaminfo += (0).to_bytes(3, "big")  # max frame size
    packed = (sample_rate << 44) | ((channels - 1) << 41) | ((bits_per_sample - 1) << 36) | samples
    streaminfo += packed.to_bytes(8, "big")
    streaminfo += bytes(16)  # md5
    data = b"fLaC" + bytes([0x80, 0x00, 0x00, 0x22]) + bytes(streaminfo)
    p = Path(path)
    p.write_bytes(data)
    return p


def make_wav(path: str | Path, *, sample_rate: int = 8000, samples: int = 800) -> Path:
    """生成一个静音 PCM WAV 文件（16bit / 单声道）。"""
    pcm = b"\x00\x00" * samples
    p = Path(path)
    with p.open("wb") as fp:
        fp.write(b"RIFF")
        fp.write(struct.pack("<I", 36 + len(pcm)))
        fp.write(b"WAVE")
        fp.write(b"fmt ")
        fp.write(struct.pack("<I", 16))
        fp.write(struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16))
        fp.write(b"data")
        fp.write(struct.pack("<I", len(pcm)))
        fp.write(pcm)
    return p
