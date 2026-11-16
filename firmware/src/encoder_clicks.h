#pragma once
#include <stdint.h>

// Called with already-debounced press edges and current held state.
// No action is emitted until release; one/two clicks wait for the next click.
class EncoderClicks {
  uint8_t count = 0;
  uint32_t lastRelease = 0, pressedAt = 0;
  bool longFired = false;
  bool armed = false;
public:
  uint8_t update(bool pressEdge, bool held, uint32_t now) {
    if (pressEdge) {armed = true; pressedAt = now; longFired = false;}
    if (armed && held && !longFired && uint32_t(now-pressedAt) >= 700) {
      longFired = true; count = 0; return 4;
    }
    if (armed && !held) {
      if (!longFired && count < 3) ++count;
      lastRelease = now; armed = false;
    }
    if (count && !held && !armed && (count == 3 || uint32_t(now-lastRelease) >= 350)) {
      uint8_t result = count; count = 0; return result;
    }
    return 0;
  }
};

// Target-side regression checks; these never read pins or send any commands.
inline bool encoderClicksSelfTest() {
  EncoderClicks one;
  if (one.update(true,true,100) || one.update(false,false,150) ||
      one.update(false,false,499) || one.update(false,false,500)!=1 ||
      one.update(false,false,900)) return false;
  EncoderClicks two;
  if (two.update(true,true,0) || two.update(false,false,50) ||
      two.update(true,true,200) || two.update(false,false,250) ||
      two.update(false,false,599) || two.update(false,false,600)!=2) return false;
  EncoderClicks three;
  if (three.update(true,true,0) || three.update(false,false,50) ||
      three.update(true,true,150) || three.update(false,false,200) ||
      three.update(true,true,300) || three.update(false,false,350)!=3) return false;
  EncoderClicks held;
  if (held.update(true,true,0) || held.update(false,true,699) || held.update(false,true,700)!=4 ||
      held.update(false,true,5000) ||
      held.update(false,false,5100) || held.update(false,false,5450)) return false;
  EncoderClicks wrap;
  if (wrap.update(true,true,0xFFFFFF00u) || wrap.update(false,false,0xFFFFFFF0u) ||
      wrap.update(false,false,0x14Du) || wrap.update(false,false,0x14Eu)!=1) return false;
  return true;
}
