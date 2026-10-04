from datetime import datetime, timedelta, timezone

from monitor import state as st
from monitor.sources.base import DISABLED, ERROR, OK, OUTAGE, SourceResult

T0 = datetime(2026, 10, 4, 11, 0, tzinfo=timezone.utc)


def R(source, status, details="d"):
    return SourceResult(source, status, details, "https://u")


def run(state, *results, minute=0):
    return st.process(state, list(results), T0 + timedelta(minutes=minute))


def test_crowd_source_needs_two_runs():
    state = st.new_state()
    assert run(state, R("downradar", OUTAGE)) == []
    messages = run(state, R("downradar", OUTAGE), minute=5)
    assert len(messages) == 1 and messages[0].startswith("🔴")
    assert state["incident"]["sources"] == ["downradar"]


def test_single_crowd_spike_is_ignored():
    state = st.new_state()
    run(state, R("downradar", OUTAGE))
    assert run(state, R("downradar", OK), minute=5) == []
    assert state["incident"] is None


def test_detector404_is_immediate():
    messages = run(st.new_state(), R("detector404", OUTAGE))
    assert messages[0].startswith("🔴")


def test_second_source_confirms():
    state = st.new_state()
    run(state, R("detector404", OUTAGE), R("downreport", OUTAGE))
    messages = run(state, R("detector404", OUTAGE), R("downreport", OUTAGE), minute=5)
    assert len(messages) == 1
    assert messages[0].startswith("➕ ВТБ: сбой подтверждает DownReport (2 из 2")


def test_recovery_after_two_calm_runs():
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    assert run(state, R("detector404", OK), minute=5) == []
    messages = run(state, R("detector404", OK), minute=10)
    assert messages[0].startswith("🟢") and "10 мин" in messages[0]
    assert state["incident"] is None


def test_outage_returning_resets_recovery():
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    run(state, R("detector404", OK), minute=5)
    run(state, R("detector404", OUTAGE), minute=10)
    assert run(state, R("detector404", OK), minute=15) == []
    assert state["incident"] is not None


def test_source_error_reported_once_after_three_runs():
    state = st.new_state()
    assert run(state, R("downreport", ERROR, "HTTP 403")) == []
    assert run(state, R("downreport", ERROR, "HTTP 403")) == []
    messages = run(state, R("downreport", ERROR, "HTTP 403"))
    assert messages == ["⚙️ DownReport не отвечает (HTTP 403). Сигналы этого источника не учитываются."]
    assert run(state, R("downreport", ERROR)) == []
    assert run(state, R("downreport", OK)) == ["⚙️ DownReport снова работает"]


def test_erroring_source_keeps_incident_open():
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    run(state, R("detector404", ERROR), minute=5)
    run(state, R("detector404", ERROR), minute=10)
    assert state["incident"] is not None


def test_telegram_does_not_open_incident():
    state = st.new_state()
    run(state, R("telegram", OK))
    assert state["incident"] is None and state["sources"]["telegram"]["last"] == OK


def test_disabled_source_is_recorded_but_ignored():
    state = st.new_state()
    assert run(state, R("detector404", DISABLED)) == []
    assert state["sources"]["detector404"]["last"] == DISABLED


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
