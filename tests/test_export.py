import json
from datetime import datetime, timedelta, timezone

from monitor import export, history
from monitor import state as st
from monitor.sources.base import ERROR, OK, OUTAGE, SourceResult

NOW = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)


def at(hours):
    return NOW + timedelta(hours=hours)


def live_state():
    state = st.new_state()
    vtb = st.service(state, "vtb")
    vtb["incident"] = {"started_at": at(-1).isoformat(), "sources": ["sboyrf"]}
    vtb["sources"] = {"sboyrf": {"last": OUTAGE, "confirmed": OUTAGE},
                      "downradar": {"last": ERROR, "confirmed": OK, "error_reported": True},
                      "detector404": {"last": OK, "confirmed": OK}}
    return state


def build(tmp_path):
    db = history.connect(tmp_path / "h.db")
    history.record_run(db, at(-24 * 3), {"vtb": [SourceResult("sboyrf", OK, "жалоб за час: 2")]}, [])
    history.record_run(db, at(-1), {"vtb": [SourceResult("sboyrf", OUTAGE, "жалоб за час: 60"),
                                            SourceResult("downradar", ERROR, "сеть: ReadTimeout")]},
                       [st.Event("incident_started", "vtb", "sboyrf", "🔴 ВТБ: похоже на сбой"),
                        st.Event("message_sent", "", "", "🔴 ВТБ: похоже на сбой")])
    history.record_run(db, at(-24 * 20), {"vtb": [SourceResult("downradar", ERROR, "HTTP 500")]},
                       [st.Event("source_down", "vtb", "downradar", "HTTP 500")])
    return export.build(db, live_state(), NOW)


def test_now_block(tmp_path):
    public, _ = build(tmp_path)
    vtb = public["now"]["vtb"]
    assert vtb["incident"] == {"start": history.iso(at(-1)), "sources": ["sboyrf"]}
    sources = vtb["sources"]
    assert sources["sboyrf"]["status"] == "outage" and sources["sboyrf"]["count"] == 60
    assert sources["downradar"]["status"] == "broken"
    assert sources["detector404"]["status"] == "ok"
    assert sources["sboyrf"]["checked_at"] == history.iso(at(-1))
    assert vtb["working"] == 2 and vtb["total"] == 4


def test_spark_covers_the_last_24_hours(tmp_path):
    public, _ = build(tmp_path)
    assert public["now"]["vtb"]["sources"]["sboyrf"]["spark"] == [[history.iso(at(-1)), 60, OUTAGE]]


def test_incidents_newest_first_with_analytics(tmp_path):
    public, _ = build(tmp_path)
    [incident] = public["incidents"]
    assert incident["service"] == "vtb" and incident["end"] is None and incident["solo"] is True
    assert incident["minutes"] == 60 and incident["peak"] == 60
    assert "24h|vtb" in public["analytics"]
    assert public["generated_at"] == history.iso(NOW)
    assert public["services"]["vtb"]["sources"][0] == {"id": "detector404", "title": "DETECTOR404"}


def test_private_part(tmp_path):
    _, private = build(tmp_path)
    # all checks of the last 48 h, plus non-OK checks of the last 30 days; newest first
    assert [row[0] for row in private["checks"]] == [history.iso(at(-1))] * 2 + [history.iso(at(-24 * 20))]
    assert private["checks"][0][1:] == ["vtb", "sboyrf", OUTAGE, 60, "жалоб за час: 60"]
    assert private["messages"] == [[history.iso(at(-1)), "🔴 ВТБ: похоже на сбой"]]
    assert private["source_events"] == [[history.iso(at(-24 * 20)), "source_down", "vtb", "downradar", "HTTP 500"]]


def test_public_holds_nothing_private(tmp_path):
    public, _ = build(tmp_path)
    text = json.dumps(public, ensure_ascii=False)
    assert "checks" not in public and "messages" not in public
    assert "HTTP 500" not in text  # old error details only in the private part
