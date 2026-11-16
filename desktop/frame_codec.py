"""Bounded, lossless RGB565 packet encoding shared with the firmware.

Each little-endian 16-bit token stores count-1 (1..32768 pixels).
Bit 15 selects a repeated pixel; otherwise count literal pixels follow.
No image dimensions, allocation requests or executable data are embedded.
"""
from array import array
import struct
import sys

MAX_PIXELS = 320 * 240


def encode_rle565(raw):
    if not raw or len(raw) % 2 or len(raw) > MAX_PIXELS * 2:
        raise ValueError("Invalid RGB565 payload")
    pixels = array("H")
    pixels.frombytes(raw)
    if sys.byteorder != "little":
        pixels.byteswap()
    result = bytearray()
    start = index = 0
    size = len(pixels)

    def literals(left, right):
        while left < right:
            end = min(right, left + 32768)
            result.extend(struct.pack("<H", end - left - 1))
            result.extend(raw[left * 2:end * 2])
            left = end

    while index < size:
        end = index + 1
        while end < size and end - index < 32768 and pixels[end] == pixels[index]:
            end += 1
        if end - index >= 3:
            literals(start, index)
            result.extend(struct.pack("<HH", 0x8000 | (end - index - 1), pixels[index]))
            index = end
            start = index
        else:
            index = end
    literals(start, size)
    return bytes(result)


def decode_rle565(encoded, expected_bytes):
    """Reference decoder used by tests and hardware CRC diagnostics."""
    if expected_bytes <= 0 or expected_bytes % 2 or expected_bytes > MAX_PIXELS * 2:
        raise ValueError("Invalid decoded size")
    output = bytearray()
    cursor = 0
    while cursor < len(encoded):
        if len(encoded) - cursor < 2:
            raise ValueError("Truncated token")
        token = struct.unpack_from("<H", encoded, cursor)[0]
        cursor += 2
        count = (token & 0x7fff) + 1
        if len(output) + count * 2 > expected_bytes:
            raise ValueError("Decoded image exceeds bounds")
        length = 2 if token & 0x8000 else count * 2
        if len(encoded) - cursor < length:
            raise ValueError("Truncated pixel packet")
        data = encoded[cursor:cursor + length]
        output.extend(data * count if token & 0x8000 else data)
        cursor += length
    if len(output) != expected_bytes:
        raise ValueError("Decoded image is incomplete")
    return bytes(output)


def encode_frame(raw, supported):
    if supported and len(raw) >= 256:
        packed = encode_rle565(raw)
        # Use raw data when packet overhead would outweigh the savings.
        if len(packed) + 64 < len(raw):
            return packed, "rle565"
    return raw, "raw"
