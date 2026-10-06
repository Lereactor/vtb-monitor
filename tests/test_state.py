from datetime import datetime, timedelta, timezone

from monitor import state as st
from monitor.sources.base import DISABLED, ERROR, OK, OUTAGE, SourceResult

T0 = datetime(2026, 10, 4, 11, 0, tzinfo=timezone.utc)


def R(source, status, details="d"):
    return SourceResult(source, status, details, "https://u")


def run(state, *results, minute=0):
    return st.process(state, "vtb", list(results), T0 + timedelta(minutes=minute))


def V(state):
    return state["services"]["vtb"]


def test_crowd_source_needs_two_runs():
    state = st.new_state()
    assert run(state, R("downradar", OUTAGE)) == []
    messages = run(state, R("downradar", OUTAGE), minute=5)
    assert len(messages) == 1 and messages[0].startswith("🔴")
    assert V(state)["incident"]["sources"] == ["downradar"]


def test_single_crowd_spike_is_ignored():
    state = st.new_state()
    run(state, R("downradar", OUTAGE))
    assert run(state, R("downradar", OK), minute=5) == []
    assert V(state)["incident"] is None


def test_detector404_is_immediate():
    messages = run(st.new_state(), R("detector404", OUTAGE))
    assert messages[0].startswith("🔴")


def test_second_source_confirms():
    state = st.new_state()
    run(state, R("detector404", OUTAGE), R("downreport", OUTAGE))
    messages = run(state, R("detector404", OUTAGE), R("downreport", OUTAGE), minute=5)
    assert len(messages) == 1
    assert messages[0].startswith("🔴 ВТБ: сбой подтверждает ещё один сайт\nDownReport")
    assert "Сбой видят сайтов: 2 из 2." in messages[0]


def test_confirm_count_is_current_not_historical():
    state = st.new_state()
    run(state, R("detector404", OUTAGE), R("downreport", OK), R("downradar", OK))
    run(state, R("detector404", OUTAGE), R("downreport", OK), R("downradar", OUTAGE), minute=5)
    messages = run(state, R("detector404", OK), R("downreport", OUTAGE), R("downradar", OUTAGE),
                   minute=10)
    assert messages == [m for m in messages if "DownReport" in m and "сайтов: 2 из 3." in m]
    assert len(messages) == 1


def test_recovery_after_two_calm_runs():
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    assert run(state, R("detector404", OK), minute=5) == []
    messages = run(state, R("detector404", OK), minute=10)
    assert messages[0].startswith("✅") and "10 мин" in messages[0]
    assert V(state)["incident"] is None


def test_outage_returning_resets_recovery():
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    run(state, R("detector404", OK), minute=5)
    run(state, R("detector404", OUTAGE), minute=10)
    assert run(state, R("detector404", OK), minute=15) == []
    assert V(state)["incident"] is not None


def test_broken_source_is_logged_not_sent(capsys):
    # a monitoring site being down is not news for the chat: it goes to the log and the heartbeat
    state = st.new_state()
    assert run(state, R("downreport", ERROR, "HTTP 403")) == []
    assert run(state, R("downreport", ERROR, "HTTP 403")) == []
    assert run(state, R("downreport", ERROR, "HTTP 403")) == []
    assert capsys.readouterr().out == "ВТБ · DownReport не отвечает (HTTP 403)\n"
    assert V(state)["sources"]["downreport"]["error_reported"]
    assert run(state, R("downreport", ERROR)) == []
    assert capsys.readouterr().out == ""
    assert run(state, R("downreport", OK)) == []
    assert capsys.readouterr().out == "ВТБ · DownReport снова отвечает\n"


def test_broken_and_restored_source_is_an_event():
    state = st.new_state()
    events = []
    for minute in (0, 5, 10, 15):
        st.process(state, "vtb", [R("downreport", ERROR)], T0 + timedelta(minutes=minute), events)
    assert events == [("vtb", "downreport", True)]
    st.process(state, "vtb", [R("downreport", OK)], T0 + timedelta(minutes=20), events)
    assert events == [("vtb", "downreport", True), ("vtb", "downreport", False)]


def test_erroring_source_keeps_incident_open():
    # within the first 2 error runs the source is not yet written off
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    run(state, R("detector404", ERROR), minute=5)
    run(state, R("detector404", ERROR), minute=10)
    assert V(state)["incident"] is not None


def test_flapping_crowd_source_keeps_one_incident():
    state = st.new_state()
    sent = []
    for i, status in enumerate([OUTAGE, OUTAGE, OK, OUTAGE, OUTAGE, OK, OUTAGE, OUTAGE]):
        sent += run(state, R("downradar", status), minute=5 * i)
    assert [m[0] for m in sent] == ["🔴"]
    assert run(state, R("downradar", OK), minute=40) == []
    assert V(state)["incident"] is not None
    messages = run(state, R("downradar", OK), minute=45)
    assert messages[0].startswith("✅")
    assert V(state)["incident"] is None


def test_outage_during_incident_survives_short_errors():
    # latest non-error result is OUTAGE -> still in outage while the source blips
    state = st.new_state()
    run(state, R("downradar", OUTAGE))
    run(state, R("downradar", OUTAGE), minute=5)
    run(state, R("downradar", OK), minute=10)
    run(state, R("downradar", OUTAGE), minute=15)
    assert run(state, R("downradar", ERROR), minute=20) == []
    assert run(state, R("downradar", ERROR), minute=25) == []
    assert V(state)["incident"] is not None


def test_written_off_source_closes_incident():
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    sent = []
    for i in range(1, 6):
        sent += run(state, R("detector404", ERROR, "HTTP 500"), minute=5 * i)
    assert V(state)["incident"] is None
    resolved = [m for m in sent if m.startswith("✅")]
    assert len(resolved) == 1
    assert V(state)["sources"]["detector404"]["confirmed"] == OK


def test_disabled_source_closes_incident():
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    run(state, R("detector404", DISABLED), minute=5)
    messages = run(state, R("detector404", DISABLED), minute=10)
    assert messages[0].startswith("✅")
    assert V(state)["incident"] is None
    assert V(state)["sources"]["detector404"]["confirmed"] == OK


def test_resolved_when_detector404_disabled():
    state = st.new_state()
    run(state, R("detector404", DISABLED), R("downradar", OUTAGE))
    run(state, R("detector404", DISABLED), R("downradar", OUTAGE), minute=5)
    run(state, R("detector404", DISABLED), R("downradar", OK), minute=10)
    messages = run(state, R("detector404", DISABLED), R("downradar", OK), minute=15)
    assert messages[0].startswith("✅")


def test_error_resets_crowd_outage_streak():
    state = st.new_state()
    run(state, R("downradar", OUTAGE))
    run(state, R("downradar", ERROR), minute=5)
    assert run(state, R("downradar", OUTAGE), minute=10) == []
    assert V(state)["sources"]["downradar"]["confirmed"] == OK
    assert V(state)["incident"] is None


def test_telegram_does_not_open_incident():
    state = st.new_state()
    run(state, R("telegram", OK))
    assert V(state)["incident"] is None and V(state)["sources"]["telegram"]["last"] == OK


def test_disabled_source_is_recorded_but_ignored():
    state = st.new_state()
    assert run(state, R("detector404", DISABLED)) == []
    assert V(state)["sources"]["detector404"]["last"] == DISABLED


def test_heartbeat_due():
    state = st.new_state()
    assert st.heartbeat_due(state, datetime(2026, 10, 4, 6, 30, tzinfo=timezone.utc))  # 09:30 MSK
    assert not st.heartbeat_due(state, datetime(2026, 10, 4, 5, 0, tzinfo=timezone.utc))  # 08:00 MSK
    state["last_heartbeat"] = "2026-10-04"
    assert not st.heartbeat_due(state, datetime(2026, 10, 4, 6, 30, tzinfo=timezone.utc))


def test_save_and_load_roundtrip(tmp_path):
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    path = tmp_path / "state.json"
    st.save_state(path, state)
    assert st.load_state(path) == state
    assert st.load_state(tmp_path / "missing.json") == st.new_state()


def test_load_garbage_json_starts_fresh(tmp_path, capsys):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    assert st.load_state(path) == st.new_state()
    assert "state" in capsys.readouterr().out.lower()


def test_load_repairs_bad_sources_and_incident(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"sources": [1, 2], "incident": {}}', encoding="utf-8")
    state = st.load_state(path)
    assert V(state)["sources"] == {} and V(state)["incident"] is None
    assert run(state, R("detector404", OK)) == []


def test_source_entry_missing_keys(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"sources": {"downreport": {"last": "OK"}, "downradar": {}}}',
                    encoding="utf-8")
    state = st.load_state(path)
    run(state, R("downreport", ERROR), R("downradar", OUTAGE))
    run(state, R("downreport", ERROR), R("downradar", OUTAGE), minute=5)
    assert V(state)["sources"]["downreport"]["error_streak"] == 2
    assert V(state)["incident"] is not None


def test_ok_details_do_not_churn_state(tmp_path):
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    state = st.new_state()
    run(state, R("downradar", OK, "нет проблем, жалоб за час: 1"))
    st.save_state(first, state)
    run(state, R("downradar", OK, "нет проблем, жалоб за час: 7"), minute=5)
    st.save_state(second, state)
    assert first.read_bytes() == second.read_bytes()


def test_outage_details_are_kept():
    state = st.new_state()
    run(state, R("downradar", OUTAGE, "есть проблемы, жалоб за час: 87"))
    assert V(state)["sources"]["downradar"]["details"] == "есть проблемы, жалоб за час: 87"
    assert V(state)["sources"]["downradar"]["url"] == "https://u"
    run(state, R("downradar", OK, "нет проблем"), minute=5)
    assert V(state)["sources"]["downradar"]["details"] == ""
    assert V(state)["sources"]["downradar"]["url"] == ""


def test_persistent_error_stops_changing_state(tmp_path):
    state = st.new_state()
    for minute in range(0, 25, 5):
        run(state, R("downradar", ERROR, "HTTP 403"), minute=minute)
    st.save_state(tmp_path / "a.json", state)
    run(state, R("downradar", ERROR, "HTTP 403"), minute=30)
    st.save_state(tmp_path / "b.json", state)
    assert (tmp_path / "a.json").read_text(encoding="utf-8") == (tmp_path / "b.json").read_text(encoding="utf-8")


def test_old_single_service_state_moves_under_vtb(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"incident": {"started_at": "2026-10-05T09:05:00+00:00", "sources": ["downradar"]},'
                    ' "recovery_streak": 1, "sources": {"downradar": {"last": "OUTAGE"}},'
                    ' "telegram_last_id": 7, "last_heartbeat": "2026-10-05"}', encoding="utf-8")
    state = st.load_state(path)
    assert set(state) == {"services", "telegram_last_id", "last_heartbeat"}
    assert V(state)["incident"]["sources"] == ["downradar"]
    assert V(state)["recovery_streak"] == 1
    assert V(state)["sources"]["downradar"]["last"] == OUTAGE
    assert state["telegram_last_id"] == 7


def test_services_have_separate_incidents():
    state = st.new_state()
    messages = st.process(state, "invest", [R("detector404", OUTAGE)], T0)
    assert messages[0].startswith("🔴 ВТБ Мои Инвестиции: похоже на сбой")
    assert run(state, R("detector404", OK)) == []
    assert V(state)["incident"] is None
    assert state["services"]["invest"]["incident"] is not None


def test_invest_confirmation_counts_its_own_detectors():
    state = st.new_state()
    st.process(state, "invest", [R("detector404", OUTAGE), R("downradar", OUTAGE)], T0)
    messages = st.process(state, "invest", [R("detector404", OUTAGE), R("downradar", OUTAGE)],
                          T0 + timedelta(minutes=5))
    assert messages == ["🔴 ВТБ Мои Инвестиции: сбой подтверждает ещё один сайт\n"
                        "DownRadar: d\nhttps://u\nСбой видят сайтов: 2 из 2."]
