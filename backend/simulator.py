"""Données entièrement fictives. Aucune dépendance aux étalonnages matériels."""
import math
import random
import time


class Simulator:
    def __init__(self, seed=None):
        self.random = random.Random(seed)
        self.start = time.monotonic()
        self.last = self.start
        self.rain_count = 0
        self.rain_fraction = 0
        self.direction = 225

    def read(self):
        now = time.monotonic()
        t, dt = now - self.start, now - self.last
        self.last = now
        self.direction = (self.direction + self.random.uniform(-5, 5)) % 360
        wind = max(0, 13 + 5 * math.sin(t / 23) + 24 * max(0, math.sin(t / 12)) ** 12 + self.random.uniform(-1, 1))
        self.rain_fraction += (1.5 if math.sin(t / 35) > .3 else 0) * dt
        tips = int(self.rain_fraction)
        self.rain_fraction -= tips
        self.rain_count += tips
        return {"temperature": 22 + 5 * math.sin(t / 90), "direction": self.direction,
                "wind": wind, "humidity": 35 + 30 * math.sin(t / 70),
                "relative_humidity": 58 + 12 * math.sin(t / 55),
                "light": max(0, 65 + 20 * math.sin(t / 130)), "rain_count": self.rain_count,
                "counter": None}

    def close(self):
        pass
