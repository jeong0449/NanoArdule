// Ardule Input handling module - auto-split from main sketch
//
// Contains:
//  - Button click debounce helper
//  - Long-press state checker
//  - Button feedback LED helper
//  - Rotary encoder ISR (handleEncoderAInterrupt)
//
// Relies on global state declared in the main sketch:
//  - LongPressState, lpEnc, lpMetro
//  - latchEncBtn, latchPlay, latchStop, latchInternal, latchMetro, latchBpmUp, latchBpmDn
//  - g_encDelta
//  - LED_A0, BTN_LED_MS, btnLedOffAt
//  - ENC_A_PIN, ENC_B_PIN
//

bool readButtonClick(uint8_t pin, bool &latch) {
  bool pressed = (digitalRead(pin) == LOW);
  static uint32_t lastMs[16] = {0};
  uint8_t idx = pin & 0x0F;
  uint32_t now = millis();
  bool fired = false;

  if(pressed && !latch && (now - lastMs[idx] > 30)) {
    latch = true;
    fired = true;
    lastMs[idx] = now;
  }
  if(!pressed) latch = false;
  return fired;
}

// Click-on-release helper (press duration must be < maxMs).
// Useful for buttons that also have long-press actions (prevents firing on long-press).
bool readButtonReleaseClick(uint8_t pin, bool &latch, uint32_t &downMs, uint32_t nowMs, uint32_t maxMs) {
  bool pressed = (digitalRead(pin) == LOW);
  bool fired = false;

  if(pressed && !latch) {
    latch = true;
    downMs = nowMs;
  } else if(!pressed && latch) {
    // released
    latch = false;
    if(nowMs - downMs < maxMs) fired = true;
  }
  return fired;
}


void indicateButtonFeedback() {
  digitalWrite(LED_A0, HIGH);
  btnLedOffAt = millis() + BTN_LED_MS;
}

bool checkLongPressState(uint8_t pin, LongPressState &st, uint32_t nowMs) {
  bool down = (digitalRead(pin) == LOW);
  if (down && !st.wasDown) {
    st.wasDown = true;
    st.downMs  = nowMs;
  } else if (!down && st.wasDown) {
    st.wasDown = false;
  }
  if (down && st.wasDown && (nowMs - st.downMs > LONG_PRESS_MS)) {
    st.wasDown = false;
    return true;
  }
  return false;
}

//////////////////// 인코더 ISR ////////////////////
void handleEncoderAInterrupt() {
  static uint8_t lastA = 0;
  uint8_t a = digitalRead(ENC_A_PIN);
  uint8_t b = digitalRead(ENC_B_PIN);
  if(a != lastA) {
    if(a != b) g_encDelta++;
    else       g_encDelta--;
    lastA = a;
  }
}
