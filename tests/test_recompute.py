from datetime import datetime, timedelta, timezone

from monitor import history, recompute
from monitor import state as st
from monitor.sources.base import OK, OUTAGE, SourceResult

T0 = datetime(2026, 10, 10, 4, 0, tzinfo=timezone.utc)
ONE_CITY = "сенсоры: недоступен в 1 городах"
COMPLAINTS = "много жалоб пользователей"


def at(minute):
    return T0 + timedelta(minutes=minute)


def checks(db):
    return db.execute("SELECT ts, status, details FROM checks ORDER BY ts").fetchall()


def kinds(db):
    return db.execute("SELECT ts, kind FROM events ORDER BY ts, rowid").fetchall()


def test_reclassify_detector404_sensors():
    assert recompute.reclassify("detector404", OUTAGE, ONE_CITY) == (OK, ONE_CITY + " (без жалоб — не тревога)")
    two = "сенсоры: недоступен в 2 городах"
    assert recompute.reclassify("detector404", OUTAGE, two) == (OK, two + " (без жалоб — не тревога)")
    assert recompute.reclassify("detector404", OUTAGE, COMPLAINTS) == (OUTAGE, COMPLAINTS)
    assert recompute.reclassify("detector404", OK, "сенсоры и жалобы в норме") == (OK, "сенсоры и жалобы в норме")
    both = ONE_CITY + "; много жалоб пользователей"
    assert recompute.reclassify("detector404", OUTAGE, both) == (OUTAGE, both)
    assert recompute.reclassify("sboyrf", OUTAGE, "жалоб за час: 1") == (OUTAGE, "жалоб за час: 1")


def test_one_city_incident_disappears(tmp_path):
    db = history.connect(tmp_path / "h.db")
    for minute, status, details in [(0, OUTAGE, ONE_CITY), (5, OK, ""), (10, OK, "")]:
        events = [st.Event("incident_started", "vtb", "detector404", "🔴")] if minute == 0 else []
        if minute == 10:
            events = [st.Event("incident_resolved", "vtb", "", "✅"), st.Event("message_sent", "", "", "✅")]
        history.record_run(db, at(minute), {"vtb": [SourceResult("detector404", status, details)]}, events)
    recompute.recompute(db, st.new_state())
    assert checks(db)[0][1:] == (OK, ONE_CITY + " (без жалоб — не тревога)")
    assert kinds(db) == [(history.iso(at(10)), "message_sent")]  # what was sent stays


def test_replay_uses_current_rules(tmp_path):
    # СБОЙ.РФ alone no longer opens an incident; DETECTOR404 complaints do at once
    db = history.connect(tmp_path / "h.db")
    for minute, status in [(0, OUTAGE), (5, OK), (10, OK)]:
        history.record_run(db, at(minute), {"vtb": [SourceResult("sboyrf", OUTAGE, "жалоб за час: 260"),
                                                    SourceResult("detector404", status, COMPLAINTS)]}, [])
    recompute.recompute(db, st.new_state())
    assert kinds(db) == [(history.iso(at(0)), "incident_started"), (history.iso(at(10)), "incident_resolved")]
    assert db.execute("SELECT source FROM events WHERE kind = 'incident_started'").fetchone() == ("detector404",)


def test_incident_open_only_in_replay_is_closed(tmp_path):
    db = history.connect(tmp_path / "h.db")
    history.record_run(db, at(0), {"vtb": [SourceResult("detector404", OUTAGE, COMPLAINTS)]}, [])
    recompute.recompute(db, st.new_state())  # live state: no incident
    rows = db.execute("SELECT kind, text FROM events ORDER BY rowid").fetchall()
    assert rows[-1] == ("incident_resolved", recompute.RECOMPUTE_END)


def test_incident_open_only_live_is_started(tmp_path):
    db = history.connect(tmp_path / "h.db")
    history.record_run(db, at(0), {"vtb": [SourceResult("sboyrf", OK, "жалоб за час: 1")]}, [])
    live = st.new_state()
    st.service(live, "vtb")["incident"] = {"started_at": at(-20).isoformat(), "sources": ["downradar"]}
    recompute.recompute(db, live)
    assert db.execute("SELECT ts, kind, service, source FROM events").fetchall() == [
        (history.iso(at(-20)), "incident_started", "vtb", "downradar")]


def test_incident_open_in_both_stays_open(tmp_path):
    db = history.connect(tmp_path / "h.db")
    history.record_run(db, at(0), {"vtb": [SourceResult("detector404", OUTAGE, COMPLAINTS)]}, [])
    live = st.new_state()
    st.service(live, "vtb")["incident"] = {"started_at": at(0).isoformat(), "sources": ["detector404"]}
    recompute.recompute(db, live)
    assert [k for _, k in kinds(db)] == ["incident_started"]
