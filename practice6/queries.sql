-- Запросы проверки базы telemetry.sqlite3 (ПР №6, используются в ПР №8).
-- Выполнять на DB-01:
--   sudo sqlite3 /root/practice6/data/telemetry.sqlite3 ".timeout 5000" ".read /root/queries.sql"
-- Перед просмотром удобно включить вывод:
--   .headers on
--   .mode column
-- Важно: сервис хранилища пишет в базу каждые 5 секунд, поэтому тяжёлые запросы
-- (особенно с оконными функциями) могут кратковременно блокировать запись.
-- Если сервис начал отвечать 503 «database is locked», перезапустите его:
--   cd /root/practice6 && sudo docker compose restart storage

-- 1. Структура таблиц
SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name IN ('measurements', 'actuator_events');

-- 2. Сколько всего записей
SELECT 'measurements' AS table_name, COUNT(*) AS rows FROM measurements
UNION ALL
SELECT 'actuator_events', COUNT(*) FROM actuator_events;

-- 3. Последние 10 показаний с расшифровкой времени
SELECT id, device_id, metric, value, unit,
       datetime(timestamp / 1000, 'unixepoch', '+3 hours') AS measured_at
FROM measurements
ORDER BY id DESC
LIMIT 10;

-- 4. Последние переключения вентилятора
SELECT id, device_id, state, mode,
       datetime(timestamp / 1000, 'unixepoch', '+3 hours') AS switched_at
FROM actuator_events
ORDER BY id DESC
LIMIT 10;

-- 5. Показания по каждому датчику: количество, минимум, максимум, среднее
SELECT device_id,
       COUNT(*) AS readings,
       MIN(value) AS min_value,
       MAX(value) AS max_value,
       ROUND(AVG(value), 2) AS avg_value,
       unit
FROM measurements
GROUP BY device_id, unit;

-- 6. Показания за последние 10 минут
SELECT device_id, value, unit,
       datetime(timestamp / 1000, 'unixepoch', '+3 hours') AS measured_at
FROM measurements
WHERE timestamp > (strftime('%s', 'now') - 600) * 1000
ORDER BY id DESC
LIMIT 20;

-- 7. Средний интервал между показаниями одного датчика, секунды
SELECT device_id,
       ROUND(AVG(delta) / 1000.0, 1) AS avg_interval_seconds,
       COUNT(*) AS intervals
FROM (
  SELECT device_id,
         timestamp - LAG(timestamp) OVER (PARTITION BY device_id ORDER BY id) AS delta
  FROM measurements
)
WHERE delta IS NOT NULL
GROUP BY device_id;

-- 8. Сколько раз вентилятор включался и выключался
SELECT state, COUNT(*) AS times
FROM actuator_events
GROUP BY state;
