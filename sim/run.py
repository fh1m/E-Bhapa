"""Three E-Bhapas in a room with a cat.

  v1          e_bhapa/e_bhapa.ino exactly as flashed in 2024, including the two
              hardware quirks it ran into (uint8 wrap, front/rear wiring).
  v1 rewired  the same logic with the wiring and the signs fixed.
  v2          e_bhapa_v2/e_bhapa_v2.ino.

The room is 3 m x 3 m. The cat (Bhapa, radius 12 cm) wanders at 0.15 m/s
and pauses now and then, as cats do. The HC-SR04 is a single forward ray
that sees walls and cat alike.

    python -m sim.run                 # prints the table, writes assets/*.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOM, FULL_SPEED, TRACK, BODY_R, CAT_R = 3.0, 0.45, 0.14, 0.09, 0.12
DT = 0.01
ASSETS = Path(__file__).resolve().parent.parent / "assets"


class Cat:
    def __init__(self, rng):
        self.rng, self.p, self.h, self.pause = rng, np.array([2.2, 2.0]), 1.0, 0.0

    def step(self):
        if self.pause > 0:
            self.pause -= DT
            return
        if self.rng.random() < 0.002:
            self.pause = self.rng.uniform(1, 4)
        self.h += self.rng.normal(0, 0.08)
        nxt = self.p + 0.15 * DT * np.array([np.cos(self.h), np.sin(self.h)])
        if not (0.3 < nxt[0] < ROOM - 0.3 and 0.3 < nxt[1] < ROOM - 0.3):
            self.h += np.pi * 0.7
        else:
            self.p = nxt


def ray(x, y, th, cat: Cat | None):
    c, s = np.cos(th), np.sin(th)
    ts = [t for t, ok in (((ROOM - x) / c if c > 1e-9 else 0, c > 1e-9), (-x / c if c < -1e-9 else 0, c < -1e-9),
                          ((ROOM - y) / s if s > 1e-9 else 0, s > 1e-9), (-y / s if s < -1e-9 else 0, s < -1e-9)) if ok]
    d = min(ts)
    if cat is not None:  # ray-circle intersection
        o = np.array([x, y]) - cat.p
        b = o @ np.array([c, s])
        disc = b * b - (o @ o - CAT_R**2)
        if disc >= 0:
            t = -b - np.sqrt(disc)
            if 0 < t < d:
                d = t
    return min(d, 4.0)


class Bot:
    def __init__(self, version: str, seed: int, cat: bool):
        self.v, self.rng = version, np.random.default_rng(seed)
        self.cat = Cat(np.random.default_rng(seed + 100)) if cat else None
        self.x, self.y, self.th = 0.8, 0.8, 0.6
        self.cmd = (0.0, 0.0)
        self.path, self.t, self.pinned, self.near_cat = [], 0.0, 0.0, 0.0
        self.bored_d, self.bored_t = None, 0.0

    def drive(self, l, r):
        if self.v == "v1":
            side = ((l % 256) + (r % 256)) / 2 / 255 * FULL_SPEED
            self.cmd = (side, side)
        else:
            self.cmd = (np.clip(l, -255, 255) / 255 * FULL_SPEED, np.clip(r, -255, 255) / 255 * FULL_SPEED)

    def stop(self):
        self.cmd = (0.0, 0.0)

    def wait(self, ms):
        for _ in range(int(ms / 1000 / DT)):
            vl, vr = self.cmd
            v, w = (vl + vr) / 2, (vr - vl) / TRACK
            nx, ny = self.x + v * np.cos(self.th) * DT, self.y + v * np.sin(self.th) * DT
            hit = not (BODY_R <= nx <= ROOM - BODY_R and BODY_R <= ny <= ROOM - BODY_R)
            if self.cat is not None and np.hypot(nx - self.cat.p[0], ny - self.cat.p[1]) < BODY_R + CAT_R:
                hit = True  # bumped the cat; she does not move for you
            if hit and abs(v) > 1e-6:
                self.pinned += DT
            else:
                self.x, self.y = nx, ny
            self.th += w * DT
            if self.cat is not None:
                self.cat.step()
                if np.hypot(self.x - self.cat.p[0], self.y - self.cat.p[1]) < 0.6:
                    self.near_cat += DT
            self.t += DT
            self.path.append((self.x, self.y))

    def sonar_cm(self):
        return int(ray(self.x, self.y, self.th, self.cat) * 100)

    # -- e_bhapa.ino ---------------------------------------------------------
    def loop_v1(self):
        d = self.sonar_cm()
        if 0 < d < 25:
            s = int(np.interp(d, [0, 25], [100, 255])); self.drive(s, s)
        elif 25 <= d < 30:
            self.stop(); self.wait(self.rng.integers(300, 800))
            left = self.rng.integers(2) == 0
            self.drive(0 if left else 200, 200 if left else 0)
            self.wait(self.rng.integers(200, 500)); self.stop()
        else:
            a, sp = self.rng.integers(0, 10), (255 if d > 25 else 150)
            if a == 0: self.drive(sp, sp)
            elif a == 1: self.drive(-sp, -sp)
            elif a == 2: self.drive(-200, 200); self.wait(self.rng.integers(200, 500)); self.stop()
            elif a == 3: self.drive(200, -200); self.wait(self.rng.integers(200, 500)); self.stop()
            elif a == 4: self.stop(); self.wait(self.rng.integers(300, 800))
        self.wait(100)

    # -- e_bhapa_v2.ino ------------------------------------------------------
    def turn_away(self):
        left = self.rng.integers(2) == 0
        self.drive(-200 if left else 200, 200 if left else -200)
        self.wait(self.rng.integers(250, 600)); self.stop()

    def loop_v2(self):
        d = self.sonar_cm()
        if d < 12:
            self.drive(-180, -180); self.wait(300); self.turn_away()
        elif d < 60:
            if self.bored_d is None or abs(d - self.bored_d) > 3:
                self.bored_d, self.bored_t = d, self.t
            if self.t - self.bored_t > 2.5:
                self.turn_away(); self.bored_d = None
            else:
                err = d - 30
                if abs(err) <= 4:
                    self.stop()
                else:
                    pwm = int(np.clip(9.0 * err, -255, 255))
                    if abs(pwm) < 90: pwm = 90 if pwm > 0 else -90
                    self.drive(pwm, pwm)
        else:
            self.bored_d = None
            a = self.rng.integers(0, 4)
            if a in (0, 1): self.drive(180, 180); self.wait(400)
            elif a == 2: self.turn_away()
            else: self.stop(); self.wait(self.rng.integers(200, 500))
        self.wait(50)

    def loop(self):
        (self.loop_v2 if self.v == "v2" else self.loop_v1)()


def run(version, seed, cat=True, minutes=3.0):
    b = Bot(version, seed, cat)
    while b.t < minutes * 60:
        b.loop()
    return b


def coverage(path, cells=20):
    ij = np.clip((np.array(path) / ROOM * cells).astype(int), 0, cells - 1)
    return len({(i, j) for i, j in ij}) / cells**2 * 100


VERSIONS = [("v1", "v1, as flashed in 2024", "#b3261e"),
            ("v1-rewired", "v1, wiring fixed", "#c2571a"),
            ("v2", "v2", "#1f4e8c")]


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans Mono", "font.size": 10})
    fig, axes = plt.subplots(1, 3, figsize=(14, 5), dpi=150)
    rows = []
    for ax, (v, label, colour) in zip(axes, VERSIONS):
        bots = [run(v, s) for s in range(10)]
        rows.append((label, np.mean([b.pinned / b.t for b in bots]) * 100,
                     np.mean([coverage(b.path) for b in bots]),
                     np.mean([b.near_cat / b.t for b in bots]) * 100))
        b = bots[0]
        p = np.array(b.path)
        ax.plot(p[:, 0], p[:, 1], color=colour, lw=0.7)
        ax.plot(*p[0], "o", color="k", ms=5)
        ax.add_patch(plt.Circle(b.cat.p, CAT_R, color="#d9a066", zorder=3))
        ax.text(b.cat.p[0], b.cat.p[1] + 0.18, "Bhapa", ha="center", fontsize=8)
        ax.set_xlim(0, ROOM); ax.set_ylim(0, ROOM); ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"{label} · 3 min", fontsize=10, loc="left")
        for s in ax.spines.values():
            s.set_linewidth(2)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(ASSETS / "three_minutes.png", bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)

    print(f"{'':24} pinned   room seen   near the cat")
    for label, pin, cov, cat in rows:
        print(f"{label:24} {pin:5.0f}%   {cov:8.0f}%   {cat:11.0f}%")
    print("uint8 wrap: -255 ->", (-255) % 256, " -200 ->", (-200) % 256, " -150 ->", (-150) % 256)


if __name__ == "__main__":
    main()
