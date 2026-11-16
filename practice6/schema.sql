-- Схема БД telemetry.sqlite3 (ПР №6)
-- Создаётся вручную на DB-01 до запуска контейнера:
--   sqlite3 data/telemetry.sqlite3 < schema.sql

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
