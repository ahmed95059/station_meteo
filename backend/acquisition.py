"""Couche NI : tâches persistantes, diagnostic explicite, aucune donnée de secours."""
import re
import threading
import time
from statistics import mean

from .sensors import decode_encoder, frequency


def inventory():
    try:
        from nidaqmx.system import System
        devices = []
        for device in System.local().devices:
            devices.append({"name": device.name, "model": device.product_type,
                            "simulated": device.dev_is_simulated,
                            "analog": [c.name for c in device.ai_physical_chans],
                            "counters": [c.name for c in device.ci_physical_chans],
                            "digital": [c.name for c in device.di_lines],
                            "terminals": list(device.terminals)})
        return {"devices": devices, "error": None}
    except Exception as exc:
        return {"devices": [], "error": f"NI-DAQmx indisponible : {exc}"}


class DigitalRain:
    """Comptage logiciel de contacts LENTS uniquement. Préférer un compteur matériel."""
    def __init__(self, channel, config):
        self.channel, self.config = channel, config
        self.stop_event, self.ready = threading.Event(), threading.Event()
        self.count, self.error = 0, None
        self.thread = threading.Thread(target=self.run, name="pluie-contact", daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            self.close()
            raise RuntimeError("Délai dépassé à l'ouverture du contact pluviomètre.")
        if self.error:
            self.close()
            raise RuntimeError(self.error)

    def run(self):
        try:
            import nidaqmx
            with nidaqmx.Task() as task:
                task.di_channels.add_di_chan(self.channel)
                previous = bool(task.read(timeout=1))
                last_edge = -float("inf")
                self.ready.set()
                while not self.stop_event.wait(self.config.poll_ms / 1000):
                    current = bool(task.read(timeout=1))
                    now = time.monotonic()
                    edge = (previous and not current) if self.config.edge == "FALLING" else (not previous and current)
                    if edge and (now - last_edge) * 1000 >= self.config.debounce_ms:
                        self.count += 1
                        last_edge = now
                    previous = current
        except Exception as exc:
            self.error = f"Contact pluviomètre : {exc}"
        finally:
            self.ready.set()

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=5)


class NIAcquisition:
    def __init__(self, settings):
        import nidaqmx
        from nidaqmx.constants import AcquisitionType, Edge, LineGrouping, TerminalConfiguration
        self.settings = settings
        self.tasks, self.counter_tasks, self.encoder = [], {}, None
        self.analog, self.rain_poller, self.analog_names = None, None, []
        self.diagnostics = inventory()
        device = next((d for d in self.diagnostics["devices"] if d["name"] == settings.device), None)
        if not device:
            raise RuntimeError(self.diagnostics["error"] or f"Périphérique {settings.device} absent. Vérifier NI MAX.")
        if device["simulated"]:
            raise RuntimeError("Ce périphérique NI MAX est simulé. Utiliser le mode simulation de l'application.")
        self.sensor_errors = {}
        try:
            for name, config in settings.sensors.items():
                if not config.enabled:
                    continue
                full = f"{settings.device}/{config.channel}" if config.channel else None
                if not full:
                    self.sensor_errors[name] = "Voie non renseignée."
                    continue
                collection = device["analog"] if config.kind in ("voltage", "frequency") else device["counters"] if config.kind == "counter" else device["digital"]
                match = re.fullmatch(r"(.*line)(\d+):(\d+)", full)
                names = [f"{match[1]}{i}" for i in range(int(match[2]), int(match[3])+1)] if match else [full]
                if not names or any(c not in collection for c in names):
                    self.sensor_errors[name] = f"Voie absente ou incompatible : {full}"
                    continue
                if config.kind in ("voltage", "frequency"):
                    if self.analog is None:
                        self.analog = nidaqmx.Task()
                        self.tasks.append(self.analog)
                    self.analog.ai_channels.add_ai_voltage_chan(full, terminal_config=getattr(TerminalConfiguration, config.terminal_config),
                                                              min_val=config.min_voltage, max_val=config.max_voltage)
                    self.analog_names.append(name)
                elif config.kind == "counter":
                    task = nidaqmx.Task()
                    self.tasks.append(task)
                    channel = task.ci_channels.add_ci_count_edges_chan(full, edge=getattr(Edge, config.edge))
                    if config.terminal:
                        terminal = config.terminal if config.terminal.startswith('/') else f"/{settings.device}/{config.terminal}"
                        if terminal not in device["terminals"]:
                            raise ValueError(f"Borne compteur absente : {terminal}")
                        channel.ci_count_edges_term = terminal
                    task.start()
                    self.counter_tasks[name] = task
                elif name == "rain":
                    self.rain_poller = DigitalRain(full, config)
                else:
                    self.encoder = nidaqmx.Task()
                    self.tasks.append(self.encoder)
                    self.encoder.di_channels.add_di_chan(full, line_grouping=LineGrouping.CHAN_PER_LINE)
            if self.analog:
                self.analog.timing.cfg_samp_clk_timing(settings.sample_rate_hz, sample_mode=AcquisitionType.FINITE,
                                                      samps_per_chan=settings.sample_count)
            if not self.tasks and not self.rain_poller:
                raise RuntimeError(f"Aucune voie exploitable : {self.sensor_errors}")
        except Exception:
            self.close()
            raise

    def read(self):
        result = {"errors": dict(self.sensor_errors), "raw": {}}
        if self.analog:
            self.analog.start()
            try:
                blocks = self.analog.read(number_of_samples_per_channel=self.settings.sample_count, timeout=2)
            finally:
                self.analog.stop()
            if len(self.analog_names) == 1:
                blocks = [blocks]
            for name, samples in zip(self.analog_names, blocks):
                config = self.settings.sensors[name]
                value = frequency(samples, self.settings.sample_rate_hz) if config.kind == "frequency" else mean(samples)
                result["raw"][name] = {"value": value, "unit": "Hz" if config.kind == "frequency" else "V",
                                       "voltage_mean": mean(samples)}
                if value is None:
                    result["errors"][name] = "Pas assez de fronts : fréquence indéterminée. Allonger la fenêtre ou vérifier le signal."
        for name, task in self.counter_tasks.items():
            result["raw"][name] = {"value": int(task.read(timeout=2)), "unit": "impulsions", "read_monotonic": time.monotonic()}
        if self.rain_poller:
            if self.rain_poller.error:
                raise RuntimeError(self.rain_poller.error)
            result["raw"]["rain"] = {"value": self.rain_poller.count, "unit": "impulsions"}
        if self.encoder:
            lines = self.encoder.read(timeout=2)
            result["raw"]["counter"] = {
                "value": decode_encoder(lines, self.settings.sensors["counter"]),
                "unit": "entier", "lines": [bool(value) for value in lines]}
        return result

    def close(self):
        if self.rain_poller:
            self.rain_poller.close()
            self.rain_poller = None
        for task in reversed(self.tasks):
            try:
                task.close()
            except Exception:
                pass
        self.tasks.clear()
