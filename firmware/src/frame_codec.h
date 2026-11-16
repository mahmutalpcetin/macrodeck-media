#pragma once
#include <stdint.h>
#include <stddef.h>

inline bool decodeRle565(const uint8_t *input, size_t length, uint8_t *output, size_t capacity) {
  size_t source = 0, destination = 0;
  while (source < length) {
    if (length - source < 2) return false;
    uint16_t token = uint16_t(input[source]) | (uint16_t(input[source + 1]) << 8);
    source += 2;
    size_t count = (token & 0x7FFFu) + 1;
    if (count > (capacity - destination) / 2) return false;
    if (token & 0x8000u) {
      if (length - source < 2) return false;
      uint8_t low = input[source++], high = input[source++];
      while (count--) {output[destination++] = low; output[destination++] = high;}
    } else {
      size_t bytes = count * 2;
      if (length - source < bytes) return false;
      while (bytes--) output[destination++] = input[source++];
    }
  }
  return destination == capacity;
}

inline bool frameCodecSelfTest() {
  uint8_t output[8] = {};
  const uint8_t repeat[] = {0x03, 0x80, 0x34, 0x12};
  if (!decodeRle565(repeat, sizeof(repeat), output, sizeof(output))) return false;
  for (uint8_t i = 0; i < 8; i++) if (output[i] != (i % 2 ? 0x12 : 0x34)) return false;
  const uint8_t literal[] = {0x01, 0x00, 0x00, 0xF8, 0xE0, 0x07};
  if (!decodeRle565(literal, sizeof(literal), output, 4)) return false;
  if (output[0] != 0 || output[1] != 0xF8 || output[2] != 0xE0 || output[3] != 7) return false;
  if (decodeRle565(repeat, sizeof(repeat), output, 2)) return false;
  if (decodeRle565(repeat, 3, output, 8)) return false;
  if (decodeRle565(literal, sizeof(literal), output, 8)) return false;
  return true;
}
