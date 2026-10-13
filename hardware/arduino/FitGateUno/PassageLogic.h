#pragma once

// Shared by the firmware and native regression tests; no Arduino dependencies.
struct DistanceFilter {
  bool near = false;
  unsigned char nearSamples = 0, farSamples = 0;
  void update(bool valid, unsigned int cm) {
    if (!valid) { near = false; nearSamples = farSamples = 0; return; }
    if (cm <= 20) {
      farSamples = 0;
      if (nearSamples < 2) ++nearSamples;
      if (nearSamples >= 2) near = true;
    } else {
      nearSamples = 0;
      if (farSamples < 2) ++farSamples;
      if (farSamples >= 2) near = false;
    }
  }
  bool detected() const { return near && nearSamples >= 2; }
  bool empty() const { return !near && farSamples >= 2; }
};

struct SingleSensorPassage {
  enum Stage { WAIT_TRIGGER, COMPLETE, ERROR };
  Stage stage = WAIT_TRIGGER;
  bool active = false, blocked[2] = {false, false};
  unsigned char triggered = 0;
  unsigned long started = 0, timeout = 8000;
  void release(bool outsideEmpty, bool insideEmpty) {
    if (outsideEmpty) blocked[0] = false;
    if (insideEmpty) blocked[1] = false;
  }
  bool canBegin() const { return !blocked[0] && !blocked[1]; }
  void begin(unsigned long now, unsigned long duration) {
    stage = WAIT_TRIGGER; started = now; timeout = duration; active = true;
  }
  void tick(bool healthy, bool outside, bool inside, unsigned long now) {
    if (!active || stage != WAIT_TRIGGER) return;
    if (!healthy || now - started >= timeout || !canBegin()) { stage = ERROR; return; }
    if (!outside && !inside) return;
    triggered = outside ? 0 : 1;
    // Latch every occupied sensor; neither may carry detection into another transaction.
    blocked[0] = outside; blocked[1] = inside;
    stage = COMPLETE;
  }
};

struct PassageSequence {
  enum Stage { WAIT_FIRST, WAIT_SECOND, WAIT_CLEAR, COMPLETE, ERROR };
  Stage stage = WAIT_FIRST;
  char expected = 'E', detected = 'N';
  unsigned long started = 0, timeout = 8000, clearSince = 0;
  bool active = false, clearing = false;
  void begin(char way, unsigned long now, unsigned long duration) {
    stage = WAIT_FIRST; expected = way; detected = 'N';
    started = now; timeout = duration; active = true; clearing = false;
  }
  void tick(bool healthy, bool outside, bool inside, bool empty, unsigned long now) {
    if (!active || stage == COMPLETE || stage == ERROR) return;
    if (!healthy || now - started >= timeout) { stage = ERROR; return; }
    if (stage == WAIT_FIRST) {
      if (outside && inside) { stage = ERROR; return; }
      if (!outside && !inside) return;
      detected = outside ? 'E' : 'X';
      if (detected != expected) { stage = ERROR; return; }
      stage = WAIT_SECOND;
    } else if (stage == WAIT_SECOND) {
      if (detected == 'E' ? inside : outside) stage = WAIT_CLEAR;
    }
    if (stage == WAIT_CLEAR) {
      if (!empty) { clearing = false; return; }
      if (!clearing) { clearSince = now; clearing = true; }
      if (now - clearSince >= 250) stage = COMPLETE;
    }
  }
};
