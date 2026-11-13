"""Statistiques sur toutes les mesures conservées, sans mélange de sources."""
from datetime import datetime


def statistics(database, start, end, source, station):
    result = database.aggregates(start, end, source, station)
    alarms = database.alarms(source, station, start, end)
    duration = 0
    for alarm in alarms:
        if alarm["sensor"] == "temperature":
            left = max(datetime.fromisoformat(start), datetime.fromisoformat(alarm["start"]))
            right = min(datetime.fromisoformat(end), datetime.fromisoformat(alarm["end"] or alarm["last_seen"]))
            duration += max(0, min(alarm["duration"], (right - left).total_seconds()))
    result.update(source=source, station=station, start=start, end=end,
                  temperature_alarm_seconds=duration, alarms_count=len(alarms))
    return result
