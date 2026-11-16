"""What did E-Bhapa actually do?

main.ino, executed faithfully in a 3 m x 3 m room: the same thresholds,
the same random choices, the same delays, and the same two quirks of the
hardware it ran on.

  1. AFMotor's setSpeed() takes a uint8_t, and every run() call says FORWARD.
     A "negative" speed wraps: -255 -> 1, -200 -> 56, -150 -> 106.
  2. adjustMotorSpeed(left, right) gives `left` to motors 1 and 2 (front-left,
     front-right) and `right` to motors 3 and 4 (rear-left, rear-right). On a
     skid-steer chassis each side then averages (left + right) / 2. Both sides
     always get the same value, so it can't turn.

"as written" runs those quirks. "as intended" fixes them (signed speeds,
left pair / right pair) and changes nothing else.

    python -m sim.run                 # prints the table, writes assets/*.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOM = 3.0                 # metres, square
FULL_SPEED = 0.45          # m/s at PWM 255 (a cheap 4WD kit, roughly)
TRACK = 0.14               # m between left and right wheels
BODY_R = 0.09              # m, for collision checks
FOLLOW, AVOID = 0.25, 0.30 # SONAR_FOLLOW_DISTANCE and the 30 cm band, in m
DT = 0.01
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def sonar(x, y, th):
    """Distance straight ahead to the nearest wall, in metres (HC-SR04 range cap 4 m)."""
    c, s = np.cos(th), np.sin(th)
    ts = []
    if c > 1e-9: ts.append((ROOM - x) / c)
    if c < -1e-9: ts.append(-x / c)
    if s > 1e-9: ts.append((ROOM - y) / s)
    if s < -1e-9: ts.append(-y / s)
    return min(min(ts), 4.0)


class Bot:
    def __init__(self, faithful: bool, seed: int):
        self.faithful = faithful
        self.rng = np.random.default_rng(seed)
        self.x, self.y, self.th = 1.5, 1.2, 0.3
        self.cmd = (0.0, 0.0)  # wheel speeds in m/s, left side / right side
        self.path, self.bumps, self.t, self.bumping = [], 0, 0.0, False
        self.pinned, self.first_pin = 0.0, None  # seconds spent driving into a wall

    # -- the two quirks -----------------------------------------------------
    def drive(self, left_pwm: int, right_pwm: int):
        if self.faithful:
            l8, r8 = left_pwm % 256, right_pwm % 256       # uint8_t wrap, always FORWARD
            side = (l8 + r8) / 2 / 255 * FULL_SPEED        # each side averages front and rear
            self.cmd = (side, side)
        else:
            self.cmd = (left_pwm / 255 * FULL_SPEED, right_pwm / 255 * FULL_SPEED)

    def stop(self):
        self.cmd = (0.0, 0.0)

    # -- physics ------------------------------------------------------------
    def wait(self, ms: float):
        for _ in range(int(ms / 1000 / DT)):
            vl, vr = self.cmd
            v, w = (vl + vr) / 2, (vr - vl) / TRACK
            nx = self.x + v * np.cos(self.th) * DT
            ny = self.y + v * np.sin(self.th) * DT
            hit = not (BODY_R <= nx <= ROOM - BODY_R and BODY_R <= ny <= ROOM - BODY_R)
            if hit and not self.bumping:
                self.bumps += 1
            self.bumping = hit
            if hit:
                self.pinned += DT
                if self.first_pin is None:
                    self.first_pin = self.t
            if not hit:
                self.x, self.y = nx, ny
            self.th += w * DT
            self.t += DT
            self.path.append((self.x, self.y))

    # -- main.ino, line by line ----------------------------------------------
    def loop(self):
        d = sonar(self.x, self.y, self.th)
        d_cm = int(d * 100)
        if 0 < d_cm < 25:
            self.drive(*(2 * [int(np.interp(d_cm, [0, 25], [100, 255]))]))     # followObject
        elif 25 <= d_cm < 30:
            self.stop(); self.wait(self.rng.integers(300, 800))                 # dynamicObstacleAvoidance
            left = self.rng.integers(2) == 0
            self.drive(0 if left else 200, 200 if left else 0)
            self.wait(self.rng.integers(200, 500)); self.stop()
        else:                                                                    # enhancedExploration
            a = self.rng.integers(0, 10)
            sp = 255 if d > FOLLOW else 150
            if a == 0: self.drive(sp, sp)
            elif a == 1: self.drive(-sp, -sp)
            elif a == 2: self.drive(-200, 200); self.wait(self.rng.integers(200, 500)); self.stop()
            elif a == 3: self.drive(200, -200); self.wait(self.rng.integers(200, 500)); self.stop()
            elif a == 4: self.stop(); self.wait(self.rng.integers(300, 800))
            # 5..9: no case, keep doing whatever it was doing
        self.wait(100)                                                           # delay(100)


def run(faithful: bool, seed: int, minutes: float = 3.0) -> Bot:
    b = Bot(faithful, seed)
    while b.t < minutes * 60:
        b.loop()
    return b


def coverage(path, cells=20) -> float:
    p = np.array(path)
    ij = np.clip((p / ROOM * cells).astype(int), 0, cells - 1)
    return len({(i, j) for i, j in ij}) / cells**2 * 100


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans Mono", "font.size": 10})
    fig, axes = plt.subplots(1, 2, figsize=(10, 5), dpi=150)
    stats = {}
    for ax, (label, faithful, colour) in zip(axes, (("as written", True, "#b3261e"),
                                                    ("as intended", False, "#1f4e8c"))):
        bots = [run(faithful, s) for s in range(10)]
        stats[label] = (np.mean([b.pinned / b.t for b in bots]) * 100,
                        np.median([b.first_pin if b.first_pin is not None else np.inf for b in bots]),
                        np.mean([coverage(b.path) for b in bots]))
        p = np.array(bots[0].path)
        ax.plot(p[:, 0], p[:, 1], color=colour, lw=0.7)
        ax.plot(*p[0], "o", color="k", ms=5)
        ax.set_xlim(0, ROOM), ax.set_ylim(0, ROOM), ax.set_aspect("equal")
        ax.set_xticks([]), ax.set_yticks([])
        ax.set_title(f"{label} · 3 minutes", fontsize=10, loc="left")
        for s in ax.spines.values():
            s.set_linewidth(2)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(ASSETS / "three_minutes.png", bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)

    print("             pinned to a wall   first pinned after   room covered")
    for k, (p, f, c) in stats.items():
        print(f"{k:>12}    {p:13.0f}%   {f:17.1f} s   {c:11.0f}%")
    print("uint8 wrap: -255 ->", (-255) % 256, " -200 ->", (-200) % 256, " -150 ->", (-150) % 256)


if __name__ == "__main__":
    main()
