#include "../../hardware/arduino/FitGateUno/PassageLogic.h"
#include <cassert>
#include <iostream>

int main() {
  DistanceFilter f;
  f.update(true,20); assert(!f.detected());
  f.update(true,20); assert(f.detected() && !f.empty());
  f.update(true,21); assert(!f.detected() && !f.empty());
  f.update(true,20); assert(!f.detected());
  f.update(true,21); f.update(true,21); assert(f.empty());
  f.update(false,0); assert(!f.empty() && !f.detected());
  for (char direction : {'E','X'}) {
    PassageSequence s; s.begin(direction,0,8000);
    s.tick(true,false,false,true,1); assert(s.stage==s.WAIT_FIRST);
    bool entry=direction=='E';
    s.tick(true,entry,!entry,false,120); assert(s.stage==s.WAIT_SECOND);
    s.tick(true,false,false,true,500); assert(s.stage==s.WAIT_SECOND);
    s.tick(true,!entry,entry,false,600); assert(s.stage==s.WAIT_CLEAR);
    s.tick(true,false,false,true,700); assert(s.stage==s.WAIT_CLEAR);
    s.tick(true,true,false,false,900); assert(s.stage==s.WAIT_CLEAR);
    s.tick(true,false,false,true,1000); s.tick(true,false,false,true,1249);
    assert(s.stage==s.WAIT_CLEAR);
    s.tick(true,false,false,true,1250); assert(s.stage==s.COMPLETE);
  }
  PassageSequence s;
  s.tick(true,true,false,false,120);
  s.tick(true,false,true,false,500);
  s.tick(true,false,false,true,1000); assert(s.stage==s.WAIT_FIRST && !s.active);
  s.begin('E',0,8000); s.tick(true,false,true,false,120); assert(s.stage==s.ERROR);
  s.begin('E',0,8000); s.tick(true,true,true,false,120); assert(s.stage==s.ERROR);
  s.begin('E',0,8000); s.tick(true,true,false,false,120);
  s.tick(true,false,false,true,8000); assert(s.stage==s.ERROR);
  s.begin('X',0,8000); s.tick(false,false,false,false,120); assert(s.stage==s.ERROR);
  s.begin('E',0xfffffff0UL,8000);
  // Native unsigned long width may differ from AVR; subtraction remains unsigned.
  s.tick(true,true,false,false,0xfffffff1UL); assert(s.stage==s.WAIT_SECOND);
  SingleSensorPassage p;
  p.tick(true,true,false,1); assert(!p.active && p.stage==p.WAIT_TRIGGER);
  for (bool outside : {true,false}) {
    p.begin(0,8000); p.tick(true,outside,!outside,120);
    assert(p.stage==p.COMPLETE && p.triggered==(outside ? 0 : 1));
    p.tick(true,true,true,300); assert(p.stage==p.COMPLETE);
    assert(!p.canBegin());
    p.release(!outside,outside); assert(!p.canBegin());
    p.release(true,true); assert(p.canBegin());
  }
  p.begin(0,8000); p.tick(true,true,true,120); assert(p.stage==p.COMPLETE);
  p.release(true,false); assert(!p.canBegin()); p.release(false,true); assert(p.canBegin());
  p.begin(0,8000); p.tick(true,false,false,7999); assert(p.stage==p.WAIT_TRIGGER);
  p.tick(true,true,false,8000); assert(p.stage==p.ERROR);
  p.begin(0,8000); p.tick(false,true,false,120); assert(p.stage==p.ERROR);
  DistanceFilter a,b;
  p.begin(0,8000); a.update(true,20); b.update(true,80);
  p.tick(true,a.detected(),b.detected(),120); assert(p.stage==p.WAIT_TRIGGER);
  a.update(true,20); b.update(true,80);
  p.tick(true,a.detected(),b.detected(),240); assert(p.stage==p.COMPLETE);
  std::cout << "PASS: legacy sequence unchanged; prototype either/both sensor, 20/21 boundary, two-sample debounce, no card/no active trigger, single event latch, per-sensor release, timeout, invalid measurement\n";
}
