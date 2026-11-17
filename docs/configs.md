# Конфигурации узлов стенда

Снято с работающих ВМ (вывод `ip -br a`, `ip r`, `ipconfig`, `docker compose ps`).

## WIN-01 — рабочее место (Windows Server 2019)

```
Адаптер Ethernet: 192.168.30.10, маска 255.255.255.192 (/26), шлюз 192.168.30.1 (VLAN 30)
Учётная запись: Administrator
```

## CTRL-01 — сервер приложений (РЕД ОС 8)

```
enp2s0  UP  192.168.40.10/26      шлюз 192.168.40.1 (VLAN 40)
default via 192.168.40.1 dev enp2s0 proto static metric 100
192.168.40.0/26 dev enp2s0 proto kernel scope link src 192.168.40.10 metric 100
```

Сервисы: `docker`, `sshd`. Каталоги: `/root/nginx-test` (ПР №3), `/root/practice4/ctrl` (ПР №4/№6).
Приёмник показаний: `ctrl-receiver-1` (`node:22-alpine`), `0.0.0.0:8080->8080/tcp`,
`GET /health` → `HTTP/1.1 200 OK`, `{"status":"ok","version":2,…}`.

## MON-01 — мониторинг (РЕД ОС 8)

```
enp2s0  UP  192.168.40.11/26      шлюз 192.168.40.1 (VLAN 40)
default via 192.168.40.1 dev enp2s0 proto static metric 100
192.168.40.0/26 dev enp2s0 proto kernel scope link src 192.168.40.11 metric 100
```

## DB-01 — сервер БД (РЕД ОС 8)

```
enp2s0  UP  192.168.40.12/26      шлюз 192.168.40.1 (VLAN 40)
default via 192.168.40.1 dev enp2s0 proto static metric 100
192.168.40.0/26 dev enp2s0 proto kernel scope link src 192.168.40.12 metric 100
```

Сервисы: `docker`, `sshd`, `sqlite3 3.40.0`. Хранилище ПР №6: `/root/practice6`,
контейнер `practice6-storage-1` (`python:3.13-alpine`), `0.0.0.0:8081->8081/tcp`.

## IOT-01 — узел IoT / Node-RED (РЕД ОС 8)

```
enp2s0  UP  192.168.50.10/26      шлюз 192.168.50.1 (VLAN 50)
default via 192.168.50.1 dev enp2s0 proto static metric 100
192.168.50.0/26 dev enp2s0 proto kernel scope link src 192.168.50.10 metric 100
```

Node-RED 4.0.9: контейнер `nodered` (`nodered/node-red:4.0`), `0.0.0.0:1880->1880/tcp`,
каталог `/root/practice4/iot`. Поток «Умный офис»: ручные `inject` температуры и влажности
(повтор 5 с) → `change` → POST на CTRL-01 (`:8080`) и DB-01 (`:8081`); температура
дополнительно идёт в `switch` с порогом 30 °C.

## REDOS8-5 — маршрутизатор стенда (эмуляция Cisco RTR)

```
ens1              UP   10.31.3.191/16      (внешний сегмент Cloud1, NAT)
enp2s0.30@enp2s0  UP   192.168.30.1/26     (шлюз VLAN 30)
enp2s0.40@enp2s0  UP   192.168.40.1/26     (шлюз VLAN 40)
enp2s0.50@enp2s0  UP   192.168.50.1/26     (шлюз VLAN 50)

default via 10.31.0.1 dev ens1 proto dhcp src 10.31.3.191 metric 101
192.168.30.0/26 dev enp2s0.30 proto kernel scope link src 192.168.30.1 metric 403
192.168.40.0/26 dev enp2s0.40 proto kernel scope link src 192.168.40.1 metric 404
192.168.50.0/26 dev enp2s0.50 proto kernel scope link src 192.168.50.1 metric 405
```

NAT и маршрутизация (`/usr/local/sbin/lab-router.sh`, служба `lab-router.service`):

```bash
sysctl -w net.ipv4.ip_forward=1
iptables -t nat -A POSTROUTING -o ens1 -j MASQUERADE
iptables -A FORWARD -i enp2s0 -o ens1 -j ACCEPT
iptables -A FORWARD -i ens1 -o enp2s0 -j ACCEPT
iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1300
```

## Switch1 — коммутатор доступа (GNS3 Ethernet switch)

Встроенный Ethernet switch GNS3 3.0.6: консоли и CLI нет, VLAN задаются в свойствах узла
(`ports_mapping`). Каждый порт — access в своём VLAN, порт к маршрутизатору — trunk (dot1q).

```
Ethernet0   dot1q    VLAN 1    trunk к REDOS8-5 (ethertype 0x8100)
Ethernet1   access   VLAN 30   WIN
Ethernet2   access   VLAN 40   CTRL
Ethernet3   access   VLAN 40   MON
Ethernet4   access   VLAN 40   DB
Ethernet5   access   VLAN 50   IOT
Ethernet6-7 access   VLAN 1    свободны
```

Связи: `WIN:eth0↔E1`, `CTRL:eth0↔E2`, `MON:eth0↔E3`, `DB:eth0↔E4`, `IOT:eth0↔E5`,
`REDOS8-5:eth0↔E0`.

VLAN 99 (управление) в этой сборке не используется: у встроенного коммутатора нет IP-адреса
управления, поэтому подсеть 192.168.99.0/26 осталась только в плане адресации.
