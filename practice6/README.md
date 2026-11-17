# ПР №6. Интеграция базы данных SQLite

Работа продолжает ПР №4 и №5: то, что уходит на приёмник CTRL-01, теперь **параллельно**
сохраняется в базу SQLite на DB-01.

## Что дано

Четыре файла из раздаточных материалов, все — в одну папку на DB-01:

| Файл | Роль |
|---|---|
| `compose.yml` | запускает сервис хранения, порт 8081, монтирует `./data` |
| `server.py` | HTTP-сервер: принимает POST и пишет в SQLite |
| `index.html` | веб-интерфейс «История показаний» |
| `inspect_db.py` | проверка содержимого базы |

`server.py` **не создаёт базу**: в нём прямо написано `No CREATE TABLE, migrations, or automatic
file creation`. Он только проверяет, что файл есть и схема совпадает с ожидаемой, иначе падает
с `Database file missing`. Базу создаём вручную — это и есть суть работы.

## Шаг 1. Установить sqlite3

```bash
sudo dnf install -y sqlite && sqlite3 --version
```

Если репозиторий колледжа не резолвится — прописать адрес в hosts:

```bash
echo '10.31.0.9 kkrepo.petrocollege.ru' | sudo tee -a /etc/hosts
```

Пакеты Rocky 8 не подходят: РЕД ОС 8 собрана на glibc 2.36 и readline 8.1, Rocky 8 — на 2.28 и 7,
поэтому `dnf` отказывается (`requires libreadline.so.7`). Нужен репозиторий RedOS.

## Шаг 2. Создать базу по своей схеме

```bash
mkdir -p /root/practice6/data && cd /root/practice6
sqlite3 data/telemetry.sqlite3 < schema.sql
sqlite3 data/telemetry.sqlite3 ".tables"     # measurements, actuator_events
```

Схема (`schema.sql`) повторяет контракт `server.py`:

```sql
CREATE TABLE measurements (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL, device_id TEXT NOT NULL, metric TEXT NOT NULL,
  zone TEXT NOT NULL, timestamp INTEGER NOT NULL, received_at INTEGER NOT NULL,
  value REAL NOT NULL, unit TEXT NOT NULL,
  labels TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE actuator_events (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL, device_id TEXT NOT NULL, zone TEXT NOT NULL,
  timestamp INTEGER NOT NULL, received_at INTEGER NOT NULL,
  state TEXT NOT NULL, mode TEXT NOT NULL
);
```

* `measurements` — числовые показания: `metric` (температура/влажность), `zone`, `value`, `unit`.
* `actuator_events` — не значения, а события: `state` (`ON`/`OFF`) и `mode` (`auto`).
* `timestamp` — когда измерено (приходит от Node-RED), `received_at` — когда принято сервером.
* `labels` с `DEFAULT '{}'` — требование `server.py`, запас под произвольные метки.

## Шаг 3. Запустить сервис

```bash
cd /root/practice6 && docker compose up -d
docker compose ps
curl -s http://127.0.0.1:8081/health     # {"status":"ok","storage":"sqlite","version":2}
```

Порт 8081, а не 8080: 8080 занят приёмником CTRL-01 и Nginx из ПР №3. Файлы монтируются
только на чтение, запись идёт лишь в `./data`, `restart: unless-stopped` поднимает сервис
после перезагрузки ВМ.

## Шаг 4. Отправка из Node-RED в два места

Одна вкладка «Умный офис» на IOT-01:

```
inject «Температура, °C (повтор 5 с)» — ручной ввод
   ├─ change «TEMP-01: показание» → POST /api/readings → CTRL-01 и БД
   └─ switch «> 30 °C» → change ON/OFF → rbe «только при изменении» → POST /api/actuators → CTRL-01 и БД

inject «Влажность, % (повтор 5 с)» — ручной ввод
   └─ change «HUM-01: показание» → POST /api/readings → CTRL-01 и БД
```

Тело запроса у приёмника и хранилища одинаковое, поэтому второй `http request` просто
подключается к тому же выходу `change`-узла.

* **Повтор 5 секунд** — чтобы карточки на странице не «замерзали» на старом времени.
* **Узел `rbe`** — пропускает событие вентилятора только при смене `ON`/`OFF`, иначе
  в `actuator_events` каждые 5 секунд падали бы одинаковые `ON`.

## Проверка

```bash
curl -s http://127.0.0.1:8081/health

sqlite3 data/telemetry.sqlite3 "SELECT COUNT(*) FROM measurements; SELECT COUNT(*) FROM actuator_events;"
sqlite3 -header -column data/telemetry.sqlite3 \
  "SELECT id,device_id,value,unit,datetime(timestamp/1000,'unixepoch') AS ts
     FROM measurements ORDER BY id DESC LIMIT 5;"
sqlite3 -header -column data/telemetry.sqlite3 \
  "SELECT id,state,datetime(timestamp/1000,'unixepoch') AS ts
     FROM actuator_events ORDER BY id DESC LIMIT 5;"

DB_PATH=/root/practice6/data/telemetry.sqlite3 python3 inspect_db.py
```

В браузере на WIN: `http://192.168.40.12:8081/` — карточки последних значений, фильтры, график,
выгрузка CSV и копия базы.

## Результат

* `sqlite3 3.40.0`, база создана по `schema.sql`, схема совпадает с контрактом.
* Контейнер `practice6-storage-1` — `Up (healthy)`.
* В `measurements` больше 1100 показаний (`TEMP-01` и `HUM-01`), в `actuator_events` —
  только реальные переключения (`ON` при 35 °C, `OFF` при 29 °C).
* Страница `http://192.168.40.12:8081/` открывается с WIN-01 и показывает те же значения,
  что и журнал приёмника на CTRL-01.

## Ошибки, на которые я наткнулся

| Симптом | Причина | Решение |
|---|---|---|
| `Database file missing` | контейнер запустили до создания базы | создать базу и перезапустить |
| `Wrong structure for measurements` | нет `DEFAULT '{}'` у `labels` | добавить в схему |
| `Could not resolve host` при `dnf` | DNS не знает внутренний репозиторий | запись в `/etc/hosts` |
| `requires libreadline.so.7` | пакет Rocky 8 на РЕД ОС 8 | ставить только из репозитория RedOS |
| `{"error":"invalid_fields"}` | в теле нет `sensor_id`, `zone`, `unit` или `timestamp` | проверить правила узла `change` |

## Файлы

```
practice6/compose.yml     — Compose сервиса хранения (из раздаточных материалов)
practice6/server.py       — HTTP-сервер и запись в SQLite (из раздаточных материалов)
practice6/index.html      — веб-интерфейс (из раздаточных материалов)
practice6/inspect_db.py   — проверка содержимого базы (из раздаточных материалов)
practice6/schema.sql      — схема БД, создаётся вручную
```

Доказательства в `evidence6/`:

| Файл | Что показывает |
|---|---|
| `01-storage.txt` | `compose ps` (healthy), `/health`, `.tables`, `.schema`, версия sqlite3 |
| `03-sql.txt` | SQL-выборки: счётчики, средние по устройствам, последние события |
| `04-manual-temp-sql.txt` | ручные значения: `TEMP-01 35.0` каждые 5 секунд, событий вентилятора всего 12 |
| `05-flow.png` | вкладка «Умный офис»: ручной ввод, ветка показания и ветка вентилятора с `rbe` |
| `08-web-ui.png` | страница «История показаний» с живыми значениями |
| `10-ctrl-view.txt` | вывод `view.sh` на CTRL-01: таблица «время — датчик — значение» |
