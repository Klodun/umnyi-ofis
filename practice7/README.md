# Практическая работа №7. Мониторинг в Prometheus и Grafana

## Что требовалось

Поднять на MON-01 Prometheus и Grafana как системные службы (без Docker), собрать метрики
приложения CTRL-01 по `/metrics`, показать готовую панель преподавателя, настроить
оповещение о пропаже показаний датчика и отдельно — о недоступности самого CTRL-01.

## Что сделано

| Шаг задания | Чем подтверждается |
|---|---|
| Prometheus и Grafana установлены как службы, добавлены в автозагрузку | `evidence7/12-services.txt`, скриншоты Grafana и Prometheus |
| Приёмник CTRL обновлён выданным `receiver.js`, старая отправка работает | `practice4/ctrl/receiver.js`, `evidence7/13-metrics-endpoint.txt` |
| `prometheus.yml` написан самостоятельно | `practice7/prometheus.yml`, проверка `promtool` — `evidence7/10-promtool.txt` |
| `prometheus.service` установлен, путь/пользователь/права проверены | `practice7/prometheus.service`, `evidence7/11-unit-check.txt` |
| Цель `office-controller` в состоянии UP, метрики собираются | `evidence7/02-prometheus-targets.png`, `evidence7/14-metrics-collected.txt` |
| Источник данных с UID `prometheus-office`, панель импортирована | `practice7/datasource.yml`, `practice7/dashboard-export.json` |
| Показания TEMP-01, HUM-01, FAN-01, режим AUTO, возраст данных видны | `evidence7/01-grafana-dashboard.png`, `03-grafana-charts.png` |
| Правила оповещения для каждого датчика, проверка 10 с, Pending 0 | `practice7/rules.yml`, `practice7/alert-rules-export.json` |
| SMTP и контакт Email привязаны к правилу, письмо доставлено | `practice7/contactpoints.yml`, `practice7/policies.yml`, `evidence7/22-alert-mail.txt` |
| Остановка только TEMP-01: цель UP, возраст растёт, HUM идёт, алерт горит | `evidence7/15-temp-alert-firing.txt`, `05-grafana-alerts-firing.png` |
| Возврат TEMP-01 в норму | `evidence7/16-temp-normal.txt` |
| Самостоятельная проверка HUM-01 | `evidence7/17-hum-alert-firing.txt` |
| Остановка CTRL-01: DOWN, значения датчиков не выдаются за текущие | `evidence7/18-ctrl-down.txt` |
| Восстановление CTRL-01 | `evidence7/19-ctrl-recovered.txt` |

## Файлы

| Файл | Что это |
|---|---|
| `prometheus.yml` | конфигурация Prometheus: задача `office-controller`, CTRL:8080, `/metrics`, сбор каждые 5 с, таймаут 4 с |
| `prometheus.service` | установленный модуль systemd (путь к программе, служебный пользователь, каталог данных) |
| `datasource.yml` | провижининг источника Grafana с UID `prometheus-office` |
| `rules.yml` | три правила оповещения (TEMP-01, HUM-01, CTRL-01) в виде провижининга |
| `contactpoints.yml`, `policies.yml` | контакт Email и политика, которая привязывает его к правилам |
| `grafana-smtp.conf` | drop-in для `grafana-server.service` с настройками SMTP |
| `dashboard-export.json` | экспорт панели из Grafana после импорта |
| `alert-rules-export.json`, `contact-points-export.json` | экспорт правил и контактов из Grafana |
| `set_sensor.py` | меняет значение ручного датчика в Node-RED через Admin API |
| `metrics_report.py` | печатает собранные метрики из Prometheus |

## Почему сделано именно так

**Службы, а не Docker.** Задание прямо запрещает Docker Compose для мониторинга. В репозитории
РЕД ОС 8 Prometheus лежит в пакете `golang-github-prometheus` (2.49.1, вместе с `promtool`),
Grafana — в пакете `grafana` (10.3.3). Оба пакета создают пользователей `prometheus` и `grafana`,
каталоги `/var/lib/prometheus` и `/var/lib/grafana` и модули systemd. Автозагрузка включается
`systemctl enable`.

**Интервал 5 с и таймаут 4 с.** Задание требует интервал сбора 5 секунд и таймаут меньше
интервала. Если таймаут равен интервалу, опросы начинают накладываться друг на друга,
и Prometheus отбрасывает часть сборов. 4 с оставляет запас на ответ.

**Правила оповещения считают возраст, а не сравнивают его в запросе.** Запрос
`office_sensor_age_seconds{...} > 20` при нормальной работе возвращает пустой вектор, и Grafana
показывает не «норма», а «нет данных» — тогда пропажу датчика не отличить от пропажи CTRL.
Поэтому запрос отдаёт само значение возраста, а порог `> 20` задан отдельным узлом Threshold.
Условие `and on(job, instance) (up == 1)` оставляет правило живым только пока CTRL отвечает:
если CTRL упал, правило уходит в NoData, а срабатывает отдельное правило `up < 1`.

**Pending 0 секунд.** В правилах стоит `for: 0s`: как только возраст превысил 20 с, правило
сразу переходит в Alerting, без выдержки. Проверка группы — каждые 10 с (`interval: 10s`).

**SMTP через drop-in.** `grafana.ini` — большой файл с комментариями, и правка его целиком
рискует сломать чужие настройки. Настройки SMTP заданы переменными окружения в
`/etc/systemd/system/grafana-server.service.d/smtp.conf`, которые Grafana читает как `GF_SMTP_*`.
`GF_SMTP_SKIP_VERIFY=true` нужен потому, что postfix на MON-01 отдаёт самоподписанный
сертификат: без этой опции Grafana падает с ошибкой
`x509: certificate is not valid for any names` (см. `evidence7/20-smtp-error.txt`).
Письма складываются в локальный ящик `grafana-alerts@MON-01.localdomain`, поэтому доставку
видно целиком, без внешней почты. Паролей в репозитории нет.

**Почему FAN-01 и режим иногда показывают NaN.** Узел `rbe` в Node-RED отправляет состояние
вентилятора только при изменении. Если перезапустить приёмник CTRL, он теряет последнее
состояние и ждёт следующего события. Достаточно один раз пересечь порог 30 °C, чтобы метрики
`office_fan_on` и `office_control_mode_auto` снова появились. Это не ошибка настройки,
а следствие фильтра «только при изменении».

## Метрики приёмника

| Метрика | Смысл |
|---|---|
| `office_temperature_celsius{sensor_id="TEMP-01"}` | последняя принятая температура серверной |
| `office_humidity_percent{sensor_id="HUM-01"}` | последняя принятая влажность рабочей зоны |
| `office_fan_on{actuator_id="FAN-01"}` | 1 — вентилятор включён, 0 — выключен |
| `office_control_mode_auto{actuator_id="FAN-01"}` | 1 — автоматический режим |
| `office_sensor_last_reading_timestamp_seconds` | время показания по часам датчика |
| `office_sensor_has_reading` | было ли показание после запуска приёмника |
| `office_sensor_age_seconds` | сколько секунд назад приёмник получил показание |
| `up{job="office-controller"}` | отвечает ли CTRL на опрос Prometheus |

## Как повторить

```bash
# 1. Установка на MON-01
sudo dnf install -y golang-github-prometheus grafana grafana-selinux

# 2. Конфигурация и службы
sudo install -o root -g root -m 0644 prometheus.yml /etc/prometheus/prometheus.yml
promtool check config /etc/prometheus/prometheus.yml
sudo systemctl enable --now prometheus grafana-server

# 3. Источник данных и правила Grafana
sudo install -d -o grafana -g grafana /etc/grafana/provisioning/alerting
sudo install -o grafana -g grafana -m 0644 datasource.yml  /etc/grafana/provisioning/datasources/prometheus-office.yml
sudo install -o grafana -g grafana -m 0644 rules.yml       /etc/grafana/provisioning/alerting/rules.yml
sudo install -o grafana -g grafana -m 0644 contactpoints.yml /etc/grafana/provisioning/alerting/contactpoints.yml
sudo install -o grafana -g grafana -m 0644 policies.yml    /etc/grafana/provisioning/alerting/policies.yml
sudo install -d /etc/systemd/system/grafana-server.service.d
sudo install -o root -g root -m 0644 grafana-smtp.conf /etc/systemd/system/grafana-server.service.d/smtp.conf
sudo systemctl daemon-reload && sudo systemctl restart grafana-server

# 4. Проверка
curl -s http://127.0.0.1:9090/api/v1/targets | head
python3 metrics_report.py
```

Панель открывается по адресу `http://192.168.40.11:3000/d/office-controller-lab/`,
Prometheus — `http://192.168.40.11:9090/targets`.

## Замечания

- Имя задачи, адрес и порт цели, интервал и таймаут заданы в `prometheus.yml` вручную,
  готовый файл не копировался.
- Панель `dashboard_teacher.json` не содержит правил оповещения — правила лежат отдельно,
  в `rules.yml` и `alert-rules-export.json`.
- Значения датчиков задаются вручную в Node-RED: `set_sensor.py inj_temp 38 5` или
  `set_sensor.py inj_hum 45 5`; пустой третий аргумент останавливает периодическую отправку.
