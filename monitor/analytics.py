"""Incidents and analytics for the live site, computed from the history."""
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import history
from .notifier import BUSINESS_RE, INVEST_RE, MSK, TITLES
from .services import SERVICES

PERIODS = {"24h": 1, "7d": 7, "30d": 30, "all": None}
PERIOD_LABELS = {"24h": "За сутки", "7d": "За 7 дней", "30d": "За 30 дней", "all": "За всё время наблюдений"}
SHORT_TITLES = {"vtb": "ВТБ", "business": "Бизнес-онлайн", "invest": "Мои Инвестиции"}
WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
ON_WEEKDAYS = ("по понедельникам", "по вторникам", "по средам", "по четвергам", "по пятницам",
               "по субботам", "по воскресеньям")
RUN_MINUTES = 5
PEAK_MIN = 5  # complaints per hour: below that «больше всего жалоб» is noise

POST_BEFORE = timedelta(minutes=30)  # the bank can post a little before the detectors react
POST_AFTER = timedelta(minutes=60)


@dataclass
class Incident:
    service: str
    start: datetime
    end: datetime | None = None   # None while still open
    sources: list = field(default_factory=list)  # in the order they joined
    peak: int | None = None       # max complaints/hour among the count sites during it
    post: dict | None = None      # the matching official post

    def minutes(self, now):
        return int(((self.end or now) - self.start).total_seconds() // 60)


def _post_matches(text, service_id):
    """A post naming a service matches only it; a general one («сбой в работе банка») matches any."""
    named = [sid for sid, pattern in (("invest", INVEST_RE), ("business", BUSINESS_RE)) if pattern.search(text)]
    return service_id in named or not named


def incidents(db, now):
    """All incidents of the monitored services, oldest first, rebuilt from the incident events."""
    found, open_ = [], {}
    for ts, kind, service, source in db.execute(
            "SELECT ts, kind, service, source FROM events WHERE kind LIKE 'incident_%' ORDER BY ts, rowid"):
        if service not in SERVICES:
            continue
        when = datetime.fromisoformat(ts)
        if kind == "incident_started":
            open_[service] = Incident(service, when, sources=[s for s in source.split(",") if s])
            found.append(open_[service])
        elif kind == "incident_confirmed" and service in open_:
            open_[service].sources.append(source)
        elif kind == "incident_resolved" and service in open_:
            open_.pop(service).end = when
    posts = db.execute("SELECT id, ts, kind, text, url FROM posts WHERE kind = 'outage' ORDER BY ts").fetchall()
    for incident in found:
        end = history.iso(incident.end or now)
        incident.peak = db.execute(
            "SELECT max(count) FROM checks WHERE service = ? AND ts BETWEEN ? AND ?",
            (incident.service, history.iso(incident.start), end)).fetchone()[0]
        for post_id, ts, kind, text, url in posts:
            when = datetime.fromisoformat(ts)
            if (incident.start - POST_BEFORE <= when <= incident.start + POST_AFTER
                    and _post_matches(text, incident.service)):
                incident.post = {"id": post_id, "ts": ts, "text": text, "url": url}
                break
    return found


def plural(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    if n % 10 == 1:
        return one
    return few if 2 <= n % 10 <= 4 else many


def duration(minutes):
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest} мин"
    return f"{hours} ч" if not rest else f"{hours} ч {rest:02d} мин"


def _period_start(db, now, days, services):
    """The period, but never before the services' first check: days before are not «calm days»."""
    marks = ",".join("?" * len(services))
    first = db.execute(f"SELECT min(ts) FROM (SELECT min(ts) AS ts FROM checks WHERE service IN ({marks}) "
                       f"UNION ALL SELECT min(hour) || ':00:00+00:00' FROM hourly WHERE service IN ({marks}))",
                       (*services, *services)).fetchone()[0]
    if first is None:  # nothing checked yet for these services
        first = db.execute("SELECT min(ts) FROM checks").fetchone()[0]
    first = min(datetime.fromisoformat(first), now) if first else now
    return max(now - timedelta(days=days), first) if days else first


def _clipped(incident, start, now):
    begin, end = max(incident.start, start), min(incident.end or now, now)
    return max(0, int((end - begin).total_seconds() // 60))


def _hourly_counts(db, start, services):
    """{"service/source": {"YYYY-MM-DDTHH": max complaints that hour}} from checks and roll-ups."""
    marks = ",".join("?" * len(services))
    series = defaultdict(dict)
    rows = db.execute(f"""SELECT service, source, substr(ts, 1, 13), max(count) FROM checks
                          WHERE count IS NOT NULL AND ts >= ? AND service IN ({marks})
                          GROUP BY 1, 2, 3""", (history.iso(start), *services)).fetchall()
    rows += db.execute(f"""SELECT service, source, hour, max_count FROM hourly
                           WHERE max_count IS NOT NULL AND hour >= ? AND service IN ({marks})""",
                       (history.iso(start)[:13], *services)).fetchall()
    for service, source, hour, value in rows:
        key = f"{service}/{source}"
        series[key][hour] = max(value, series[key].get(hour, value))
    return series


def _heatmap(hourly):
    """7 weekdays × 24 MSK hours: mean complaints per hour, all count sites summed."""
    totals = defaultdict(int)
    for values in hourly.values():
        for hour, value in values.items():
            totals[hour] += value
    cells = defaultdict(list)
    for hour, value in totals.items():
        local = datetime.fromisoformat(hour + ":00:00+00:00").astimezone(MSK)
        cells[(local.weekday(), local.hour)].append(value)
    return [[round(statistics.mean(cells[(day, hour)]), 1) if cells[(day, hour)] else None
             for hour in range(24)] for day in range(7)]


def _complaints(hourly, daily):
    """Hourly series, or daily maxima for the all-time period (keeps the file small)."""
    if not daily:
        return {key: [[hour, values[hour]] for hour in sorted(values)] for key, values in hourly.items()}
    out = {}
    for key, values in hourly.items():
        days = defaultdict(int)
        for hour, value in values.items():
            days[hour[:10]] = max(days[hour[:10]], value)
        out[key] = [[day, days[day]] for day in sorted(days)]
    return out


def _count(db, sql, *args):
    return db.execute(sql, args).fetchone()[0]


def _monitors(db, services, incs, start):
    since, since_hour = history.iso(start), history.iso(start)[:13]
    rows = []
    for service_id in services:
        mine = [i for i in incs if i.service == service_id]
        for source in SERVICES[service_id].detectors:
            down = _count(db, "SELECT count(*) FROM events WHERE kind = 'source_down' "
                              "AND service = ? AND source = ? AND ts >= ?", service_id, source, since)
            errors = _count(db, "SELECT count(*) FROM checks WHERE status = 'SOURCE_ERROR' "
                                "AND service = ? AND source = ? AND ts >= ?", service_id, source, since)
            errors += _count(db, "SELECT coalesce(sum(errors), 0) FROM hourly "
                                 "WHERE service = ? AND source = ? AND hour >= ?", service_id, source, since_hour)
            rows.append({"service": service_id, "source": source, "title": TITLES[source],
                         "first": sum(1 for i in mine if i.sources[:1] == [source]),
                         "solo": sum(1 for i in mine if i.sources == [source]),
                         "alarms": sum(1 for i in mine if source in i.sources),
                         "down_episodes": down, "error_minutes": errors * RUN_MINUTES})
    return rows


def _sites(db, services, start):
    """Per bank site and region: share of check points that got an answer, and minutes when
    none of at least two did (the site did not open from anywhere in that region)."""
    rows = []
    for service_id in services:
        for host in SERVICES[service_id].sites:
            row = {"service": service_id, "host": host}
            for region in ("ru", "world"):
                up, total, dark, checks = db.execute(
                    "SELECT coalesce(sum(up), 0), coalesce(sum(total), 0), "
                    "coalesce(sum(up = 0 AND total >= 2), 0), count(*) "
                    "FROM reach WHERE service = ? AND host = ? AND region = ? AND ts >= ?",
                    (service_id, host, region, history.iso(start))).fetchone()
                row[region] = {"share": round(up / total, 4) if total else None,
                               "dark_minutes": dark * RUN_MINUTES, "checks": checks}
            rows.append(row)
    return rows


def _kpi(services, incs, start, now):
    period = max((now - start).total_seconds() / 60, 1)
    leads = [int((datetime.fromisoformat(i.post["ts"]) - i.start).total_seconds() // 60)
             for i in incs if i.post]
    uptimes = [1 - sum(_clipped(i, start, now) for i in incs if i.service == s) / period
               for s in services]
    return {"incidents": len(incs), "minutes": sum(_clipped(i, start, now) for i in incs),
            "uptime": round(statistics.mean(uptimes), 4), "confirmed": len(leads),
            "lead_min": round(statistics.median(leads)) if leads else None}


def _per_day(incs, start, now):
    """Every MSK day of the period; an incident counts on the day it started."""
    days = {}
    day = start.astimezone(MSK).date()
    while day <= now.astimezone(MSK).date():
        days[day.isoformat()] = {"date": day.isoformat(), "incidents": 0, "minutes": 0}
        day += timedelta(days=1)
    for incident in incs:
        key = max(incident.start, start).astimezone(MSK).date().isoformat()
        if key in days:
            days[key]["incidents"] += 1
            days[key]["minutes"] += _clipped(incident, start, now)
    return list(days.values())


def _summary(period, services, incs, kpi, monitors, heatmap, start, now, sites=()):
    """Plain-language summary built from the same numbers. No LLM."""
    label = PERIOD_LABELS[period]
    parts = []
    if not incs:
        parts.append(f"{label} сбоев не было.")
    else:
        counts = []
        for service_id in services:
            mine = [i for i in incs if i.service == service_id]
            minutes = sum(_clipped(i, start, now) for i in mine)
            counts.append(f"{len(mine)} {plural(len(mine), 'сбой', 'сбоя', 'сбоев')} "
                          f"{SHORT_TITLES[service_id]} ({duration(minutes)})" if mine
                          else f"0 — {SHORT_TITLES[service_id]}")
        parts.append(f"{label}: {', '.join(counts)}.")
        longest = max(incs, key=lambda i: i.minutes(now))
        local = longest.start.astimezone(MSK)
        parts.append(f"Самый длинный — {WEEKDAYS[local.weekday()]} {local:%d.%m} в {local:%H:%M}, "
                     f"{duration(longest.minutes(now))}.")
        if kpi["confirmed"]:
            lead = kpi["lead_min"]
            parts.append(f"Банк подтвердил {kpi['confirmed']} из {len(incs)}, " +
                         (f"в среднем через {lead} мин после начала сбоя." if lead >= 0
                          else f"в среднем за {-lead} мин до начала сбоя."))
        else:
            parts.append("Банк сбои не подтверждал.")
        first = Counter(i.sources[0] for i in incs if i.sources).most_common(1)
        if first:
            parts.append(f"Первым обычно срабатывает {TITLES[first[0][0]]}.")
        solo = sum(1 for i in incs if len(i.sources) == 1)
        if solo:
            parts.append(f"Одиночных срабатываний (возможно, ложных): {solo}.")
    broken = Counter()
    for row in monitors:
        broken[row["title"]] += row["down_episodes"]
    for title, n in broken.items():
        if n:
            parts.append(f"{title} не отвечал {n} {plural(n, 'раз', 'раза', 'раз')}.")
    for row in sites:
        dark = [f"{where} {duration(row[region]['dark_minutes'])}"
                for region, where in (("ru", "из России"), ("world", "из-за рубежа"))
                if row[region]["dark_minutes"]]
        if dark:
            parts.append(f"{row['host']} не открывался {' и '.join(dark)}.")
    cells = [(value, day, hour) for day, row in enumerate(heatmap)
             for hour, value in enumerate(row) if value and value >= PEAK_MIN]
    if cells:
        _, day, hour = max(cells)
        parts.append(f"Больше всего жалоб — {ON_WEEKDAYS[day]} около {hour:02d}:00.")
    return " ".join(parts)


def report(db, now):
    """{"<period>|<service filter>": analytics block} for every period and service filter."""
    every = incidents(db, now)
    out = {}
    for period, days in PERIODS.items():
        for service_filter in ("all", *SERVICES):
            services = list(SERVICES) if service_filter == "all" else [service_filter]
            start = _period_start(db, now, days, services)
            incs = [i for i in every if i.service in services and (i.end or now) > start and i.start <= now]
            kpi = _kpi(services, incs, start, now)
            hourly = _hourly_counts(db, start, services)
            heatmap = _heatmap(hourly)
            monitors = _monitors(db, services, incs, start)
            sites = _sites(db, services, start)
            out[f"{period}|{service_filter}"] = {
                "kpi": kpi, "per_day": _per_day(incs, start, now),
                "complaints": _complaints(hourly, daily=days is None),
                "heatmap": heatmap, "monitors": monitors, "sites": sites,
                "summary": _summary(period, services, incs, kpi, monitors, heatmap, start, now, sites)}
    return out
