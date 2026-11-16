"""Configuration validée : aucun coefficient matériel n'est activé implicitement."""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[1]
SENSOR_NAMES = ("temperature", "direction", "wind", "rain", "humidity", "light", "counter")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SensorConfig(StrictModel):
    enabled: bool = False
    kind: Literal["voltage", "frequency", "counter", "digital"] = "voltage"
    channel: str | None = None
    terminal: str | None = None
    terminal_config: Literal["RSE", "DIFF", "NRSE", "DEFAULT"] = "RSE"
    edge: Literal["RISING", "FALLING"] = "FALLING"
    calibrated: bool = False
    scale: float | None = None
    offset: float = 0
    unit: str = Field(default="", max_length=30)
    quantity: Literal["physical", "surface_wetness", "relative_humidity"] = "physical"
    min_voltage: float = -10
    max_voltage: float = 10
    ml_per_pulse: float | None = Field(default=None, gt=0)
    collector_cm2: float | None = Field(default=None, gt=0)
    direction_mode: Literal["linear", "table"] = "linear"
    direction_voltages: dict[Literal["N", "NE", "E", "SE", "S", "SO", "O", "NO"], float | None] = Field(default_factory=dict)
    direction_tolerance: float = Field(default=.2, gt=0, le=2)
    direction_reversed: bool = False
    direction_offset: float = 0
    encoder_active_low: bool = False
    encoder_reverse_bits: bool = False
    encoder_encoding: Literal["binary", "gray"] = "binary"
    poll_ms: int = Field(default=10, ge=2, le=100)
    debounce_ms: int = Field(default=40, ge=0, le=2000)

    @model_validator(mode="after")
    def valid(self):
        voltages = [value for value in self.direction_voltages.values() if value is not None]
        if len(voltages) != len(set(voltages)):
            raise ValueError("Deux directions ne peuvent pas avoir la même tension.")
        if self.direction_mode == "table" and not voltages:
            raise ValueError("Renseigner au moins une tension pour la girouette.")
        if self.min_voltage >= self.max_voltage:
            raise ValueError("La tension minimale doit être inférieure au maximum.")
        if self.calibrated and self.kind != "digital" and self.direction_mode != "table" and self.scale is None and self.ml_per_pulse is None:
            raise ValueError("Un capteur étalonné doit avoir un coefficient.")
        return self


class Limits(StrictModel):
    low: float | None = None
    high: float | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.low is not None and self.high is not None and self.low >= self.high:
            raise ValueError("Le seuil bas doit être inférieur au seuil haut.")
        return self


class AlarmConfig(StrictModel):
    seasonal: bool = True
    temperature: Limits = Field(default_factory=lambda: Limits(low=0, high=30))
    seasons: dict[str, Limits] = Field(default_factory=lambda: {
        "hiver": Limits(low=-5, high=18), "printemps": Limits(low=2, high=28),
        "ete": Limits(low=10, high=35), "automne": Limits(low=0, high=25)})
    rain_unit: Literal["mL", "mm", "impulsions"] = "mL"
    rain: Limits = Field(default_factory=lambda: Limits(low=None, high=100))

    @model_validator(mode="after")
    def complete(self):
        if set(self.seasons) != {"hiver", "printemps", "ete", "automne"}:
            raise ValueError("Renseigner les quatre saisons.")
        return self


class Settings(StrictModel):
    mode: Literal["simulation", "hardware"] = "simulation"
    station_number: int = Field(default=1, ge=0, le=65535)
    station_from_encoder: bool = True
    rain_display_unit: Literal["mL", "mm", "impulsions"] = "mL"
    device: str = Field(default="Dev1", pattern=r"^[A-Za-z0-9_-]+$")
    interval_seconds: float = Field(default=1, ge=1, le=60)
    save_seconds: float = Field(default=10, ge=1, le=300)
    sample_rate_hz: int = Field(default=5000, ge=1000, le=100000)
    sample_count: int = Field(default=1000, ge=200, le=10000)
    peak_window_seconds: int = Field(default=30, ge=3, le=3600)
    peak_threshold_kmh: float = Field(default=30, ge=0, le=500)
    timezone: str = "Europe/Paris"
    sensors: dict[str, SensorConfig]
    alarms: AlarmConfig = Field(default_factory=AlarmConfig)

    @model_validator(mode="after")
    def validate_settings(self):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Fuseau horaire inconnu (exemple : Europe/Paris).") from exc
        if set(self.sensors) != set(SENSOR_NAMES):
            raise ValueError("Les sept capteurs doivent être définis (enabled=false si absent).")
        if self.sample_count / self.sample_rate_hz > self.interval_seconds * .8:
            raise ValueError("La fenêtre analogique doit laisser du temps au cycle d'acquisition.")
        used = [s.channel for s in self.sensors.values() if s.enabled and s.channel]
        if len(used) != len(set(used)):
            raise ValueError("Deux capteurs ne peuvent pas réserver la même voie.")
        allowed = {"temperature": {"voltage"}, "direction": {"voltage"},
                   "humidity": {"voltage", "frequency"}, "light": {"voltage"},
                   "wind": {"counter", "frequency"}, "rain": {"counter", "digital"},
                   "counter": {"counter", "digital"}}
        for name, sensor in self.sensors.items():
            if sensor.kind not in allowed[name]:
                raise ValueError(f"Type de mesure incompatible : {name} / {sensor.kind}.")
        return self


def load_config(path: Path = ROOT / "config.yaml") -> Settings:
    return Settings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def save_config(settings: Settings, path: Path):
    # Remplacement atomique : le fichier reste lisible après une interruption d'écriture.
    temporary = path.with_suffix(".yaml.tmp")
    temporary.write_text(yaml.safe_dump(settings.model_dump(), allow_unicode=True, sort_keys=False), encoding="utf-8")
    temporary.replace(path)
