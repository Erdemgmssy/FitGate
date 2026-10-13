#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <hd44780.h>
#include <hd44780ioClass/hd44780_I2Cexp.h>
#include <Servo.h>
#include "PassageLogic.h"

#ifndef FITGATE_SINGLE_SENSOR_PROTOTYPE
#define FITGATE_SINGLE_SENSOR_PROTOTYPE 0
#endif
#if FITGATE_SINGLE_SENSOR_PROTOTYPE
#define FITGATE_FIRMWARE_VERSION "7"
SingleSensorPassage singlePassage;
#else
#define FITGATE_FIRMWARE_VERSION "6"
#endif

const byte OUT_TRIG = 2, OUT_ECHO = 3, IN_TRIG = 4, IN_ECHO = 5;
const byte SERVO_PIN = 6, BUZZER_PIN = 7, LED_PIN = 8;
const byte RFID_RST = 9, RFID_SS = 10;
const byte CLOSED_ANGLE = 0, OPEN_ANGLE = 90;
MFRC522 reader(RFID_SS, RFID_RST);
hd44780_I2Cexp lcd(0x3F);
Servo gate;

struct Sensor : DistanceFilter {
  bool valid = false;
  unsigned long sampledAt = 0;
  unsigned int cm = 0;
};
Sensor sensors[2];
enum Mode { IDLE, WAIT_SERVER, OPEN, WAIT_ACK, FAILED, DIAGNOSTIC, CLOSING };
Mode mode = IDLE;
bool linked = false, lcdOk = false, opened = false;
bool captureMode = false;
bool attendanceMode = false;
PassageSequence passage;
char diagnosticId[37];
bool diagnosticServo = false;
bool diagnosticOk = false;
unsigned long diagnosticAt = 0, shownAt = 0;
unsigned long lastPing = 0;
unsigned long captureAt = 0;
char input[110];
byte inputSize = 0;
unsigned long sequence = 0, activeScan = 0, requestedAt = 0;
unsigned long allowedAt = 0, validMs = 8000, passedMs = 0;
unsigned long lastSample = 0, lastHealth = 0, lastReady = 0;
unsigned long lastDistance = 0;
unsigned long clearAt = 0, lastPassSend = 0;
byte sampleSide = 0;
char direction = 'E';
unsigned long signalAt = 0;
byte signalPulses = 0;
byte lastUid[10], lastUidSize = 0;
bool cardLatched = false;
unsigned long lastRfidPoll = 0, lastCardSeen = 0;

void show(const char* top, const char* bottom) {
  shownAt = millis();
  Serial.print(F("LCD|")); for (byte i=0;i<16 && top[i];i++) Serial.write(top[i]);
  Serial.print('|'); for (byte i=0;i<16 && bottom[i];i++) Serial.write(bottom[i]); Serial.println();
  if (!lcdOk) return;
  lcd.setCursor(0, 0); lcd.print(F("                "));
  lcd.setCursor(0, 0); for (byte i=0;i<16 && top[i];i++) lcd.write(top[i]);
  lcd.setCursor(0, 1); lcd.print(F("                "));
  lcd.setCursor(0, 1); for (byte i=0;i<16 && bottom[i];i++) lcd.write(bottom[i]);
}

void show(const __FlashStringHelper* top, const __FlashStringHelper* bottom) {
  char first[17], second[17];
  strncpy_P(first, reinterpret_cast<PGM_P>(top), 16); first[16]=0;
  strncpy_P(second, reinterpret_cast<PGM_P>(bottom), 16); second[16]=0;
  show(first, second);
}

void signal(byte count) { signalAt = millis(); signalPulses = count; }
void tickSignal() {
  unsigned long age = millis() - signalAt;
  bool on = signalPulses && age < signalPulses * 400UL && age % 400 < 180;
  digitalWrite(LED_PIN, on); digitalWrite(BUZZER_PIN, on);
  static bool reported = false;
  if (on != reported) { Serial.print(F("IO|")); Serial.print(on ? '1' : '0'); Serial.print('|'); Serial.println(on ? '1' : '0'); reported = on; }
  if (age >= signalPulses * 400UL) signalPulses = 0;
}

bool healthy() {
  return sensors[0].valid && sensors[1].valid &&
    millis() - sensors[0].sampledAt < 500 && millis() - sensors[1].sampledAt < 500;
}
bool clearPath() { return healthy() && sensors[0].empty() && sensors[1].empty(); }
void progress(const __FlashStringHelper* state, char way = 'N') {
  Serial.print(F("PROGRESS|")); Serial.print(activeScan); Serial.print('|');
  Serial.print(state); Serial.print('|'); Serial.println(way);
}

void sampleSensor(byte side) {
  byte trig = side ? IN_TRIG : OUT_TRIG, echo = side ? IN_ECHO : OUT_ECHO;
  digitalWrite(trig, LOW); delayMicroseconds(2);
  digitalWrite(trig, HIGH); delayMicroseconds(10); digitalWrite(trig, LOW);
  unsigned long duration = pulseIn(echo, HIGH, 20000UL);
  Sensor& sensor = sensors[side];
  sensor.sampledAt = millis();
  unsigned int cm = duration / 58;
  sensor.valid = duration && cm >= 2 && cm <= 340;
  sensor.cm = sensor.valid ? cm : 0;
  sensor.update(sensor.valid, cm);
}

void idle() {
  mode = IDLE; clearAt = 0;
  progress(F("idle"));
  show("FITGATE HAZIR", captureMode ? "KART TANIMLAMA" : linked ? "KART OKUTUN" : "BAGLANTI YOK");
}
void fault(const char* reason) {
  Serial.print(F("FAULT|")); Serial.print(activeScan); Serial.print('|'); Serial.println(reason);
  mode = captureMode && !opened ? IDLE : FAILED;
  clearAt = 0; signal(2); show(captureMode ? "Okutma hatasi" : "Gecis durduruldu", reason);
  progress(F("fault"), passage.detected);
}
void sendPass() {
  Serial.print(F("PASS|")); Serial.print(activeScan); Serial.print('|');
  Serial.print(direction); Serial.print('|'); Serial.print(passedMs);
#if FITGATE_SINGLE_SENSOR_PROTOTYPE
  Serial.print('|'); Serial.print(singlePassage.triggered); Serial.print(F("|single_sensor_prototype"));
#endif
  Serial.println();
  lastPassSend = millis();
}

void command() {
  char* op = strtok(input, "|");
  char* idText = strtok(NULL, "|");
  if (!op || !idText) return;
  if (!strcmp(op, "HELLO") && !strcmp(idText, FITGATE_FIRMWARE_VERSION)) { linked = true; lastPing = millis(); if (!opened && mode != WAIT_ACK) idle(); return; }
  if (!strcmp(op, "PING") && !strcmp(idText, FITGATE_FIRMWARE_VERSION)) { lastPing = millis(); return; }
  if (!strcmp(op, "PURPOSE")) {
    attendanceMode = false;
    return;
  }
  if (!strcmp(op,"DIAG")) {
    char* test = strtok(NULL,"|");
    if (!strcmp(idText,diagnosticId)) {
      if (mode != DIAGNOSTIC) { Serial.print(F("DIAGDONE|")); Serial.print(idText); Serial.println(diagnosticOk ? F("|ok|Duplicate ignored") : F("|error|Duplicate ignored")); }
      return;
    }
    if (!linked || mode != IDLE || opened || captureMode || !test || strlen(idText) != 36) {
      Serial.print(F("DIAGDONE|")); Serial.print(idText); Serial.println(F("|error|Busy")); return;
    }
    bool servoTest = !strcmp(test,"servo");
    if ((servoTest && !clearPath()) || (strcmp(test,"servo") && strcmp(test,"lcd") && strcmp(test,"indicators"))) {
      Serial.print(F("DIAGDONE|")); Serial.print(idText); Serial.println(F("|error|Sensor/command")); return;
    }
    strcpy(diagnosticId,idText); diagnosticOk=false; diagnosticServo=servoTest; diagnosticAt=millis(); mode=DIAGNOSTIC;
    if (servoTest) { gate.write(OPEN_ANGLE); opened=true; }
    if (!strcmp(test,"indicators")) signal(3);
    show("DONANIM TESTI",servoTest ? "ALANI BOS TUTUN" : test); return;
  }
  if (!strcmp(op, "CAPTURE")) {
    if (opened || mode == OPEN || mode == WAIT_ACK || mode == WAIT_SERVER || mode == DIAGNOSTIC || mode == CLOSING) { Serial.println(F("MODE|busy")); return; }
    captureMode = !strcmp(idText, "1"); captureAt = millis(); idle();
    Serial.println(captureMode ? F("MODE|capture") : F("MODE|normal")); return;
  }
  unsigned long id = strtoul(idText, NULL, 10);
  if (id != activeScan) return;
  if (!strcmp(op,"RESULT") && (mode == IDLE || mode == WAIT_ACK || mode == CLOSING)) {
    char* message = strtok(NULL,"|");
    if (message) { show(message,"KAYIT TAMAMLANDI"); signal(!strcmp(message,"MESAI BITTI") ? 2 : 1); }
    return;
  }
  if (!strcmp(op, "ACK") && mode == WAIT_ACK) { mode=opened ? CLOSING : IDLE; shownAt=millis(); return; }
  if (mode != WAIT_SERVER) return;
  if (!strcmp(op,"CAPTURED") && captureMode) {
    char* error = strtok(NULL,"|"); mode = IDLE;
    signal(error ? 2 : 1);
    show(error ? "Okutma hatasi" : "Kart okundu",error ? "PC kontrol edin" : "PC den atayin"); return;
  }
  if (captureMode && !strcmp(op,"ALLOW")) return;
  if (!strcmp(op,"ATTENDED") && attendanceMode) {
    char* approved = strtok(NULL,"|"), *message = strtok(NULL,"|");
    bool ok = approved && !strcmp(approved,"1");
    signal(ok ? 1 : 2); show(ok ? "Mesai kaydedildi" : "Mesai reddedildi",message ? message : "PC kontrol edin");
    mode = FAILED; clearAt = millis(); return;
  }
  if (!strcmp(op, "DENY")) {
    char* reason = strtok(NULL, "|");
    signal(2); show("GIRIS REDDEDILDI", reason ? reason : "BAGLANTI YOK"); mode = FAILED; clearAt = millis(); progress(F("fault")); return;
  }
  if (strcmp(op, "ALLOW")) return;
  if (attendanceMode) { fault("Mesai modu"); return; }
  char* way = strtok(NULL, "|"), *duration = strtok(NULL, "|");
  if (!way || (strcmp(way, "E") && strcmp(way, "X")) || !duration) return;
  if (millis() - requestedAt > 4000 || !healthy()) { fault("Sensor / zaman"); return; }
#if FITGATE_SINGLE_SENSOR_PROTOTYPE
  if (!singlePassage.canBegin()) { fault("Sensoru birakin"); return; }
#endif
  direction = way[0];
  validMs = min(8000UL, strtoul(duration, NULL, 10));
  if (validMs < 1000) { fault("Izin gecersiz"); return; }
  char* member = strtok(NULL, "|");
  allowedAt = millis(); clearAt = 0;
#if FITGATE_SINGLE_SENSOR_PROTOTYPE
  singlePassage.begin(allowedAt, validMs);
  for (byte i=0; i<2; ++i) { sensors[i].near=false; sensors[i].nearSamples=0; sensors[i].farSamples=0; }
#else
  passage.begin(direction, allowedAt, validMs);
#endif
  gate.write(OPEN_ANGLE); opened = true; mode = OPEN; signal(1);
  show(direction == 'E' ? "GIRIS ONAYLANDI" : "CIKIS ONAYLANDI", FITGATE_SINGLE_SENSOR_PROTOTYPE ? "TEK SENSOR TEST" : "GECIS BEKLENIYOR");
  progress(F("waiting_first"));
}

void readCommands() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') { input[inputSize] = 0; command(); inputSize = 0; }
    else if (inputSize < sizeof(input) - 1) input[inputSize++] = ch;
    else { inputSize = 0; fault("Seri veri uzun"); }
  }
}

void tickPassage() {
  unsigned long now = millis();
#if FITGATE_SINGLE_SENSOR_PROTOTYPE
  singlePassage.release(sensors[0].valid && sensors[0].empty(), sensors[1].valid && sensors[1].empty());
  if ((mode == WAIT_ACK || mode == CLOSING) && opened) {
    if (clearPath()) {
      if (!clearAt) clearAt=now;
      if (now-clearAt>=250) { gate.write(CLOSED_ANGLE); opened=false; if (mode==CLOSING) idle(); }
    } else clearAt=0;
  }
#endif
  if (mode == DIAGNOSTIC && now-diagnosticAt>=1500) {
    bool safe = !diagnosticServo || clearPath();
    diagnosticOk=safe;
    if (safe && opened) { gate.write(CLOSED_ANGLE); opened=false; }
    Serial.print(F("DIAGDONE|")); Serial.print(diagnosticId); Serial.println(safe ? F("|ok|Test command complete") : F("|error|Area occupied / sensor fault"));
    if (safe) idle(); else fault("SENSOR HATASI");
    return;
  }
  if (mode == OPEN) {
#if FITGATE_SINGLE_SENSOR_PROTOTYPE
    singlePassage.tick(healthy(), sensors[0].detected(), sensors[1].detected(), now);
    if (singlePassage.stage == SingleSensorPassage::ERROR) {
      fault(!healthy() ? "SENSOR HATASI" : "Gecis zaman asimi"); return;
    }
    if (singlePassage.stage == SingleSensorPassage::COMPLETE) {
      passedMs=now-allowedAt; clearAt=0; mode=WAIT_ACK;
      show(direction=='E' ? F("TEST GIRIS OLAYI") : F("TEST CIKIS OLAYI"), F("KAPANMA BEKLENIR"));
      progress(F("prototype_triggered"),direction); sendPass();
    }
#else
    PassageSequence::Stage before = passage.stage;
    passage.tick(healthy(), sensors[0].detected(), sensors[1].detected(), clearPath(), now);
    if (passage.stage == PassageSequence::ERROR) {
      fault(!healthy() ? "SENSOR HATASI" : now-allowedAt>=validMs ? "Gecis zaman asimi" : "Yon belirsiz"); return;
    }
    if (before != passage.stage) {
      if (passage.stage == PassageSequence::WAIT_SECOND) {
        show(direction=='E' ? F("GIRIS ALGILANDI") : F("CIKIS ALGILANDI"), F("IKINCI SENSOR"));
        progress(F("detected"), direction);
      } else if (passage.stage == PassageSequence::WAIT_CLEAR) {
        show(F("IKI SENSOR TAMAM"), F("ALAN BOS BEKLENIR")); progress(F("waiting_clear"), direction);
      } else if (passage.stage == PassageSequence::COMPLETE) {
        passedMs = now - allowedAt;
        gate.write(CLOSED_ANGLE); opened = false;
        mode = WAIT_ACK; show(F("GECIS TAMAMLANDI"), F("KAYIT BEKLENIYOR")); progress(F("completed"), direction); sendPass();
      }
    }
#endif
  } else if (mode == FAILED) {
    if (!opened) {
      if (!clearAt) clearAt = now;
      if (now - clearAt >= 1500) idle();
      return;
    }
    // Never command closing while a sensor is occupied or unreadable.
    if (clearPath()) {
      if (!clearAt) clearAt = now;
      if (now - clearAt >= 1500) {
        if (opened) { gate.write(CLOSED_ANGLE); opened = false; }
        idle();
      }
    } else clearAt = 0;
  } else if (mode == WAIT_ACK && now - lastPassSend >= 1000) sendPass();
}

void setup() {
  Serial.begin(115200);
  pinMode(OUT_TRIG, OUTPUT); pinMode(IN_TRIG, OUTPUT);
  pinMode(OUT_ECHO, INPUT); pinMode(IN_ECHO, INPUT);
  pinMode(BUZZER_PIN, OUTPUT); pinMode(LED_PIN, OUTPUT);
  gate.attach(SERVO_PIN); gate.write(CLOSED_ANGLE);
  Wire.begin(); Wire.setWireTimeout(25000, true);
  lcdOk = lcd.begin(16, 2) == 0;
  if (lcdOk) lcd.backlight();
  SPI.begin(); reader.PCD_Init();
  Serial.print(F("READY|")); Serial.println(FITGATE_FIRMWARE_VERSION); Serial.println(F("IO|0|0")); idle();
}

void loop() {
  readCommands(); tickSignal();
  unsigned long now = millis();
  // Alternate sensors at 60 ms to limit acoustic crosstalk.
  if (now - lastSample >= 60) { sampleSensor(sampleSide); sampleSide = 1 - sampleSide; lastSample = now; }
  if (now - lastHealth >= 2000) {
    Serial.println(healthy() ? F("HEALTH|ready") : F("HEALTH|fault")); lastHealth = now;
    byte version = reader.PCD_ReadRegister(MFRC522::VersionReg);
    Serial.print(F("COMP|")); Serial.print(version != 0 && version != 0xFF ? F("ready") : F("fault"));
    Serial.print('|'); Serial.print(opened ? F("open") : F("closed"));
    Serial.print('|'); Serial.println(lcdOk ? F("ready") : F("fault"));
  }
  if (now - lastDistance >= 1000) {
    Serial.print(F("DIST|")); Serial.print(sensors[0].valid ? (int)sensors[0].cm : -1);
    Serial.print('|'); Serial.println(sensors[1].valid ? (int)sensors[1].cm : -1);
    lastDistance = now;
  }
  if (!linked && now - lastReady >= 2000) { Serial.print(F("READY|")); Serial.println(FITGATE_FIRMWARE_VERSION); lastReady = now; }
  if (mode == IDLE && now-shownAt>5000) idle();
  if (linked && now - lastPing > 12000) {
    linked = false;
    if (mode == OPEN || mode == WAIT_SERVER || mode == DIAGNOSTIC) fault("BAGLANTI YOK");
  }
  if (captureMode && now - captureAt > 50000 && mode == IDLE) { captureMode = false; idle(); Serial.println(F("MODE|normal")); }
  if (mode == WAIT_SERVER && now - requestedAt > 4000) fault("PC cevap yok");
  tickPassage();
  if (!linked || now - lastRfidPoll < 120) return;
  lastRfidPoll = now;
  byte atqa[2], size = sizeof(atqa);
  MFRC522::StatusCode status = reader.PICC_WakeupA(atqa, &size);
  if ((status != MFRC522::STATUS_OK && status != MFRC522::STATUS_COLLISION) || !reader.PICC_ReadCardSerial()) {
    if (cardLatched && now - lastCardSeen >= 500) { cardLatched = false; Serial.println(F("REMOVED")); }
    return;
  }
  lastCardSeen = now;
  bool different = reader.uid.size != lastUidSize || memcmp(lastUid, reader.uid.uidByte, reader.uid.size);
  if (mode != IDLE || (cardLatched && !different)) {
    if (mode == DIAGNOSTIC) { memcpy(lastUid,reader.uid.uidByte,reader.uid.size); lastUidSize=reader.uid.size; cardLatched=true; }
    reader.PICC_HaltA(); reader.PCD_StopCrypto1(); return;
  }
  memcpy(lastUid, reader.uid.uidByte, reader.uid.size); lastUidSize = reader.uid.size; cardLatched = true;
#if FITGATE_SINGLE_SENSOR_PROTOTYPE
  if (!singlePassage.canBegin()) { show("SENSORU BIRAKIN","YENI ISLEM YOK"); signal(2); reader.PICC_HaltA(); reader.PCD_StopCrypto1(); return; }
#endif
  direction = captureMode ? 'C' : 'A';
  activeScan = ++sequence; requestedAt = now; mode = WAIT_SERVER;
  show("Kart okunuyor", "Sunucu kontrolu");
  progress(F("authorizing"));
  Serial.print(F("SCAN|")); Serial.print(activeScan); Serial.print('|');
  for (byte i = 0; i < reader.uid.size; i++) {
    if (reader.uid.uidByte[i] < 16) Serial.print('0');
    Serial.print(reader.uid.uidByte[i], HEX);
  }
  Serial.print('|'); Serial.println(direction); reader.PICC_HaltA(); reader.PCD_StopCrypto1();
}
