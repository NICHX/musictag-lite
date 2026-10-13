"""社区源所需的密码学原语。

- AES-128-ECB：网易云 eapi 加解密（密钥固定 ``e82ckenh8dichen8``）——直接使用
  **pycryptodome**，不自实现。
- QRC 私有 DES / 3DES：QQ 音乐逐字歌词（QRC）专用。注意这是**非标准 DES**
  （S 盒位序被打乱、置换用位运算展开），标准 DES/3DES 库无法解密，因此只能保留
  自实现。结构参考 music-lib / songloft-plugin-karaoke-lyric（Apache-2.0）所描述的
  QRC 私有算法，此处为独立重写，仅用于互操作。
"""

from __future__ import annotations

import zlib

from Crypto.Cipher import AES

# --------------------------------------------------------------------------- #
# AES-128 ECB + PKCS7（pycryptodome）
# --------------------------------------------------------------------------- #


def aes_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    """AES-128-ECB + PKCS7 填充。"""
    pad = 16 - len(data) % 16
    return AES.new(key, AES.MODE_ECB).encrypt(data + bytes([pad]) * pad)


def aes_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    """AES-128-ECB 解密并去除 PKCS7 填充。"""
    if not data or len(data) % 16:
        raise ValueError("密文长度非法")
    out = AES.new(key, AES.MODE_ECB).decrypt(data)
    pad = out[-1]
    if 1 <= pad <= 16:
        out = out[:-pad]
    return out


# --------------------------------------------------------------------------- #
# QRC 私有 DES / 3DES（QQ 音乐逐字歌词；标准库无法解，故为独立实现）
# --------------------------------------------------------------------------- #

# prettier-ignore
_QRC_SBOX = [
    [14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7, 0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8, 4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0, 15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13],
    [15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10, 3, 13, 4, 7, 15, 2, 8, 15, 12, 0, 1, 10, 6, 9, 11, 5, 0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15, 13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9],
    [10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8, 13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1, 13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7, 1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12],
    [7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15, 13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9, 10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4, 3, 15, 0, 6, 10, 10, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14],
    [2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9, 14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6, 4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14, 11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3],
    [12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11, 10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8, 9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6, 4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13],
    [4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1, 13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6, 1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2, 6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12],
    [13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7, 1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2, 7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8, 2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11],
]

_QRC_ENCRYPT = 1
_QRC_DECRYPT = 0
_QRC_KEY = b"!@#)(*$%123ZXC!@!@#)(NHL"

_KEY_RND_SHIFT = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]
_KEY_PERM_C = [56, 48, 40, 32, 24, 16, 8, 0, 57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59, 51, 43, 35]
_KEY_PERM_D = [62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45, 37, 29, 21, 13, 5, 60, 52, 44, 36, 28, 20, 12, 4, 27, 19, 11, 3]
_KEY_COMPRESSION = [13, 16, 10, 23, 0, 4, 2, 27, 14, 5, 20, 9, 22, 18, 11, 3, 25, 7, 15, 6, 26, 19, 12, 1, 40, 51, 30, 36, 46, 54, 29, 39, 50, 44, 32, 47, 43, 48, 38, 55, 33, 52, 45, 41, 49, 35, 28, 31]


def _qrc_bit_num(data: bytes, index: int, shift: int) -> int:
    pos = (index // 32) * 4 + 3 - (index % 32) // 8
    return ((data[pos] >> (7 - index % 8)) & 1) << shift


def _qrc_bit_num_intr(value: int, index: int, shift: int) -> int:
    return ((value >> (31 - index)) & 1) << shift


def _qrc_bit_num_intl(value: int, index: int, shift: int) -> int:
    return (((value << index) & 0xFFFFFFFF) & 0x80000000) >> shift


def _qrc_sbox_bit(value: int) -> int:
    return (value & 32) | ((value & 31) >> 1) | ((value & 1) << 4)


def _qrc_initial_permutation(data: bytes) -> tuple[int, int]:
    s0 = 0
    for index, shift in (
        (57, 31), (49, 30), (41, 29), (33, 28), (25, 27), (17, 26), (9, 25), (1, 24),
        (59, 23), (51, 22), (43, 21), (35, 20), (27, 19), (19, 18), (11, 17), (3, 16),
        (61, 15), (53, 14), (45, 13), (37, 12), (29, 11), (21, 10), (13, 9), (5, 8),
        (63, 7), (55, 6), (47, 5), (39, 4), (31, 3), (23, 2), (15, 1), (7, 0),
    ):
        s0 |= _qrc_bit_num(data, index, shift)
    s1 = 0
    for index, shift in (
        (56, 31), (48, 30), (40, 29), (32, 28), (24, 27), (16, 26), (8, 25), (0, 24),
        (58, 23), (50, 22), (42, 21), (34, 20), (26, 19), (18, 18), (10, 17), (2, 16),
        (60, 15), (52, 14), (44, 13), (36, 12), (28, 11), (20, 10), (12, 9), (4, 8),
        (62, 7), (54, 6), (46, 5), (38, 4), (30, 3), (22, 2), (14, 1), (6, 0),
    ):
        s1 |= _qrc_bit_num(data, index, shift)
    return s0, s1


def _qrc_inverse_permutation(s0: int, s1: int) -> bytes:
    groups = [
        (s1, 7, s0, 7), (s1, 6, s0, 6), (s1, 5, s0, 5), (s1, 4, s0, 4),
        (s1, 3, s0, 3), (s1, 2, s0, 2), (s1, 1, s0, 1), (s1, 0, s0, 0),
    ]
    order = [3, 2, 1, 0, 7, 6, 5, 4]
    out = bytearray(8)
    for idx, (a1, a2, b1, b2) in enumerate(groups):
        byte = 0
        for step in range(4):
            byte |= _qrc_bit_num_intr(a1, a2 + step * 8, 7 - step * 2)
            byte |= _qrc_bit_num_intr(b1, b2 + step * 8, 6 - step * 2)
        out[order[idx]] = byte & 0xFF
    return bytes(out)


def _qrc_feistel(state: int, key: bytes) -> int:
    t1 = (
        _qrc_bit_num_intl(state, 31, 0)
        | ((state & 0xF0000000) >> 1)
        | _qrc_bit_num_intl(state, 4, 5)
        | _qrc_bit_num_intl(state, 3, 6)
        | ((state & 0x0F000000) >> 3)
        | _qrc_bit_num_intl(state, 8, 11)
        | _qrc_bit_num_intl(state, 7, 12)
        | ((state & 0x00F00000) >> 5)
        | _qrc_bit_num_intl(state, 12, 17)
        | _qrc_bit_num_intl(state, 11, 18)
        | ((state & 0x000F0000) >> 7)
        | _qrc_bit_num_intl(state, 16, 23)
    ) & 0xFFFFFFFF
    t2 = (
        _qrc_bit_num_intl(state, 15, 0)
        | (((state & 0x0000F000) << 15) & 0xFFFFFFFF)
        | _qrc_bit_num_intl(state, 20, 5)
        | _qrc_bit_num_intl(state, 19, 6)
        | (((state & 0x00000F00) << 13) & 0xFFFFFFFF)
        | _qrc_bit_num_intl(state, 24, 11)
        | _qrc_bit_num_intl(state, 23, 12)
        | (((state & 0x000000F0) << 11) & 0xFFFFFFFF)
        | _qrc_bit_num_intl(state, 28, 17)
        | _qrc_bit_num_intl(state, 27, 18)
        | (((state & 0x0000000F) << 9) & 0xFFFFFFFF)
        | _qrc_bit_num_intl(state, 0, 23)
    ) & 0xFFFFFFFF
    lrg = bytearray(6)
    lrg[0] = (t1 >> 24) & 0xFF
    lrg[1] = (t1 >> 16) & 0xFF
    lrg[2] = (t1 >> 8) & 0xFF
    lrg[3] = (t2 >> 24) & 0xFF
    lrg[4] = (t2 >> 16) & 0xFF
    lrg[5] = (t2 >> 8) & 0xFF
    for i in range(6):
        lrg[i] ^= key[i]
    s = (
        (_QRC_SBOX[0][_qrc_sbox_bit(lrg[0] >> 2)] << 28)
        | (_QRC_SBOX[1][_qrc_sbox_bit((((lrg[0] & 0x03) << 4) | (lrg[1] >> 4)) & 0xFF)] << 24)
        | (_QRC_SBOX[2][_qrc_sbox_bit((((lrg[1] & 0x0F) << 2) | (lrg[2] >> 6)) & 0xFF)] << 20)
        | (_QRC_SBOX[3][_qrc_sbox_bit(lrg[2] & 0x3F)] << 16)
        | (_QRC_SBOX[4][_qrc_sbox_bit(lrg[3] >> 2)] << 12)
        | (_QRC_SBOX[5][_qrc_sbox_bit((((lrg[3] & 0x03) << 4) | (lrg[4] >> 4)) & 0xFF)] << 8)
        | (_QRC_SBOX[6][_qrc_sbox_bit((((lrg[4] & 0x0F) << 2) | (lrg[5] >> 6)) & 0xFF)] << 4)
        | _QRC_SBOX[7][_qrc_sbox_bit(lrg[5] & 0x3F)]
    ) & 0xFFFFFFFF
    result = 0
    for index, shift in (
        (15, 0), (6, 1), (19, 2), (20, 3), (28, 4), (11, 5), (27, 6), (16, 7),
        (0, 8), (14, 9), (22, 10), (25, 11), (4, 12), (17, 13), (30, 14), (9, 15),
        (1, 16), (7, 17), (23, 18), (13, 19), (31, 20), (26, 21), (2, 22), (8, 23),
        (18, 24), (12, 25), (29, 26), (5, 27), (21, 28), (10, 29), (3, 30), (24, 31),
    ):
        result |= _qrc_bit_num_intl(s, index, shift)
    return result & 0xFFFFFFFF


def _qrc_des_crypt(data: bytes, key: list[bytes]) -> bytes:
    s0, s1 = _qrc_initial_permutation(data)
    for i in range(15):
        prev = s1
        s1 = (_qrc_feistel(s1, key[i]) ^ s0) & 0xFFFFFFFF
        s0 = prev
    s0 = (_qrc_feistel(s1, key[15]) ^ s0) & 0xFFFFFFFF
    return _qrc_inverse_permutation(s0, s1)


def _qrc_key_schedule(key: bytes, mode: int) -> list[bytes]:
    schedule = [bytearray(6) for _ in range(16)]
    c = 0
    d = 0
    for i in range(28):
        c = (c + _qrc_bit_num(key, _KEY_PERM_C[i], 31 - i)) & 0xFFFFFFFF
        d = (d + _qrc_bit_num(key, _KEY_PERM_D[i], 31 - i)) & 0xFFFFFFFF
    for i in range(16):
        shift = _KEY_RND_SHIFT[i]
        c = ((((c << shift) & 0xFFFFFFFF) | (c >> (28 - shift))) & 0xFFFFFFF0) & 0xFFFFFFFF
        d = ((((d << shift) & 0xFFFFFFFF) | (d >> (28 - shift))) & 0xFFFFFFF0) & 0xFFFFFFFF
        target = schedule[15 - i if mode == _QRC_DECRYPT else i]
        for j in range(24):
            target[j // 8] |= _qrc_bit_num_intr(c, _KEY_COMPRESSION[j], 7 - (j % 8)) & 0xFF
        for j in range(24, 48):
            target[j // 8] |= _qrc_bit_num_intr(d, _KEY_COMPRESSION[j] - 27, 7 - (j % 8)) & 0xFF
    return [bytes(item) for item in schedule]


_QRC_TRIPLE_KEYS = [
    _qrc_key_schedule(_QRC_KEY[16:], _QRC_DECRYPT),
    _qrc_key_schedule(_QRC_KEY[8:16], _QRC_ENCRYPT),
    _qrc_key_schedule(_QRC_KEY[0:8], _QRC_DECRYPT),
]


def decrypt_qrc(encrypted_hex: str) -> str:
    """解密 QQ 音乐 QRC 密文（hex）并解压为逐字歌词文本。"""
    hex_text = encrypted_hex.strip()
    total = len(hex_text) // 2
    if total < 8:
        return ""
    raw = bytes.fromhex(hex_text[: total * 2])
    aligned = total - (total % 8)
    out = bytearray(aligned)
    for i in range(0, aligned, 8):
        block = raw[i : i + 8]
        for keys in _QRC_TRIPLE_KEYS:
            block = _qrc_des_crypt(block, keys)
        out[i : i + 8] = block
    try:
        plain = zlib.decompress(bytes(out))
    except zlib.error:
        return ""
    return plain.decode("utf-8", errors="replace")
