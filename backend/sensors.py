"""Conversions indépendantes du matériel, donc faciles à tester."""
import math
from collections import deque
from statistics import mean


def cardinal(degrees):
    return ("N", "NE", "E", "SE", "S", "SO", "O", "NO")[int((degrees % 360 + 22.5) // 45) % 8]


def decode_encoder(lines, config):
    """Ligne 0 = bit de poids faible ; les quatre états restent indépendants."""
    if len(lines) != 4:
        raise ValueError("L'encodeur doit utiliser exactement quatre lignes numériques.")
    bits = [int(bool(value)) ^ int(config.encoder_active_low) for value in lines]
    if config.encoder_reverse_bits:
        bits.reverse()
    value = sum(bit << i for i, bit in enumerate(bits))
    if config.encoder_encoding == "gray":
        gray = value
        while gray:
            gray >>= 1
            value ^= gray
    return value


def direction_angle(value, config):
    if value is None or not config.calibrated:
        return None
    if config.direction_mode == "table":
        anchors = [(abs(value-voltage), index*45) for index, bearing in enumerate(("N","NE","E","SE","S","SO","O","NO"))
                   if (voltage := config.direction_voltages.get(bearing)) is not None]
        anchors.sort()
        if not anchors or anchors[0][0] > config.direction_tolerance:
            return None
        if len(anchors) > 1 and math.isclose(anchors[0][0], anchors[1][0], abs_tol=1e-9):
            return None
        return anchors[0][1]
    angle = linear(value, config)
    if angle is None:
        return None
    return ((-angle if config.direction_reversed else angle) + config.direction_offset) % 360


def linear(value, config):
    if value is None or not config.calibrated or config.scale is None:
        return None
    result = value * config.scale + config.offset
    return result if math.isfinite(result) else None


def frequency(samples, sample_rate, threshold=2.0):
    """Fréquence entre fronts montants ; aucun 0 fictif si la fenêtre est trop courte."""
    edges = [i for i in range(1, len(samples)) if samples[i - 1] < threshold <= samples[i]]
    if len(edges) < 2:
        return None
    return sample_rate * (len(edges) - 1) / (edges[-1] - edges[0])


def counter_delta(current, previous, bits=32):
    if previous is None:
        return 0
    if current >= previous:
        return current - previous
    # Un débordement n'est reconnu qu'au voisinage de la borne du compteur.
    modulus = 2 ** bits
    if previous > modulus * .9 and current < modulus * .1:
        return modulus - previous + current
    return current  # remise à zéro ; jamais de différence négative


class RainAccumulator:
    def __init__(self, total_ml=0, total_pulses=0):
        self.previous = None
        self.total_ml = total_ml
        self.total_pulses = total_pulses

    @classmethod
    def restore(cls, checkpoint):
        return cls(**checkpoint) if isinstance(checkpoint, dict) else cls(total_ml=checkpoint)

    def checkpoint(self):
        return {"total_ml": self.total_ml, "total_pulses": self.total_pulses}

    def update(self, count, ml_per_pulse, collector_cm2=None):
        pulses = counter_delta(count, self.previous)
        self.previous = count
        self.total_pulses += pulses
        delta = pulses * ml_per_pulse if ml_per_pulse else None
        if delta is not None:
            self.total_ml += delta
        total = self.total_ml if ml_per_pulse else None
        return {"rain_count": self.total_pulses, "rain_delta_count": pulses,
                "rain_delta_ml": delta, "rain_ml": total,
                "rain_delta_mm": delta * 10 / collector_cm2 if delta is not None and collector_cm2 else None,
                "rain_mm": total * 10 / collector_cm2 if total is not None and collector_cm2 else None}


class WindPeaks:
    """Un pic = maximum de chaque fenêtre non chevauchante, au-dessus du seuil."""
    def __init__(self, window, threshold):
        self.window, self.threshold = window, threshold
        self.started = None
        self.best = None

    def update(self, timestamp, value):
        if self.started is None:
            self.started = timestamp
        event = None
        if (timestamp - self.started).total_seconds() >= self.window:
            event = self.finish()
            self.started = timestamp
        if value is not None and (self.best is None or value > self.best[1]):
            self.best = (timestamp, value)
        return event

    def finish(self):
        best, self.best = self.best, None
        if best and best[1] >= self.threshold:
            return {"timestamp": best[0].isoformat(), "value": best[1], "window_seconds": self.window}
        return None


class AnomalyDetector:
    def __init__(self):
        self.history = {}

    def check(self, name, value, timestamp):
        if value is None:
            return []
        ranges = {"temperature": (-80, 80), "humidity": (0, 100), "light": (0, 100), "wind": (0, 500)}
        warnings = []
        if name in ranges and not ranges[name][0] <= value <= ranges[name][1]:
            warnings.append("Valeur hors domaine : vérifier le capteur et l'étalonnage.")
        previous = self.history.get(name)
        if previous:
            old, changed, last = previous
            dt = max(.001, (timestamp - last).total_seconds())
            if name == "temperature" and abs(value - old) / dt > 3:
                warnings.append("Variation thermique suspecte : contrôle conseillé.")
            if abs(value - old) > .000001:
                changed = timestamp
            if (timestamp - changed).total_seconds() >= 600:
                warnings.append("Valeur inchangée depuis 10 min : capteur possiblement bloqué.")
        else:
            changed = timestamp
        self.history[name] = (value, changed, timestamp)
        return warnings


def comfort(temperature, relative_humidity, wind):
    if any(x is None for x in (temperature, relative_humidity, wind)):
        return None
    return round(max(0, min(100, 100 - 3 * abs(temperature - 22) - .5 * abs(relative_humidity - 50) - .6 * wind)))
