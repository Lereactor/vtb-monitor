from datetime import datetime, timedelta, timezone

from monitor import analytics, history
from monitor.sources.base import OK, OUTAGE, SourceResult
from monitor.state import Event

T0 = datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)  # Tue 12:00 MSK


def at(minute):
    return T0 + timedelta(minutes=minute)


def ev(db, minute, kind, service="vtb", source=""):
    history.record_run(db, at(minute), {}, [Event(kind, service, source, kind)])


def check(db, minute, source, status, count=None, service="vtb"):
    details = f"жалоб за час: {count}" if count is not None else ""
    history.record_run(db, at(minute), {service: [SourceResult(source, status, details)]}, [])


def post(db, minute, text, kind="outage", post_id=1):
    db.execute("INSERT INTO posts VALUES (?, ?, ?, ?, ?)",
               (post_id, history.iso(at(minute)), kind, text, f"https://t.me/bankvtb/{post_id}"))
    db.commit()


def make_db(tmp_path):
    return history.connect(tmp_path / "h.db")


def test_closed_incident(tmp_path):
    db = make_db(tmp_path)
    ev(db, 0, "incident_started", source="detector404")
    ev(db, 5, "incident_confirmed", source="sboyrf")
    ev(db, 20, "incident_resolved")
    [incident] = analytics.incidents(db, at(60))
    assert (incident.service, incident.start, incident.end) == ("vtb", at(0), at(20))
    assert incident.sources == ["detector404", "sboyrf"]
    assert incident.minutes(at(60)) == 20


def test_open_incident_counts_to_now(tmp_path):
    db = make_db(tmp_path)
    ev(db, 0, "incident_started", source="detector404,sboyrf")
    [incident] = analytics.incidents(db, at(45))
    assert incident.end is None and incident.minutes(at(45)) == 45
    assert incident.sources == ["detector404", "sboyrf"]


def test_services_are_paired_separately(tmp_path):
    db = make_db(tmp_path)
    ev(db, 0, "incident_started", "vtb", "detector404")
    ev(db, 5, "incident_started", "invest", "downradar")
    ev(db, 10, "incident_resolved", "invest")
    ev(db, 30, "incident_resolved", "vtb")
    got = {i.service: (i.start, i.end) for i in analytics.incidents(db, at(60))}
    assert got == {"vtb": (at(0), at(30)), "invest": (at(5), at(10))}


def test_resolved_without_start_is_ignored(tmp_path):
    db = make_db(tmp_path)
    ev(db, 0, "incident_resolved")
    assert analytics.incidents(db, at(60)) == []


def test_peak_is_max_count_inside_the_incident(tmp_path):
    db = make_db(tmp_path)
    check(db, -10, "sboyrf", OK, 500)  # before: ignored
    ev(db, 0, "incident_started", source="sboyrf")
    check(db, 0, "sboyrf", OUTAGE, 60)
    check(db, 5, "downradar", OK, 75)
    check(db, 5, "downradar", OK, 90, service="invest")  # other service: ignored
    ev(db, 10, "incident_resolved")
    check(db, 15, "sboyrf", OK, 400)  # after: ignored
    assert analytics.incidents(db, at(60))[0].peak == 75


def test_bank_post_matches_by_time_and_service(tmp_path):
    db = make_db(tmp_path)
    ev(db, 0, "incident_started", source="detector404")
    ev(db, 30, "incident_resolved")
    post(db, -60, "Наблюдаются затруднения", post_id=1)            # too early
    post(db, 20, "Наблюдаются сбои в ВТБ Мои Инвестиции", post_id=2)  # other service
    post(db, 25, "Работа восстановлена", kind="recovery", post_id=3)  # not an outage post
    post(db, 40, "Наблюдаются затруднения в приложении", post_id=4)
    assert analytics.incidents(db, at(90))[0].post["id"] == 4


def test_no_bank_post_more_than_an_hour_later(tmp_path):
    db = make_db(tmp_path)
    ev(db, 0, "incident_started", source="detector404")
    post(db, 61, "Наблюдаются затруднения")
    assert analytics.incidents(db, at(90))[0].post is None
