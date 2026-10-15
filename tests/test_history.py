import pytest
from datetime import datetime, timedelta, timezone

from monitor import history
from monitor.sources.base import OK, OUTAGE, SourceResult
from monitor.state import Event

pytestmark = pytest.mark.usefixtures("legacy_vtb")

T0 = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)


def test_count_from_details():
    assert history.count_from_details("есть проблемы, жалоб за час: 87") == 87
    assert history.count_from_details("жалоб за час: 3, за сегодня: 459") == 3
    assert history.count_from_details("сенсоры и жалобы в норме") is None
    assert history.count_from_details("") is None


def test_record_run(tmp_path):
    db = history.connect(tmp_path / "h.db")
    results = {"vtb": [SourceResult("downradar", OUTAGE, "есть проблемы, жалоб за час: 12")],
               "invest": [SourceResult("detector404", OK, "сенсоры и жалобы в норме")]}
    history.record_run(db, T0, results, [Event("incident_started", "vtb", "downradar", "🔴 …")])
    assert db.execute("SELECT ts, service, source, status, count FROM checks ORDER BY service").fetchall() == [
        ("2026-10-15T06:00:00+00:00", "invest", "detector404", "OK", None),
        ("2026-10-15T06:00:00+00:00", "vtb", "downradar", "OUTAGE", 12)]
    assert db.execute("SELECT kind, service, source, text FROM events").fetchall() == [
        ("incident_started", "vtb", "downradar", "🔴 …")]


def test_connect_twice_keeps_data(tmp_path):
    db = history.connect(tmp_path / "h.db")
    history.record_run(db, T0, {"vtb": [SourceResult("sboyrf", OK, "жалоб за час: 1")]}, [])
    db.close()
    assert history.connect(tmp_path / "h.db").execute("SELECT count(*) FROM checks").fetchone() == (1,)


def test_roll_up_keeps_hourly_totals(tmp_path):
    db = history.connect(tmp_path / "h.db")
    old = T0 - timedelta(days=history.KEEP_CHECKS_DAYS + 1)
    for minute, status, details in [(0, "OK", "жалоб за час: 3"), (5, "OUTAGE", "жалоб за час: 60"),
                                    (10, "SOURCE_ERROR", "HTTP 500")]:
        history.record_run(db, old + timedelta(minutes=minute),
                           {"vtb": [SourceResult("sboyrf", status, details)]}, [])
    history.record_run(db, T0, {"vtb": [SourceResult("sboyrf", OK, "жалоб за час: 1")]}, [])
    history.roll_up(db, T0)
    assert db.execute("SELECT count(*) FROM checks").fetchone() == (1,)
    assert db.execute("SELECT hour, checks, outages, errors, max_count FROM hourly").fetchall() == [
        ("2026-07-16T06", 3, 1, 1, 60)]


def test_roll_up_leaves_recent_hour_whole(tmp_path):
    # the cutoff is on an hour boundary, so an hour is never split between checks and hourly
    db = history.connect(tmp_path / "h.db")
    edge = (T0 - timedelta(days=history.KEEP_CHECKS_DAYS)).replace(minute=10)
    history.record_run(db, edge, {"vtb": [SourceResult("sboyrf", OK)]}, [])
    history.roll_up(db, T0 + timedelta(minutes=30))
    assert db.execute("SELECT count(*) FROM checks").fetchone() == (1,)
    assert db.execute("SELECT count(*) FROM hourly").fetchone() == (0,)
