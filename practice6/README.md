# ПР №6. Интеграция базы данных SQLite

Работа продолжает ПР №4 и №5: то, что раньше уходило только на приёмник CTRL-01, теперь
**параллельно** сохраняется в базу данных SQLite на DB-01. Приёмник CTRL-01 остаётся — он
по-прежнему отвечает `{"status":"ok",…}`, но историю показаний и состояний вентилятора хранит
уже отдельный сервис хранения.

## Что дано в раздаточных материалах

Папка `Файлы задание 6` — четыре файла, все кладутся в **одну** папку на ВМ DB-01:

| Файл | Что это | Зачем |
|---|---|---|
| `compose.yml` | Docker Compose сервиса хранения | запускает `server.py` в контейнере, публикует порт 8081, монтирует `./data` |
| `server.py` | HTTP-сервер хранения на стандартной библиотеке Python | принимает POST-запросы и пишет их в SQLite; отдаёт веб-страницу, сводку, историю, CSV, резервную копию |
| `index.html` | веб-интерфейс «История показаний» | то, что видит преподаватель в браузере на `http://192.168.40.12:8081/` |
| `inspect_db.py` | маленький скрипт проверки | печатает количество строк и последние 5 записей из обеих таблиц |

`server.py` — **не** генератор базы. В нём прямо написано:

```python
# Expected contract only. No CREATE TABLE, migrations, or automatic file creation.
```

То есть база и таблицы создаются **вручную**, до первого запуска контейнера. Если файла базы нет,
сервис падает с ошибкой `Database file missing: create data/telemetry.sqlite3 manually with sqlite3
BEFORE starting storage`. Это сделано специально: в учебной работе важно показать, что студент
умеет проектировать схему, а не что сервис сам себе всё нарисовал.

## Зачем вообще база, если есть приёмник

Приёмник CTRL-01 пишет в журнал Docker (`docker compose logs`). Журнал — плохое хранилище истории:

* он ротируется и теряется при пересоздании контейнера;
* по нему нельзя построить выборку «средняя температура за час»;
* два разных процесса (показания датчиков и состояния вентилятора) лежат вперемешку в тексте.

SQLite даёт структурированную таблицу, индексы, SQL-выборки, выгрузку в CSV и резервную копию
файла. Поэтому в ПР №6 данные идут в два места сразу: приёмник подтверждает приём «здесь и сейчас»,
база накапливает историю.

## Шаг 1. Установить sqlite3 на DB-01

Без CLI нельзя ни создать базу, ни показать `.schema`, ни выполнить запросы в отчёте.

```bash
sudo dnf install -y sqlite
sqlite3 --version
```

В лабораторной сети репозиторий колледжа `kkrepo.petrocollege.ru` не резолвился через DNS
(внутренний адрес `10.31.0.9`). Лечится записью в `/etc/hosts`:

```bash
echo '10.31.0.9 kkrepo.petrocollege.ru' | sudo tee -a /etc/hosts
sudo dnf clean all && sudo dnf install -y sqlite
```

Пакеты Rocky Linux 8 для этого не подходят: РЕД ОС 8 собрана на glibc 2.36 и readline 8.1,
а Rocky 8 — на glibc 2.28 и readline 7, поэтому `dnf` честно отказывается ставить чужой пакет
(`requires libreadline.so.7`). Нужен именно репозиторий RedOS.

## Шаг 2. Создать базу и таблицы вручную

Файл базы должен называться ровно `telemetry.sqlite3` и лежать в подпапке `data` — это задано
в `compose.yml` (`DB_PATH=/data/telemetry.sqlite3`, монтируется `./data:/data`).

```bash
mkdir -p /root/practice6/data
cd /root/practice6
sqlite3 data/telemetry.sqlite3 < schema.sql
sqlite3 data/telemetry.sqlite3 ".tables"
```

Схема (`schema.sql`) повторяет контракт из `server.py` — словарь `EXPECTED`. Две таблицы:

```sql
CREATE TABLE measurements (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  device_id TEXT NOT NULL,
  metric TEXT NOT NULL,
  zone TEXT NOT NULL,
  timestamp INTEGER NOT NULL,
  received_at INTEGER NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL,
  labels TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE actuator_events (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  device_id TEXT NOT NULL,
  zone TEXT NOT NULL,
  timestamp INTEGER NOT NULL,
  received_at INTEGER NOT NULL,
  state TEXT NOT NULL,
  mode TEXT NOT NULL
);
```

Почему именно так:

* **`measurements`** — числовые показания. `metric` отделяет температуру от влажности, `zone` —
  зону офиса, `unit` — единицу измерения. `labels` — запас под произвольные метки в JSON
  (в ПР №6 не используется, но `server.py` требует `DEFAULT '{}'`).
* **`actuator_events`** — не значения, а **события** исполнительных устройств: `state` (`ON`/`OFF`)
  и `mode` (`auto`/`manual`). Событие — это факт «в момент времени T вентилятор перешёл в
  состояние S», поэтому отдельная таблица, а не строка в `measurements`.
* **`timestamp`** — время измерения, приходит от источника (Node-RED), в миллисекундах Unix.
  **`received_at`** — время приёма на сервере. Разница между ними показывает задержку доставки,
  а `timestamp` позволяет восстановить хронологию, даже если запросы пришли не по порядку.
* **`id INTEGER PRIMARY KEY`** — автоинкремент SQLite (алиас `rowid`), удобно для `ORDER BY id DESC`.

Проверка структуры:

```bash
sqlite3 data/telemetry.sqlite3 "PRAGMA table_info(measurements);"
```

`server.py` при старте сверяет `PRAGMA table_info` с `EXPECTED` и падает, если имена, типы,
`NOT NULL` или `PRIMARY KEY` не совпали. Порядок колонок при этом не важен — сравнение идёт
по множеству.

## Шаг 3. Запустить сервис хранения

```bash
cd /root/practice6
docker compose up -d
docker compose ps
curl -s http://127.0.0.1:8081/health
```

Ожидаемый ответ: `{"status": "ok", "storage": "sqlite", "version": 2}`.

Разбор `compose.yml`:

| Строка | Зачем |
|---|---|
| `image: python:3.13-alpine` | серверу нужен только Python, отдельный образ собирать не надо |
| `command: ["python","-u","server.py"]` | `-u` — без буферизации, логи видны сразу |
| `DB_PATH: /data/telemetry.sqlite3` | путь внутри контейнера, совпадает с ожиданием `server.py` |
| `ports: "8081:8081"` | 8080 занят приёмником CTRL-01 и Nginx из ПР №3, поэтому 8081 |
| `./server.py:/app/server.py:ro,Z` | файлы монтируются только на чтение; `Z` — метка SELinux |
| `./data:/data:Z` | папка с базой — единственное место, куда контейнер пишет |
| `restart: unless-stopped` | сервис поднимается после перезагрузки ВМ |
| `healthcheck` | `docker compose ps` показывает `(healthy)`, а не просто `Up` |

## Шаг 4. Научить Node-RED отправлять данные в два места

Node-RED на IOT-01 уже умеет отправлять показания на CTRL-01 (ПР №4) и состояние вентилятора
на CTRL-01 (ПР №5). Теперь от каждого узла `change` идёт **два** провода: старый `http request`
на `http://192.168.40.10:8080/...` и новый — на `http://192.168.40.12:8081/...`.

Вся схема собрана на **одной** вкладке «Умный офис», чтобы было видно всю цепочку сразу:

```
inject «Температура, °C» (ручной ввод)
   ├─ change «TEMP-01: показание» → POST /api/readings  → CTRL-01
   │                             └→ POST /api/readings (БД) → DB-01
   └─ switch «Температура > 30 °C»
         ├─ ON  → POST /api/actuators  → CTRL-01 и БД
         └─ OFF → POST /api/actuators  → CTRL-01 и БД

inject «HUM-01 каждые 5 с» (влажность, автоматически)
   └─ change «HUM-01: показание» → POST /api/readings → CTRL-01 и БД
```

**Температуру задаёшь ты сам**, случайных значений нет: двойной клик по узлу
«Температура, °C» → вписать число → **Done** → **Deploy** → клик по квадратику слева от узла.
Одно нажатие даёт сразу два эффекта: показание TEMP-01 сохраняется в базу и в приёмник,
а `switch` тут же решает, включать вентилятор или нет. Влажность HUM-01 остаётся
автоматической (каждые 5 секунд), чтобы в базе был непрерывный поток для графика.

Почему это работает без пересборки объекта: формат тела запроса у приёмника и у хранилища
**одинаковый** — `{"sensor_id","zone","value","unit","timestamp"}` для показаний и
`{"actuator_id","zone","state","mode","timestamp"}` для событий. Один и тот же `msg.payload`
годится обоим адресатам, поэтому второй `http request` просто подключается к тому же выходу
`change`-узла.

## Шаг 5. Проверка

```bash
# 1. Сервис жив и здоров
curl -s http://127.0.0.1:8081/health

# 2. Счётчики строк
sqlite3 data/telemetry.sqlite3 \
  "SELECT COUNT(*) FROM measurements; SELECT COUNT(*) FROM actuator_events;"

# 3. Последние показания
sqlite3 -header -column data/telemetry.sqlite3 \
  "SELECT id,device_id,value,unit,datetime(timestamp/1000,'unixepoch') AS ts
     FROM measurements ORDER BY id DESC LIMIT 5;"

# 4. Последние события вентилятора
sqlite3 -header -column data/telemetry.sqlite3 \
  "SELECT id,device_id,state,mode,datetime(timestamp/1000,'unixepoch') AS ts
     FROM actuator_events ORDER BY id DESC LIMIT 5;"

# 5. Скрипт из раздаточных материалов
DB_PATH=/root/practice6/data/telemetry.sqlite3 python3 inspect_db.py
```

В браузере на WIN: `http://192.168.40.12:8081/` — страница «История показаний» с карточками
последних значений, фильтрами, графиком, кнопками «CSV» и «Копия SQLite».

## Что получилось (фактические результаты)

* `sqlite3 3.40.0` установлен на DB-01 из репозитория RedOS.
* База `data/telemetry.sqlite3` создана вручную, таблицы `measurements` и `actuator_events`
  совпадают с контрактом `server.py`.
* Контейнер `practice6-storage-1` — `Up (healthy)`, `GET /health` → `{"status":"ok","storage":"sqlite","version":2}`.
* Node-RED отправляет каждые 5 секунд влажность HUM-01 в оба адреса, а температуру TEMP-01 —
  по твоему ручному вводу. За время проверки в `measurements` накопилось больше 700 строк,
  в `actuator_events` — оба состояния: `OFF` при 25 °C и `ON` при 35 °C.
* Один клик по inject с температурой 35 °C дал одновременно: `measurements` id 778 (TEMP-01, 35.0),
  `actuator_events` id 9 (`ON`), ответы `{"status":"stored",…}` и от CTRL-01, и от БД-01.
* Веб-интерфейс на `http://192.168.40.12:8081/` открывается с WIN-01 и показывает те же цифры.

## Ошибки, на которые я наткнулся

| Симптом | Причина | Решение |
|---|---|---|
| `Database file missing: create data/telemetry.sqlite3 manually` | контейнер запустили до создания базы | создать базу `sqlite3 data/telemetry.sqlite3 < schema.sql` и перезапустить |
| `Wrong structure for measurements` | в схеме забыли `DEFAULT '{}'` у `labels` | добавить `labels TEXT NOT NULL DEFAULT '{}'` |
| `dnf install sqlite` — `Could not resolve host` | DNS не знает внутренний репозиторий | запись `10.31.0.9 kkrepo.petrocollege.ru` в `/etc/hosts` |
| `dnf` ставит Rocky-пакет и ругается на `libreadline.so.7` | РЕД ОС 8 не совместима с бинарными пакетами Rocky 8 | ставить только из репозитория RedOS |
| `{"error":"invalid_fields"}` / `sensor_id` | в теле нет `sensor_id`, `zone`, `unit` или `timestamp` | проверить, что узел `change` собирает все поля, а `timestamp` — типа `date` |
| Порт 8081 занят | на DB-01 уже что-то слушает | `ss -lntp \| grep 8081`, остановить лишнее |

## Файлы работы

```
practice6/compose.yml      — Docker Compose сервиса хранения (из раздаточных материалов)
practice6/server.py        — HTTP-сервер и запись в SQLite (из раздаточных материалов)
practice6/index.html       — веб-интерфейс «История показаний» (из раздаточных материалов)
practice6/inspect_db.py    — скрипт проверки содержимого БД (из раздаточных материалов)
practice6/schema.sql       — схема БД, создаётся вручную (моя работа)
practice6/README.md        — этот файл
evidence6/                 — доказательства: консольные проверки, SQL-выборки, скриншоты
```

Доказательства в `evidence6/`:

| Файл | Что показывает |
|---|---|
| `01-storage.txt` | `docker compose ps` (healthy), `/health`, `.tables`, `.schema`, версия sqlite3 |
| `03-sql.txt` | SQL-выборки: счётчики, средние по устройствам, последние события вентилятора |
| `04-manual-temp-sql.txt` | SQL после ручного ввода: `TEMP-01 25.0` → `OFF`, `TEMP-01 35.0` → `ON` |
| `05-flow.png` | вкладка «Умный офис»: ручной ввод температуры, две ветки — показание и вентилятор, обе в CTRL и БД |
| `06-inject-dialog.png` | диалог узла «Температура, °C» — здесь вписывается своё число |
| `07-manual-35-on.png` | ручной ввод 35 °C: `TEMP-01 stored id 737`, `FAN-01 ON`, ответы и от CTRL, и от БД |
| `08-web-ui.png` | страница «История показаний» на `http://192.168.40.12:8081/` |
