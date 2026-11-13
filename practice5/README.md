# ПР №5. Эмуляция вентилятора в Node-RED

## Задача

Собрать в Node-RED вентилятор, который срабатывает по показаниям датчика температуры TEMP-01:
**температура больше 30 °C — вентилятор включается, приёмник получает сигнал ON; иначе — OFF.**
Для каждого состояния использовать **отдельный узел `change`**. Правила:

- `fan.state` — состояние (`ON` / `OFF`);
- `fan.actuator_id` — название (`FAN-01`);
- `fan.zone` — место (`server_room`);
- `fan.mode` — режим (`auto`).

## Приёмник v2

В работе используется приёмник из «Приемник для задания 5» — версия 2. Он принимает два вида
запросов (видно по `GET /health`):

```json
{"status":"ok","version":2,"endpoints":["/api/readings","/api/actuators"]}
```

`POST /api/actuators` ждёт тело:

```json
{"actuator_id":"FAN-01","zone":"server_room","state":"ON","mode":"auto","timestamp":1794575231832}
```

Проверки: `actuator_id` строго `FAN-01`, `zone` строго `server_room`, `state` только `ON` или `OFF`,
`mode` только `auto`, `timestamp` — корректное время (мс или строка с датой). При нарушении —
`400 {"error":"invalid_actuator_fields"}`.

## Поток в Node-RED

Вкладка **«Вентилятор FAN-01»** в том же Node-RED (файл `../practice4/iot/flows.json`).

```
inject «Температура, °C» (число)
        │
        ▼
switch (> 30 °C) ─┬─ ON  → change «Включить» ─┐
                  └─ OFF → change «Выключить» ─┴─► POST /api/actuators → debug
```

### Как вводить температуру

Всё на схеме, отдельной страницы нет:

1. Двойной клик по узлу **«Температура, °C»** (inject).
2. В поле `msg.payload` (тип **number**) вписать число, например `35`.
3. **Done**, затем **Deploy**.
4. Нажать квадратик слева от узла — показание уйдёт в `switch`.

Результат — в панели **debug** справа: «ВЕНТИЛЯТОР ВКЛЮЧЁН (ON)» при значении больше 30,
«ВЫКЛЮЧЕН (OFF)» при 30 и меньше.

Рандомной имитации в потоке нет: уходит ровно то число, которое вписали. Проверено на стенде —
`35` даёт `ON`, `25` даёт `OFF`.

### Узел switch

| Поле | Значение |
|---|---|
| Property | `payload` |
| Правило 1 | `>` `30` (число) → выход 1 |
| Правило 2 | `otherwise` → выход 2 |

> **Важно.** В Node-RED «иначе» — это не просто второй выход, а отдельное правило типа `else`
> в списке правил. Если оставить одно правило и два выхода, второй выход не сработает никогда
> (проверено на стенде: приходили только `ON`).

### Узлы change (по одному на состояние)

| Правило | ON | OFF |
|---|---|---|
| 1 | `fan.state` = `ON` | `fan.state` = `OFF` |
| 2 | `fan.actuator_id` = `FAN-01` | `fan.actuator_id` = `FAN-01` |
| 3 | `fan.zone` = `server_room` | `fan.zone` = `server_room` |
| 4 | `fan.mode` = `auto` | `fan.mode` = `auto` |
| 5 | `fan.timestamp` = `$millis()` (JSONata) | `fan.timestamp` = `$millis()` |
| 6 | `msg.payload` = `msg.fan` | `msg.payload` = `msg.fan` |
| 7 | `msg.headers` = `{"Content-Type":"application/json"}` | то же |

### Отправка

Узел `http request`: метод `POST`, URL `http://192.168.40.10:8080/api/actuators`,
Return — `a parsed JSON object`.

## Проверка

Состояние видно в двух местах:

1. **Панель debug в редакторе** (значок жука) — строки «ВЕНТИЛЯТОР ВКЛЮЧЁН (ON)» /
   «ВЫКЛЮЧЕН (OFF)», их формирует правило `msg.human`.
2. **Под узлом** «состояние вентилятора» — та же подпись.

На CTRL-01:

```bash
cd /root/practice4/ctrl
curl -i http://127.0.0.1:8080/health
docker compose logs --tail=20 receiver
```

В журнале приёмника появляются строки обоих видов:

```json
{"received_at":"…","state":"ON","actuator_id":"FAN-01","zone":"server_room","mode":"auto","timestamp":1794575231832}
{"received_at":"…","state":"OFF","actuator_id":"FAN-01","zone":"server_room","mode":"auto","timestamp":1794575216831}
```

Ответ приёмника: `{"status":"ok","actuator_id":"FAN-01","state":"ON","mode":"auto"}`.

## Доказательства

| Файл | Что внутри |
|---|---|
| `evidence5/01-health.txt` | `GET /health` — приёмник v2, оба эндпоинта |
| `evidence5/02-actuator-log.txt` | журнал приёмника: переходы `ON` → `OFF` → `ON` |
| `evidence5/03-flow.png` | схема в редакторе: inject «Температура, °C» → switch → change → POST |
