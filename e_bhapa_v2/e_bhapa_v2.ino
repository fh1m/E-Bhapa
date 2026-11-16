// E-Bhapa v2 — the same robot, the same single HC-SR04, wired the way the
// comments always claimed it was.
//
// What changed from e_bhapa/e_bhapa.ino, and why:
//   1. Left pair = motors 1 + 3, right pair = motors 2 + 4. (v1 drove the
//      front pair and the rear pair, so it could never turn.)
//   2. Speeds are signed. setSpeed() gets |speed|, run() gets the sign.
//      (v1 passed negatives into a uint8_t: -255 became 1, and every run()
//      said FORWARD.)
//   3. pulseIn() has a 25 ms timeout (~4 m). No echo used to freeze the
//      loop for a whole second.
//   4. Following holds a distance instead of closing it: push when the
//      thing is far, back off when it's near, stop in a 4 cm band.
//   5. Walls are boring. One sensor can't tell a cat from a wall, but time
//      can: a cat moves. If the reading hasn't changed by more than 3 cm in
//      2.5 s, it's a wall. Turn away and go find something more interesting.
//   6. Exploration picks only from behaviours that exist.

#include <AFMotor.h>

#define TRIG_PIN 13
#define ECHO_PIN 12

const int TOO_CLOSE_CM   = 12;   // back off and turn, no questions asked
const int HOLD_CM        = 30;   // where a followed thing should sit
const int HOLD_BAND_CM   = 4;    // close enough to stop fidgeting
const int NOTICE_CM      = 60;   // anything nearer is worth following
const float KP           = 9.0;  // PWM per cm of distance error
const int MIN_PWM        = 90;   // below this the gearmotors just hum
const int CRUISE_PWM     = 180;
const int TURN_PWM       = 200;
const unsigned long BORED_MS = 2500;
const int BORED_CM       = 3;

AF_DCMotor leftFront(1), rightFront(2), leftRear(3), rightRear(4);

long boredSinceDist = -1;
unsigned long boredSinceMs = 0;

void side(AF_DCMotor &a, AF_DCMotor &b, int pwm) {
  pwm = constrain(pwm, -255, 255);
  uint8_t mag = abs(pwm);
  uint8_t dir = pwm > 0 ? FORWARD : (pwm < 0 ? BACKWARD : RELEASE);
  a.setSpeed(mag); b.setSpeed(mag);
  a.run(dir);      b.run(dir);
}

void drive(int left, int right) {
  side(leftFront, leftRear, left);
  side(rightFront, rightRear, right);
}

void stopAll() { drive(0, 0); }

long distanceCm() {
  digitalWrite(TRIG_PIN, LOW);  delayMicroseconds(4);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long us = pulseIn(ECHO_PIN, HIGH, 25000UL);
  return us == 0 ? 400 : (long)(us * 0.0343 / 2.0);  // no echo = nothing there
}

void turnAway() {
  bool left = random(2) == 0;
  drive(left ? -TURN_PWM : TURN_PWM, left ? TURN_PWM : -TURN_PWM);
  delay(random(250, 600));
  stopAll();
}

bool isBoring(long d) {
  if (boredSinceDist < 0 || abs(d - boredSinceDist) > BORED_CM) {
    boredSinceDist = d;
    boredSinceMs = millis();
    return false;
  }
  return millis() - boredSinceMs > BORED_MS;
}

void hold(long d) {
  long err = d - HOLD_CM;                     // + means it's far, go forward
  if (abs(err) <= HOLD_BAND_CM) { stopAll(); return; }
  int pwm = (int)(KP * err);
  if (abs(pwm) < MIN_PWM) pwm = pwm > 0 ? MIN_PWM : -MIN_PWM;
  drive(pwm, pwm);
}

void explore() {
  switch (random(0, 4)) {
    case 0: case 1: drive(CRUISE_PWM, CRUISE_PWM); delay(400); break;
    case 2: turnAway(); break;
    case 3: stopAll(); delay(random(200, 500)); break;   // look around, like a cat
  }
}

void setup() {
  Serial.begin(9600);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  randomSeed(analogRead(A0));
}

void loop() {
  long d = distanceCm();
  Serial.println(d);

  if (d < TOO_CLOSE_CM) {
    drive(-CRUISE_PWM, -CRUISE_PWM); delay(300); turnAway();
  } else if (d < NOTICE_CM) {
    if (isBoring(d)) { turnAway(); boredSinceDist = -1; }
    else hold(d);
  } else {
    boredSinceDist = -1;
    explore();
  }
  delay(50);
}
