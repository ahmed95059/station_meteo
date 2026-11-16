"""Statistiques sur toutes les mesures conservées, sans mélange de sources."""
from datetime import datetime
from zoneinfo import ZoneInfo


def statistics(database, start, end, source, station):
    result = database.aggregates(start, end, source, station)
    alarms = database.alarms(source, station, start, end)
    duration = 0
    by_season = dict.fromkeys(("hiver", "printemps", "ete", "automne"), 0)
    local_zone = ZoneInfo(database.get_setting("configuration", {}).get("timezone", "Europe/Paris"))
    for alarm in alarms:
        if alarm["sensor"] == "temperature":
            left = max(datetime.fromisoformat(start), datetime.fromisoformat(alarm["start"]))
            right = min(datetime.fromisoformat(end), datetime.fromisoformat(alarm["end"] or alarm["last_seen"]))
            observed = max(0, min(alarm["duration"], (right - left).total_seconds()))
            duration += observed
            month = datetime.fromisoformat(alarm["start"]).astimezone(local_zone).month
            season = "hiver" if month in (12, 1, 2) else "printemps" if month < 6 else "ete" if month < 9 else "automne"
            by_season[season] += observed
    result.update(source=source, station=station, start=start, end=end,
                  temperature_alarm_seconds=duration, temperature_alarm_seconds_by_season=by_season,
                  alarms_count=len(alarms))
    return result
