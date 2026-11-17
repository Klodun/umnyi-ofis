"""Print the office metrics collected by Prometheus (MON-01)."""
import json
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:9090/api/v1/query"
NAMES = [
    "up",
    "office_temperature_celsius",
    "office_humidity_percent",
    "office_fan_on",
    "office_control_mode_auto",
    "office_sensor_last_reading_timestamp_seconds",
    "office_sensor_age_seconds",
]


def query(expr):
    url = BASE + "?query=" + urllib.parse.quote(expr)
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.load(resp)["data"]["result"]


for name in NAMES:
    rows = query(name)
    if not rows:
        print(f"{name}: нет данных")
        continue
    for row in rows:
        label = row["metric"].get("sensor_id") or row["metric"].get("actuator_id") or row["metric"].get("job", "")
        print(f"{name}{{id={label}}} = {row['value'][1]}")
