Единый агент внешнего мониторинга сбоев банков

Версия: 1.0
Дата: 2026-10-04
Назначение: проектирование локального агента, который агрегирует внешние
сигналы о сбоях банков и связанных IT-сервисов, нормализует их,
коррелирует и рассчитывает вероятность массового инцидента.

------------------------------------------------------------------------

1. Цель проекта

Создать на локальном компьютере единый агент мониторинга, который
регулярно получает информацию из нескольких независимых источников:

1.  сервисов типа Downdetector;
2.  российских детекторов сбоев;
3.  официальных status pages;
4.  RSS Банка России;
5.  официальных Telegram-каналов банков;
6.  новостных/пользовательских источников;
7.  собственных synthetic-проверок доступности;
8.  в дальнейшем — внутренних систем мониторинга.

Главная идея:

  Не считать один источник истиной. Система должна объединять несколько
  независимых сигналов и выдавать вероятность того, что действительно
  происходит массовый инцидент.

------------------------------------------------------------------------

2. Целевая архитектура

                            ВНЕШНИЕ ИСТОЧНИКИ
                                   |
            +----------------------+----------------------+
            |                      |                      |
            v                      v                      v
      DETECTOR404             DownScope             Downdetector
         API                     API                    API
            |                      |                      |
            +----------------------+----------------------+
                                   |
            +----------------------+----------------------+
            |                      |                      |
            v                      v                      v
       Status pages            Banki.ru             Telegram
            |                      |                      |
            +----------------------+----------------------+
                                   |
                                   v
                         НОРМАЛИЗАЦИЯ СОБЫТИЙ
                                   |
                                   v
                           ENTITY RESOLUTION
                         "ВТБ" = "Банк ВТБ"
                                   |
                                   v
                           CORRELATION ENGINE
                                   |
                    +--------------+--------------+
                    |                             |
                    v                             v
            ANOMALY DETECTION              SOURCE AGREEMENT
                    |                             |
                    +--------------+--------------+
                                   |
                                   v
                           RISK / CONFIDENCE SCORE
                                   |
                    +--------------+--------------+
                    |              |              |
                    v              v              v
                 GREEN          WARNING        CRITICAL
                                   |
                                   v
                           DASHBOARD / ALERT

------------------------------------------------------------------------

3. Приоритет источников

Tier 1 — основные источники

3.1 DETECTOR404

Сайт: https://detector404.ru/

Документация API:

https://detector404.ru/doc/api

API требует учетную запись и токен. Токен передается через:

    Authorization: Bearer <TOKEN>

Пример:

    curl --location 'https://detector404.ru/api/v1/alerts' \
      --header 'Authorization: Bearer <TOKEN>'

По официальной документации:

-   есть API;
-   есть активные события;
-   есть сервисы;
-   есть статусы;
-   API возвращает JSON;
-   для большинства запросов ограничение составляет до 20 запросов/сек;
-   для geoip — до 15 запросов/сек;
-   для сервисов с кириллицей рекомендуется использовать urlname или
    percent-encoding.

Особенно важно: DETECTOR404 предоставляет не только пользовательские
жалобы, но и собственные проверки доступности/сенсоры.

В FAQ также указана возможность получать уведомления через Telegram,
e-mail и API.

Роль в агенте

Использовать как один из основных независимых источников:

    DETECTOR404
        |
        +-- service status
        +-- alerts
        +-- user reports
        +-- regions
        +-- availability signals

------------------------------------------------------------------------

3.2 DownScope

Сайт:

https://downscope.ru/

На сайте заявлен Business API:

  статусы сервисов и поток инцидентов в формате JSON.

DownScope мониторит популярные онлайн-сервисы, собирает пользовательские
жалобы и выполняет проверки доступности.

Роль

Использовать как независимый второй источник.

Важно:

  DETECTOR404 и DownScope нельзя считать полностью независимыми друг от
  друга, если часть их сигналов построена на похожих пользовательских
  данных.

Поэтому источник должен иметь вес ниже, чем два действительно разных
класса сигналов.

------------------------------------------------------------------------

3.3 Downdetector

Сайт:

https://downdetector.com/

API:

https://downdetectorapi.com/v2/docs/

Downdetector API v2 — REST API Enterprise-уровня.

Документация описывает:

    companies
    status
    incidents
    messages
    baseline

Например:

    GET /v2/companies/{company_id}/status
    GET /v2/companies/{company_id}/incidents
    GET /v2/companies/{company_id}/messages
    GET /v2/companies/{company_id}/baseline/current

Есть Bearer authentication и rate limiting.

Роль

Очень хороший источник для production-варианта, но для MVP сначала
проверить стоимость и доступность Enterprise API.

------------------------------------------------------------------------

4. Tier 2 — официальные и подтверждающие источники

4.1 Status pages

Использовать официальные status pages внешних поставщиков.

Примеры категорий:

    Cloud
    CDN
    DNS
    Authentication
    Payment
    Messaging
    API
    Cloud infrastructure

Задача агента:

    status page
          |
          v
    официальный incident
          |
          v
    нормализованное событие

Официальный status page имеет больший вес, чем пользовательский отчет.

------------------------------------------------------------------------

4.2 StatusGator

Сайт:

https://statusgator.com/

API:

https://statusgator.com/integration/rest_api

StatusGator агрегирует status pages и предоставляет REST API.

Актуальная версия API — v3.

API позволяет получать:

-   сервисы;
-   статусы;
-   incidents;
-   historical data;
-   monitors;
-   uptime.

StatusGator полезен как единый слой над большим количеством официальных
status pages.

Роль

Использовать для зависимостей банка и внешних IT-поставщиков.

------------------------------------------------------------------------

4.3 IsDown

Сайт:

https://isdown.app/

API:

https://dev.isdown.app/

Использовать как дополнительный агрегатор.

Не делать его единственным источником: он скорее дополнительный слой
подтверждения.

------------------------------------------------------------------------

5. Tier 3 — российские источники

5.1 DownRadar

https://downradar.ru/

Есть отдельная секция API/мониторинга.

Использовать как дополнительный источник, пока не подтверждены
актуальные условия и формат API.

Сигналы:

-   пользовательские сообщения;
-   история;
-   доступность;
-   комментарии;
-   информация о проблемах доступа.

------------------------------------------------------------------------

5.2 DownReport

https://downreport.ru/

Сервис показывает:

-   жалобы за час;
-   статус популярных сервисов;
-   историю;
-   пользовательские сообщения;
-   признаки ограничений/замедлений.

В каталоге присутствуют российские банки, включая Сбербанк, Альфа-Банк,
Т-Банк и Газпромбанк.

Публичная API-документация не найдена. Поэтому на MVP использовать
только после проверки разрешенного способа автоматизированного получения
данных.

------------------------------------------------------------------------

5.3 Outage.Report

https://outage.report/

Полезен как дополнительный международный источник.

Сервис использует пользовательские reports и социальные сигналы,
сравнивая их с нормальным baseline.

Не использовать как основной источник российских банков.

------------------------------------------------------------------------

6. Банки.ру

https://www.banki.ru/

Использовать как вторичный пользовательский/медийный сигнал.

Что искать:

    банк + не работает
    банк + приложение
    банк + сбой
    банк + платеж
    банк + перевод
    банк + карта
    банк + личный кабинет

Главное правило:

  данные Banki.ru не должны сами создавать CRITICAL-инцидент.

Они должны усиливать уже существующий сигнал.

------------------------------------------------------------------------

7. Telegram

Подключить официальные каналы банков.

Принцип:

    официальный канал банка
            |
            v
    новое сообщение
            |
            v
    NLP / keyword classifier
            |
            v
    "технические проблемы"
    "восстановили работу"
    "наблюдаются затруднения"
    "проводятся работы"

Особенно ценны сообщения:

    "наблюдаются проблемы"
    "временная недоступность"
    "часть клиентов"
    "не работает приложение"
    "не проходят операции"
    "проблема устранена"

Официальное сообщение банка имеет очень высокий вес.

------------------------------------------------------------------------

8. Банк России

RSS:

https://www.cbr.ru/development/RSS/

Доступны RSS:

-   новости;
-   события;
-   пресс-релизы;
-   валюты;
-   отдельные регламентные информационные потоки.

Для агента достаточно начать с:

    RssNews
    eventrss
    RssPress

Цель:

не детектировать технический сбой, а добавлять официальный регуляторный
контекст.

------------------------------------------------------------------------

9. Собственные synthetic checks

Это один из самых важных компонентов.

Агент должен уметь сам проверять:

    DNS
    TCP
    TLS
    HTTP
    HTTPS
    response time
    HTTP status
    content
    API endpoint

Пример:

    https://bank.ru/
    https://bank.ru/login
    https://api.bank.ru/health
    https://auth.bank.ru/

Для каждого endpoint:

    {
      "target": "bank.ru/login",
      "dns_ms": 12,
      "tcp_ms": 20,
      "tls_ms": 35,
      "ttfb_ms": 180,
      "status_code": 200,
      "available": true,
      "checked_at": "2026-10-04T10:00:00Z"
    }

Важно:

  Один компьютер не является надежным источником географически
  распределенной доступности.

Если возможно, использовать несколько разрешенных внешних точек.

------------------------------------------------------------------------

10. Список банков для MVP

Начать с:

    Сбербанк
    ВТБ
    Т-Банк
    Альфа-Банк
    Газпромбанк
    Райффайзенбанк
    Совкомбанк
    Росбанк
    МТС Банк
    Открытие / актуальная правопреемная структура
    ПСБ
    Россельхозбанк
    МКБ
    Ак Барс Банк
    Уралсиб
    Банк Санкт-Петербург

После проверки источников добавить остальные банки.

------------------------------------------------------------------------

11. Каноническая модель события

Все источники должны приводиться к единому JSON.

    {
      "event_id": "uuid",
      "timestamp": "2026-10-04T10:00:00Z",

      "entity": {
        "type": "bank",
        "canonical_name": "ВТБ",
        "aliases": [
          "Банк ВТБ",
          "ВТБ",
          "VTB"
        ]
      },

      "source": {
        "name": "detector404",
        "type": "crowd_monitoring",
        "reliability": 0.75
      },

      "signal": {
        "type": "user_reports",
        "status": "anomaly",
        "value": 87,
        "baseline": 12,
        "ratio": 7.25
      },

      "location": {
        "country": "RU",
        "regions": []
      },

      "severity": "warning",

      "raw": {}
    }

------------------------------------------------------------------------

12. Типы сигналов

    USER_REPORT
    SYNTHETIC_CHECK
    OFFICIAL_STATUS
    OFFICIAL_TELEGRAM
    NEWS
    REGULATOR
    SOCIAL
    DNS_FAILURE
    TCP_FAILURE
    TLS_FAILURE
    HTTP_FAILURE
    API_FAILURE
    LATENCY_ANOMALY

------------------------------------------------------------------------

13. Нормализация сущностей

Главная проблема агрегатора — разные названия одной организации.

Например:

    "ВТБ"
    "Банк ВТБ"
    "ВТБ Банк"
    "VTB"
    "vtb.ru"

должны стать:

    canonical_id = bank_vtb
    canonical_name = ВТБ

Создать файл:

    entities.yaml

Пример:

    bank_vtb:
      name: "ВТБ"
      aliases:
        - "ВТБ"
        - "Банк ВТБ"
        - "VTB"
      domains:
        - "vtb.ru"

    bank_sber:
      name: "Сбербанк"
      aliases:
        - "Сбербанк"
        - "Сбер"
        - "Sber"
      domains:
        - "sberbank.ru"

------------------------------------------------------------------------

14. Anomaly detection

Нельзя считать:

    100 жалоб = сбой

Для разных сервисов нормальное количество жалоб разное.

Нужно считать baseline.

Простейшая модель:

    ratio = current_reports / expected_reports

Пример:

    обычно: 5 сообщений / 15 мин
    сейчас: 40 сообщений / 15 мин

    ratio = 8

Это сильнее абсолютного значения.

------------------------------------------------------------------------

15. Более правильный baseline

Учитывать:

    час суток
    день недели
    праздники
    время зарплат
    начало месяца
    конец месяца
    известные акции
    известные технические работы

Минимальная модель:

    expected =
    median(
      same_weekday,
      same_hour,
      previous_4_weeks
    )

Затем:

    z_score =
    (current - mean) / std

На первом этапе достаточно rolling median + MAD.

------------------------------------------------------------------------

16. Корреляция источников

Главная логика агента:

    Источник                 Сигнал
    ----------------------------------------
    DETECTOR404              +1
    DownScope                +1
    Downdetector             +1
    Synthetic                +2
    Official Telegram        +3
    Official Status Page     +3
    Banki.ru                 +0.5
    News                     +0.5
    CBR                      +3

Это не финальные веса. Их нужно калибровать на истории.

------------------------------------------------------------------------

17. External Outage Confidence Score

Предлагаемая шкала:

    EOCS = 0..100

Пример:

    30% anomaly user reports
    25% synthetic checks
    20% independent detector agreement
    15% official/social confirmation
    10% additional context

Пример:

    DETECTOR404 anomaly       24
    DownScope anomaly         18
    Synthetic HTTP 503        25
    Telegram confirmation     10
    Banki.ru activity          4
    --------------------------------
    EOCS                      81

Результат:

    CRITICAL

------------------------------------------------------------------------

18. Статусы

    0–19     GREEN
    20–39    WATCH
    40–59    WARNING
    60–79    PROBABLE_OUTAGE
    80–100   CONFIRMED/CRITICAL

Но необходимо различать:

    technical failure
    user complaint spike
    regional outage
    national outage
    external dependency outage
    access restriction
    scheduled maintenance

------------------------------------------------------------------------

19. Географическая корреляция

Если есть региональные данные:

    Москва        +
    СПб           +
    Екатеринбург  +
    Новосибирск   +
    Казань        +

то вероятность массового сбоя выше.

Если:

    только Москва

не надо автоматически считать это общенациональным инцидентом.

Модель:

    geographic_coverage =
    affected_regions / monitored_regions

------------------------------------------------------------------------

20. Корреляция по функциональному признаку

Очень полезно классифицировать жалобы:

    LOGIN
    PAYMENT
    TRANSFER
    CARD
    MOBILE_APP
    WEB
    ATM
    API
    SMS
    PUSH
    AUTH
    BIOMETRICS

Например:

    LOGIN      70%
    PAYMENT    10%
    TRANSFER    5%

может означать проблему authentication layer.

А:

    PAYMENT    70%
    TRANSFER   20%
    LOGIN       5%

может указывать на платежный контур.

------------------------------------------------------------------------

21. Причинно-следственная модель

Добавить dependency graph:

    Банк
     |
     +-- Mobile App
     |
     +-- Web
     |
     +-- Auth
     |
     +-- Payment
     |     |
     |     +-- external PSP
     |
     +-- SMS
     |
     +-- Push
     |
     +-- CDN
     |
     +-- DNS
     |
     +-- Cloud

Если одновременно падают:

    много банков
          |
          v
    один внешний provider

это уже другой класс инцидента:

    COMMON_DEPENDENCY_INCIDENT

------------------------------------------------------------------------

22. Пример корреляции

Ситуация:

    14:03 DETECTOR404
    ВТБ: +500% reports

    14:04 DownScope
    ВТБ: anomaly

    14:05 Synthetic
    vtb.ru = HTTP 503

    14:06 Banki.ru
    +15 новых сообщений

    14:07 Telegram ВТБ
    официальное сообщение о затруднениях

Агент:

    ENTITY: ВТБ
    STATUS: CRITICAL
    EOCS: 96

    START: 14:03

    SIGNALS:
    5 независимых подтверждений

    SCOPE:
    Russia-wide probable

    PRIMARY SYMPTOM:
    Web/mobile access

    OFFICIAL CONFIRMATION:
    YES

------------------------------------------------------------------------

23. Если одновременно проблемы у нескольких банков

Особенно важный сценарий.

    ВТБ       ++++
    Сбер      ++++
    Альфа     ++++
    Т-Банк    ++++

и одновременно:

    Cloudflare +
    DNS +
    Internet provider +

тогда агент должен искать общую причину.

Возможные категории:

    DNS
    CDN
    cloud
    payment network
    telecom
    internet exchange
    authentication provider
    certificate authority

------------------------------------------------------------------------

24. Архитектура локального приложения

Для первого MVP не нужны Kubernetes, Kafka или PostgreSQL.

Предлагаемый стек:

    Python
    SQLite
    FastAPI
    HTML/CSS/JS

Если хочется вообще без сторонних библиотек:

    Python stdlib
    SQLite
    http.server
    urllib
    sqlite3
    json
    xml
    threading

Но для удобства разработки лучше:

    Python
    FastAPI
    SQLite
    vanilla JS

------------------------------------------------------------------------

25. Структура проекта

    bank-outage-agent/
    │
    ├── config/
    │   ├── banks.yaml
    │   ├── sources.yaml
    │   └── keywords.yaml
    │
    ├── collectors/
    │   ├── detector404.py
    │   ├── downscope.py
    │   ├── downdetector.py
    │   ├── statusgator.py
    │   ├── telegram.py
    │   ├── cbr.py
    │   ├── bankiru.py
    │   └── synthetic.py
    │
    ├── core/
    │   ├── normalizer.py
    │   ├── entity_resolver.py
    │   ├── anomaly.py
    │   ├── correlation.py
    │   ├── scoring.py
    │   └── incident.py
    │
    ├── storage/
    │   ├── database.py
    │   └── schema.sql
    │
    ├── api/
    │   └── server.py
    │
    ├── ui/
    │   ├── index.html
    │   ├── app.js
    │   └── style.css
    │
    ├── logs/
    │
    ├── data/
    │
    ├── .env
    ├── requirements.txt
    └── main.py

------------------------------------------------------------------------

26. Интервал опроса

Для MVP:

    DETECTOR404        1–5 min
    DownScope          1–5 min
    Downdetector       1–5 min
    Status pages       1–5 min
    Telegram           near real-time / 1 min
    CBR RSS            5–10 min
    Banki.ru           5 min
    Synthetic          1 min

Не надо делать запрос каждую секунду.

Это увеличит нагрузку и может привести к блокировкам.

------------------------------------------------------------------------

27. Retry policy

Для каждого collector:

    timeout = 10 sec

    retry:
      1st = 5 sec
      2nd = 15 sec
      3rd = 60 sec

При HTTP 429:

    уважать Retry-After

При HTTP 401/403:

    не делать бесконечный retry
    перевести источник в AUTH_ERROR

------------------------------------------------------------------------

28. Хранение

Минимальная SQLite схема:

    CREATE TABLE events (
        id TEXT PRIMARY KEY,
        timestamp TEXT,
        entity_id TEXT,
        source TEXT,
        signal_type TEXT,
        status TEXT,
        value REAL,
        baseline REAL,
        score REAL,
        region TEXT,
        raw_json TEXT
    );

Инциденты:

    CREATE TABLE incidents (
        id TEXT PRIMARY KEY,
        entity_id TEXT,
        started_at TEXT,
        resolved_at TEXT,
        status TEXT,
        confidence REAL,
        severity TEXT,
        summary TEXT
    );

------------------------------------------------------------------------

29. Dashboard

Главный экран:

    =================================================
     EXTERNAL BANK OUTAGE MONITOR
    =================================================

    CRITICAL
    -------------------------------------------------
    🔴 ВТБ             EOCS 94
    🔴 Сбербанк        EOCS 82
    🟠 Альфа-Банк      EOCS 57

    WATCH
    -------------------------------------------------
    🟡 Т-Банк          EOCS 34

    NORMAL
    -------------------------------------------------
    🟢 Газпромбанк
    🟢 ПСБ
    🟢 Совкомбанк

    =================================================

    ACTIVE INCIDENTS: 3

    14:03 ВТБ
      reports +520%
      synthetic 503
      3 sources agree

    13:47 Сбербанк
      mobile login anomaly

    12:30 Альфа
      payment reports spike
    =================================================

------------------------------------------------------------------------

30. Карточка инцидента

    ВТБ
    --------------------------------------------

    STATUS: CRITICAL
    EOCS: 94

    Started:
    14:03

    Duration:
    17 min

    Sources:
    DETECTOR404       YES
    DownScope         YES
    Downdetector      YES
    Synthetic         YES
    Telegram          YES
    Banki.ru          YES

    Symptoms:
    LOGIN
    WEB
    MOBILE

    Regions:
    Москва
    СПб
    Казань
    Екатеринбург
    ...

    Official confirmation:
    YES

    Possible cause:
    AUTH / WEB PLATFORM

    Confidence:
    94%

------------------------------------------------------------------------

31. AI-агент

LLM не должен быть основным детектором.

Правильная схема:

    COLLECTORS
        ↓
    RULES
        ↓
    STATISTICS
        ↓
    CORRELATION
        ↓
    INCIDENT
        ↓
    LLM

LLM получает уже структурированные данные.

Его задачи:

    1. объяснить инцидент человеку;
    2. объединить похожие события;
    3. определить вероятный тип проблемы;
    4. сделать краткое резюме;
    5. сравнить с историческими инцидентами;
    6. предложить гипотезу причины;
    7. сформировать сообщение для NOC/руководителя.

------------------------------------------------------------------------

32. Пример промпта для LLM

    Ты являешься аналитиком внешних IT-инцидентов банков.

    Твоя задача — анализировать структурированные сигналы мониторинга.

    Не утверждай причину инцидента без подтверждения.

    Разделяй:
    1. факт;
    2. наблюдение;
    3. корреляцию;
    4. гипотезу.

    Для каждого инцидента сформируй:

    - банк;
    - время начала;
    - текущий статус;
    - масштаб;
    - затронутые функции;
    - географию;
    - независимые источники;
    - официальное подтверждение;
    - вероятную причину;
    - альтернативные гипотезы;
    - confidence;
    - что проверить дальше.

    Если данных недостаточно, явно напиши:
    "Недостаточно данных".

------------------------------------------------------------------------

33. Очень важное правило

Не использовать LLM для определения:

    HTTP 503 = точно сбой банка

Это должен определить deterministic engine.

LLM только интерпретирует.

------------------------------------------------------------------------

34. Концепция “сигнал → событие → инцидент”

Это фундаментальная архитектура.

Signal

Один факт:

    DETECTOR404:
    reports = 80
    baseline = 10

Event

Интерпретация:

    user_report_anomaly

Incident

Коррелированное событие:

    ВТБ массовый сбой web/mobile

------------------------------------------------------------------------

35. Состояния инцидента

    NEW
     |
     v
    INVESTIGATING
     |
     +--> FALSE_POSITIVE
     |
     v
    PROBABLE
     |
     v
    CONFIRMED
     |
     v
    RESOLVED

------------------------------------------------------------------------

36. False Positive

Система должна уметь сама снижать ложные тревоги.

Например:

    DETECTOR404:
    +300%

    Synthetic:
    200 OK

    DownScope:
    normal

    Official:
    normal

    Banki.ru:
    1 message

Результат:

    WATCH
    EOCS 27

а не CRITICAL.

------------------------------------------------------------------------

37. Maintenance awareness

Добавить календарь плановых работ:

    entity
    start
    end
    scope
    source

Если известно:

    01:00–03:00 плановые работы

и в 01:30 выросли жалобы:

    не создавать CRITICAL

а:

    PLANNED_MAINTENANCE

------------------------------------------------------------------------

38. Что делать в MVP

Этап 1

Сделать:

    DETECTOR404
    DownScope
    CBR RSS
    Synthetic HTTP
    SQLite
    Dashboard

Этап 2

Добавить:

    Telegram
    Banki.ru
    Downdetector

Этап 3

Добавить:

    StatusGator
    IsDown
    Outage.Report
    DownRadar
    DownReport

Этап 4

Добавить:

    LLM
    historical analysis
    root cause hypotheses
    incident summaries

------------------------------------------------------------------------

39. Первый MVP: минимальный код

Логика запуска:

    while True:

        signals = []

        signals += detector404.collect()
        signals += downscope.collect()
        signals += cbr.collect()
        signals += synthetic.collect()

        normalized = normalize(signals)

        incidents = correlate(normalized)

        scored = calculate_scores(incidents)

        save(scored)

        notify(scored)

        sleep(60)

------------------------------------------------------------------------

40. Конфигурация источников

Пример:

    sources:

      detector404:
        enabled: true
        interval: 60
        token_env: DETECTOR404_TOKEN

      downscope:
        enabled: true
        interval: 60
        token_env: DOWNSCOPE_TOKEN

      downdetector:
        enabled: false
        interval: 300
        token_env: DOWNDETECTOR_TOKEN

      cbr:
        enabled: true
        interval: 600

      synthetic:
        enabled: true
        interval: 60

------------------------------------------------------------------------

41. Конфигурация банков

    banks:

      - id: vtb
        name: "ВТБ"
        aliases:
          - "ВТБ"
          - "Банк ВТБ"
          - "VTB"
        domains:
          - "vtb.ru"
        critical_endpoints:
          - "https://www.vtb.ru/"
          - "https://www.vtb.ru/personal/"

------------------------------------------------------------------------

42. Secrets

Никогда не хранить API keys в коде.

Использовать:

    .env

Пример:

    DETECTOR404_TOKEN=...
    DOWNSCOPE_TOKEN=...
    DOWNDETECTOR_TOKEN=...
    STATUSGATOR_TOKEN=...
    ISDOWN_TOKEN=...

.env добавить в .gitignore.

------------------------------------------------------------------------

43. Логирование

Каждый collector должен писать:

    timestamp
    source
    request
    response code
    duration
    items received
    error

Пример:

    2026-10-04 14:03:01
    [DETECTOR404]
    HTTP 200
    events=17
    duration=0.42s

При ошибке:

    [DETECTOR404]
    HTTP 429
    retry_after=30

------------------------------------------------------------------------

44. Health monitoring самого агента

Нельзя допустить ситуацию:

  агент не работает, но dashboard показывает “всё нормально”.

Поэтому добавить:

    collector health
    last_success
    last_error
    last_event

Dashboard:

    DETECTOR404     🟢 12 sec ago
    DownScope       🟢 21 sec ago
    CBR RSS         🟢 4 min ago
    Telegram        🟢 3 sec ago
    Synthetic       🟢 20 sec ago

Если источник не отвечает:

    SOURCE_UNAVAILABLE

а не GREEN.

------------------------------------------------------------------------

45. Ключевой принцип надежности

Статус:

    GREEN

означает не:

  “Мы не нашли проблем.”

а:

  “Мы получили свежие данные из достаточного количества источников и
  признаков сбоя нет.”

Это принципиально разные вещи.

------------------------------------------------------------------------

46. Что можно добавить потом

Машинное обучение

После накопления истории:

    features:

    report_count
    report_velocity
    baseline_ratio
    z_score
    region_count
    source_count
    http_errors
    latency
    official_confirmation
    time_of_day
    day_of_week

Модель:

    P(outage | features)

Можно начать с:

    Logistic Regression
    Random Forest
    XGBoost

LLM для этого не обязателен.

------------------------------------------------------------------------

47. Перспективная архитектура

В будущем:

                       SOURCE LAYER
                             |
                  +----------+----------+
                  |          |          |
                  v          v          v
               API        RSS       Social
                  |          |          |
                  +----------+----------+
                             |
                      NORMALIZATION
                             |
                       EVENT BUS
                             |
                  +----------+----------+
                  |                     |
                  v                     v
           RULE ENGINE             ML ENGINE
                  |                     |
                  +----------+----------+
                             |
                     INCIDENT ENGINE
                             |
                  +----------+----------+
                  |                     |
                  v                     v
                 LLM                DASHBOARD
                  |
                  v
           HUMAN SUMMARY

------------------------------------------------------------------------

48. Главная идея проекта

Это не “парсер Downdetector”.

Это:

  External Banking Incident Intelligence Agent

Он должен отвечать на четыре вопроса:

1. Что произошло?

    ВТБ — резкий рост сообщений о недоступности.

2. Насколько это серьезно?

    EOCS = 91
    CRITICAL

3. Насколько мы уверены?

    5 независимых сигналов
    3 типа источников
    официальное подтверждение

4. Что вероятно происходит?

    Вероятная проблема web/authentication контура.
    Общебанковский платежный контур пока не подтвержден.

------------------------------------------------------------------------

49. Приоритет реализации

  Компонент            Приоритет
  ------------------ -----------
  DETECTOR404                 P0
  DownScope                   P0
  Synthetic checks            P0
  SQLite                      P0
  Normalization               P0
  Correlation                 P0
  EOCS scoring                P0
  Dashboard                   P0
  CBR RSS                     P1
  Telegram                    P1
  Downdetector                P1
  Banki.ru                    P1
  StatusGator                 P2
  IsDown                      P2
  DownRadar                   P2
  DownReport                  P2
  LLM                         P2
  ML                          P3

------------------------------------------------------------------------

50. Источники и документация

DETECTOR404 API: https://detector404.ru/doc/api

DETECTOR404 FAQ: https://detector404.ru/doc/faq

DownScope: https://downscope.ru/

Downdetector API: https://downdetectorapi.com/v2/docs/

StatusGator REST API: https://statusgator.com/integration/rest_api

StatusGator API v3:
https://statusgator.com/blog/announcing-the-statusgator-api-v3/

IsDown: https://isdown.app/

IsDown API: https://dev.isdown.app/

Outage.Report: https://outage.report/

DownRadar: https://downradar.ru/

DownReport: https://downreport.ru/

Banki.ru: https://www.banki.ru/

Банк России RSS: https://www.cbr.ru/development/RSS/

------------------------------------------------------------------------

51. Важные ограничения

1.  Пользовательские жалобы не равны количеству пострадавших
    пользователей.
2.  Один источник не должен самостоятельно подтверждать массовый
    инцидент.
3.  Scraping использовать только с учетом условий конкретного сервиса.
4.  API-токены хранить вне кода.
5.  Собственные synthetic checks могут быть ограничены географией точки
    проверки.
6.  У разных детекторов могут быть общие исходные данные, поэтому “три
    источника” не всегда означают три независимых наблюдения.
7.  Planned maintenance необходимо отделять от реального сбоя.
8.  HTTP 200 не гарантирует корректность бизнес-функции.
9.  HTTP 503 не всегда означает проблему именно банка.
10. LLM должен интерпретировать события, а не подменять deterministic
    monitoring.

------------------------------------------------------------------------

52. Итоговая концепция MVP

Минимальный работающий продукт:

                    +----------------+
                    | DETECTOR404    |
                    +-------+--------+
                            |
                    +-------v--------+
                    | DOWNSCOPE      |
                    +-------+--------+
                            |
                    +-------v--------+
                    | SYNTHETIC      |
                    +-------+--------+
                            |
                    +-------v--------+
                    | CBR RSS        |
                    +-------+--------+
                            |
                            v
                    +---------------+
                    | NORMALIZER    |
                    +-------+-------+
                            |
                            v
                    +---------------+
                    | CORRELATOR     |
                    +-------+-------+
                            |
                            v
                    +---------------+
                    | EOCS ENGINE    |
                    +-------+-------+
                            |
                  +---------+---------+
                  |                   |
                  v                   v
            +-----------+       +-----------+
            | DASHBOARD |       | ALERTING  |
            +-----------+       +-----------+

После этого подключаются:

    Telegram
    Downdetector
    Banki.ru
    StatusGator
    IsDown
    DownRadar
    DownReport
    LLM
    ML

------------------------------------------------------------------------

53. Следующий практический шаг

После создания MVP имеет смысл перейти от “мониторинга банков” к
мониторингу всей банковской экосистемы:

                        BANK
                         |
           +-------------+-------------+
           |             |             |
         AUTH          PAYMENT       MOBILE
           |             |             |
         SMS          PSP/API       PUSH
           |             |             |
           +-------------+-------------+
                         |
                  EXTERNAL PROVIDERS
                         |
           +------+------+------+------+
           |      |      |      |      |
          DNS    CDN    CLOUD   ISP   API

Тогда агент сможет обнаруживать не только:

  “ВТБ лежит”

но и:

  “У четырех банков одновременно растут ошибки платежей. Одновременно
  наблюдается аномалия у общего внешнего платежного провайдера.
  Вероятность общей инфраструктурной причины — высокая.”

Именно этот уровень корреляции превращает простой outage detector в
инструмент операционного мониторинга и раннего выявления массовых
инцидентов.
