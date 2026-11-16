#!/usr/bin/env bash
# ПР №4/№6: показать последние показания приёмника на CTRL-01 в виде таблицы.
# Использование:  sudo ./view.sh [N]      (N — сколько последних строк взять, по умолчанию 20)
set -uo pipefail
cd "$(dirname "$0")" || exit 1
N="${1:-20}"
docker compose logs --no-color --tail="$N" receiver | python3 -c '
import json, sys
rows = []
for line in sys.stdin:
    i = line.find("{")
    if i < 0:
        continue
    try:
        d = json.loads(line[i:])
    except Exception:
        continue
    name = d.get("sensor_id") or d.get("actuator_id") or "?"
    val = d.get("value")
    if val is None:
        val = d.get("state", "")
    unit = d.get("unit", "")
    t = d.get("received_at", "")[11:19]
    rows.append((t, name, str(val) + unit))
print("%-10s %-9s %s" % ("время UTC", "датчик", "значение"))
print("-" * 34)
for t, name, v in rows:
    print("%-10s %-9s %s" % (t, name, v))
'
