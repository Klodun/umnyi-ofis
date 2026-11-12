# ПР №4. Виртуальные датчики в Node-RED

## Что нужно было сделать

Подготовить среду для эмуляции датчиков: на CTRL-01 поднять приёмник показаний,
на IOT-01 — Node-RED, создать в нём два виртуальных датчика (температура и влажность),
которые каждые 5 секунд сами отправляют показания на приёмник.

| Требование | Где выполнено |
|---|---|
| Приёмник из раздаточных материалов установлен на CTRL через Docker Compose | `ctrl/compose.yml`, `ctrl/receiver.js` |
| Node-RED поднят на IOT через Docker Compose и открывается с WIN | `iot/compose.yml`, `http://192.168.50.10:1880` |
| В Node-RED два готовых виртуальных датчика: температура и влажность | `iot/flows.json` |
| Датчики сами отправляют показание каждые 5 секунд, CTRL его пишет | `evidence4/02-receiver-log.txt` |

## Как устроено

```
WIN-01 (браузер)                    IOT-01                     CTRL-01
192.168.30.10/26               192.168.50.10/26            192.168.40.10/26
       │                              │                          │
       └──── http://…:1880 ──────────►│ Node-RED 4.0 (Docker)    │
                                      │ inject (5 c) → change →  │
                                      │ http request POST ───────┼──► приёмник :8080
                                      │                          │    (node:22-alpine)
```

Датчики:

| Датчик | sensor_id | zone | unit | Значение |
|---|---|---|---|---|
| Температура (серверная) | `TEMP-01` | `server_room` | `C` | 18…26 °C |
| Влажность (рабочая зона) | `HUM-01` | `work_area` | `%` | 35…60 % |

Приёмник принимает только эти пары `sensor_id` + `zone` + `unit`, значение обязано быть
числом, а `timestamp` — числом миллисекунд или строкой, которую понимает `Date.parse`.
Нарушение любого поля даёт `400 {"error":"invalid_fields"}`.

## Запуск на CTRL-01

В раздаточных материалах файл называется `receiver.yml`; здесь он лежит как `compose.yml` —
это тот же compose-файл, `docker compose` подхватывает его без `-f`. Содержимое совпадает
с тем, что реально запущено на CTRL-01.

```bash
cd ~/practice4/ctrl          # файлы этой папки: compose.yml и receiver.js
docker compose up -d
docker compose ps
curl -i --connect-timeout 10 http://127.0.0.1:8080/health

# журнал показаний
docker compose logs -f --tail=20 receiver
```

Приёмник слушает `0.0.0.0:8080`, поэтому он доступен из VLAN 50 по адресу `192.168.40.10:8080`.

## Запуск на IOT-01

```bash
cd ~/practice4/iot           # файлы этой папки: compose.yml и flows.json
mkdir -p data
cp flows.json data/flows.json
chown -R 1000:1000 data      # в контейнере Node-RED работает uid 1000
docker compose up -d
docker compose ps
curl -I http://127.0.0.1:1880/
```

Поток `data/flows.json` — две одинаковые цепочки: `inject → change → http request → debug`.

Узел `change` собирает показание из отдельных правил (как в редакторе «Правила»):

| Правило | Свойство | Значение |
|---|---|---|
| 1 | `msg.reading.value` | `msg.payload` |
| 2 | `msg.reading.sensor_id` | `TEMP-01` (для второго датчика — `HUM-01`) |
| 3 | `msg.reading.zone` | `server_room` (для второго — `work_area`) |
| 4 | `msg.reading.timestamp` | `msg.timestamp` |
| 5 | `msg.reading.unit` | `C` (для второго — `%`) |
| 6 | `msg.payload` | `msg.reading` |
| 7 | `msg.headers` | `{"Content-Type":"application/json"}` |

Значение и метку времени формирует `inject`:

* `msg.payload` — выражение JSONata `$round(18 + $random() * 8, 1)` (для влажности
  `$round(35 + $random() * 25, 1)`);
* `msg.timestamp` — свойство типа «timestamp» (в `flows.json` это `vt: "date"`), узел
  подставляет текущее время в миллисекундах (`Date.now()`).

> **Грабли.** `flows.json` здесь собран текстом, а не в редакторе. Если для свойства
> `msg.timestamp` написать `vt: "timestamp"`, узел молча ничего не подставит: такого типа
> в Node-RED нет, пункт «timestamp» редактор хранит как `date`. В сообщении окажется
> `msg.timestamp: ""`, `reading.timestamp` уйдёт пустым, и приёмник ответит
> `{"error":"invalid_fields"}`. Правильно — `vt: "date"`.

## Проверка

```bash
# на CTRL-01
curl -i http://127.0.0.1:8080/health
docker compose logs --no-color --tail=20 receiver

# на IOT-01
curl -i --connect-timeout 10 http://192.168.40.10:8080/health
curl -s http://127.0.0.1:1880/flows | head -c 300
```

С WIN-01 редактор открывается по адресу `http://192.168.50.10:1880`.

Журнал для отчёта (как в инструкции):

```bash
cd ~/practice4/ctrl
sudo docker compose -f compose.yml logs --no-color --tail=100 receiver > ~/practice4/receiver-log.txt
sudo docker compose -f compose.yml ps > ~/practice4/ctrl-containers.txt
```

## Доказательства

| Файл | Что внутри |
|---|---|
| `evidence4/01-ctrl-check.txt` | CTRL-01: адрес, версии Docker, `compose ps`, `/health`, доступность Node-RED с CTRL |
| `evidence4/02-receiver-log.txt` | 100 записей приёмника: оба датчика каждые 5 секунд |
| `evidence4/03-iot-check.txt` | IOT-01: адрес, версии, `compose ps`, ответ Node-RED, `POST`-проверка до CTRL |
| `evidence4/04-iot-containers.txt` | `docker compose ps` на IOT-01 |
| `evidence4/05-win-nodered-change.png` | редактор Node-RED, открытый на WIN-01: правила узла `change` |
| `evidence4/06-win-nodered-editor.png` | WIN-01: браузер с открытым редактором `http://192.168.50.10:1880`, видны обе цепочки датчиков |
