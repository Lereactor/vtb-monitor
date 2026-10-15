"""Period analytics and the summary text (monitor.analytics.report)."""
from datetime import datetime, timedelta, timezone

import pytest

from monitor import analytics, history
from monitor.sources.base import ERROR, OK, OUTAGE, SourceResult
from monitor.state import Event

NOW = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)  # Thu 12:00 MSK


def at(hours):
    return NOW + timedelta(hours=hours)


def ev(db, when, kind, service="vtb", source=""):
    history.record_run(db, when, {}, [Event(kind, service, source, kind)])


def incident(db, start, minutes, sources, service="vtb"):
    ev(db, start, "incident_started", service, sources[0])
    for i, source in enumerate(sources[1:], 1):
        ev(db, start + timedelta(minutes=i), "incident_confirmed", service, source)
    ev(db, start + timedelta(minutes=minutes), "incident_resolved", service)


def check(db, when, source, status=OK, count=None, service="vtb"):
    details = f"жалоб за час: {count}" if count is not None else ""
    history.record_run(db, when, {service: [SourceResult(source, status, details)]}, [])


@pytest.fixture
def db(tmp_path):
    db = history.connect(tmp_path / "h.db")
    check(db, at(-24 * 10), "sboyrf", count=1)  # history starts 10 days ago
    return db


def test_plural():
    forms = ("сбой", "сбоя", "сбоев")
    assert [analytics.plural(n, *forms) for n in (0, 1, 2, 5, 11, 21, 22, 25, 111)] == [
        "сбоев", "сбой", "сбоя", "сбоев", "сбоев", "сбой", "сбоя", "сбоев", "сбоев"]


def test_duration_text():
    assert analytics.duration(35) == "35 мин"
    assert analytics.duration(65) == "1 ч 05 мин"
    assert analytics.duration(120) == "2 ч"


def test_keys_cover_every_period_and_service(db):
    report = analytics.report(db, NOW)
    assert set(report) == {f"{p}|{s}" for p in ("24h", "7d", "30d", "all") for s in ("all", "vtb", "invest")}


def test_kpi_counts_and_clips_to_the_period(db):
    incident(db, at(-2), 20, ["detector404"])
    incident(db, at(-24 - 0.25), 30, ["sboyrf"])  # 15 of its 30 minutes fall into the last 24 h
    incident(db, at(-5), 10, ["downradar"], service="invest")
    kpi = analytics.report(db, NOW)["24h|vtb"]["kpi"]
    assert kpi["incidents"] == 2 and kpi["minutes"] == 35
    assert kpi["uptime"] == pytest.approx(1 - 35 / (24 * 60), abs=1e-4)
    both = analytics.report(db, NOW)["24h|all"]["kpi"]
    assert both["incidents"] == 3 and both["minutes"] == 45


def test_bank_confirmation_and_lead(db):
    incident(db, at(-3), 40, ["detector404"])
    incident(db, at(-1), 10, ["sboyrf"])
    db.execute("INSERT INTO posts VALUES (1, ?, 'outage', 'Наблюдаются затруднения', 'u')",
               (history.iso(at(-3) + timedelta(minutes=12)),))
    db.commit()
    kpi = analytics.report(db, NOW)["24h|vtb"]["kpi"]
    assert kpi["confirmed"] == 1 and kpi["lead_min"] == 12


def test_per_day_uses_msk_dates(db):
    incident(db, datetime(2026, 10, 14, 21, 30, tzinfo=timezone.utc), 15, ["detector404"])  # 15.10 00:30 MSK
    days = {d["date"]: d for d in analytics.report(db, NOW)["7d|vtb"]["per_day"]}
    assert days["2026-10-15"]["incidents"] == 1 and days["2026-10-15"]["minutes"] == 15
    assert days["2026-10-14"]["incidents"] == 0
    assert len(days) == 8  # 7 days back + today


def test_monitors_table(db):
    incident(db, at(-5), 10, ["detector404", "sboyrf"])
    incident(db, at(-3), 10, ["detector404"])
    incident(db, at(-1), 10, ["sboyrf"])
    ev(db, at(-2), "source_down", source="downradar")
    for i in range(3):
        check(db, at(-2) + timedelta(minutes=5 * i), "downradar", ERROR)
    rows = {r["source"]: r for r in analytics.report(db, NOW)["24h|vtb"]["monitors"]}
    assert (rows["detector404"]["first"], rows["detector404"]["solo"], rows["detector404"]["alarms"]) == (2, 1, 2)
    assert (rows["sboyrf"]["first"], rows["sboyrf"]["solo"], rows["sboyrf"]["alarms"]) == (1, 1, 2)
    assert rows["downradar"]["down_episodes"] == 1 and rows["downradar"]["error_minutes"] == 15
    assert set(rows) == {"detector404", "downreport", "downradar", "sboyrf"}


def test_complaints_and_heatmap(db):
    check(db, at(-2), "sboyrf", count=10)
    check(db, at(-2) + timedelta(minutes=5), "sboyrf", count=30)
    check(db, at(-2), "downradar", count=4)
    block = analytics.report(db, NOW)["24h|vtb"]
    assert block["complaints"]["vtb/sboyrf"] == [["2026-10-15T07", 30]]
    # 07 UTC = 10 MSK on Thursday (3): max per source per hour, summed over sources
    assert block["heatmap"][3][10] == 34


def test_summary_without_incidents(db):
    check(db, datetime(2026, 10, 9, 16, 5, tzinfo=timezone.utc), "sboyrf", count=40)  # Fri 19:05 MSK
    text = analytics.report(db, NOW)["7d|all"]["summary"]
    assert text == "За 7 дней сбоев не было. Больше всего жалоб — по пятницам около 19:00."


def test_summary_with_incidents(db):
    incident(db, datetime(2026, 10, 14, 12, 25, tzinfo=timezone.utc), 20, ["detector404", "sboyrf"])  # ср 15:25
    incident(db, at(-3), 15, ["detector404"])
    db.execute("INSERT INTO posts VALUES (1, ?, 'outage', 'Наблюдаются затруднения', 'u')",
               (history.iso(at(-3) + timedelta(minutes=12)),))
    ev(db, at(-1), "source_down", source="downradar")
    ev(db, at(-24 * 8), "source_down", source="downradar")  # outside 7 days
    db.commit()
    text = analytics.report(db, NOW)["7d|all"]["summary"]
    assert text == (
        "За 7 дней: 2 сбоя ВТБ (35 мин), 0 — Мои Инвестиции. "
        "Самый длинный — ср 14.10 в 15:25, 20 мин. "
        "Банк подтвердил 1 из 2, в среднем через 12 мин после начала сбоя. "
        "Первым обычно срабатывает DETECTOR404. "
        "Одиночных срабатываний (возможно, ложных): 1. "
        "DownRadar не отвечал 1 раз.")


def test_summary_for_one_service(db):
    incident(db, at(-3), 15, ["downradar"], service="invest")
    text = analytics.report(db, NOW)["24h|invest"]["summary"]
    assert text.startswith("За сутки: 1 сбой Мои Инвестиции (15 мин).")


def test_summary_skips_peak_time_when_complaints_are_few(db):
    check(db, at(-2), "downradar", count=2, service="invest")
    assert "Больше всего жалоб" not in analytics.report(db, NOW)["24h|invest"]["summary"]


def test_period_starts_at_the_first_check(tmp_path):
    # days before the history began are not «days without incidents»
    db = history.connect(tmp_path / "h.db")
    check(db, at(-24 * 2), "sboyrf", count=1)
    block = analytics.report(db, NOW)["7d|vtb"]
    assert [d["date"] for d in block["per_day"]] == ["2026-10-13", "2026-10-14", "2026-10-15"]
    assert block["kpi"]["uptime"] == 1.0
