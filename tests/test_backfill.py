import pytest
from datetime import datetime, timezone
from pathlib import Path

from monitor import backfill, history
from monitor.sources.base import OK, OUTAGE, SourceResult

pytestmark = pytest.mark.usefixtures("legacy_vtb")

FIXTURE = Path(__file__).parent / "fixtures" / "journal_sample.txt"


def line(ts, pid, service_source, status, details):
    return f"{ts} host python3[{pid}]: [{service_source}] {status} {details}"


def test_parse_groups_lines_into_runs():
    runs = backfill.parse_journal(FIXTURE.read_text(encoding="utf-8").splitlines())
    assert len(runs) == 2
    first_ts, first = runs[0]
    assert first_ts == datetime(2026, 10, 10, 4, 20, 43, tzinfo=timezone.utc)  # 11:20:43+07:00
    assert [r.source for r in first["vtb"]] == ["detector404", "downreport", "downradar", "sboyrf"]
    assert first["vtb"][0].status == OUTAGE
    assert first["vtb"][0].details == "сенсоры: недоступен в 1 городах"
    assert all(len(results["invest"]) == 3 for _, results in runs)


def test_parse_ignores_other_lines():
    lines = ["2026-10-10T11:20:03+07:00 host systemd[1]: Starting vtb-monitor.service",
             "2026-10-10T11:20:43+07:00 host python3[5]: Traceback (most recent call last):",
             "2026-10-10T11:20:43+07:00 host python3[5]: [telegram] OK последний пост #1"]
    assert backfill.parse_journal(lines) == []


def test_backfill_replays_incidents_and_stops_at_live_history(tmp_path):
    db = history.connect(tmp_path / "h.db")
    lines = [
        line("2026-10-10T11:20:43+07:00", 1, "vtb/detector404", "OUTAGE", "много жалоб пользователей"),
        line("2026-10-10T11:25:43+07:00", 2, "vtb/detector404", "OK", "сенсоры и жалобы в норме"),
        line("2026-10-10T11:30:43+07:00", 3, "vtb/detector404", "OK", "сенсоры и жалобы в норме"),
        line("2026-10-10T11:35:43+07:00", 4, "vtb/detector404", "OK", "сенсоры и жалобы в норме"),
    ]
    # live history started with the 4th run
    history.record_run(db, datetime(2026, 10, 10, 4, 35, 43, tzinfo=timezone.utc),
                       {"vtb": [SourceResult("detector404", OK)]}, [])
    assert backfill.backfill(db, lines) == 3
    assert db.execute("SELECT count(*) FROM checks").fetchone() == (4,)
    events = db.execute("SELECT ts, kind, source FROM events ORDER BY ts").fetchall()
    assert events == [("2026-10-10T04:20:43+00:00", "incident_started", "detector404"),
                      ("2026-10-10T04:30:43+00:00", "incident_resolved", "")]


def test_incident_open_at_the_end_is_closed(tmp_path):
    # the live history has its own state: an incident left open by the replay would never end
    db = history.connect(tmp_path / "h.db")
    lines = [line("2026-10-10T11:20:43+07:00", 1, "vtb/detector404", "OUTAGE", "много жалоб"),
             line("2026-10-10T11:25:43+07:00", 2, "vtb/detector404", "OUTAGE", "много жалоб")]
    backfill.backfill(db, lines)
    events = db.execute("SELECT ts, kind, text FROM events ORDER BY ts").fetchall()
    assert [(ts, kind) for ts, kind, _ in events] == [
        ("2026-10-10T04:20:43+00:00", "incident_started"),
        ("2026-10-10T04:25:43+00:00", "incident_resolved")]
    assert events[1][2] == "конец восстановленной истории"


def test_backfill_keeps_counts(tmp_path):
    db = history.connect(tmp_path / "h.db")
    backfill.backfill(db, [line("2026-10-10T11:20:43+07:00", 1, "vtb/sboyrf", "OK",
                                "жалоб за час: 1, за сегодня: 126")])
    assert db.execute("SELECT count FROM checks").fetchone() == (1,)
