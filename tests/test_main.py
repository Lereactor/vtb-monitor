from datetime import datetime, timezone

import pytest

from monitor import main
from monitor import state as st
from monitor.sources.base import ERROR, OK, OUTAGE, SourceResult
from monitor.sources.telegram_channel import Post

NOW = datetime(2026, 10, 4, 6, 30, tzinfo=timezone.utc)  # 09:30 MSK


@pytest.fixture
def sources(monkeypatch):
    results = {"detector404": OK, "downreport": OK, "downradar": OK}
    tg = {"posts": [], "last_id": 100}
    monkeypatch.setattr(main.detector404, "check",
                        lambda token, s: SourceResult("detector404", results["detector404"]))
    monkeypatch.setattr(main.downreport, "check",
                        lambda s: SourceResult("downreport", results["downreport"]))
    monkeypatch.setattr(main.downradar, "check",
                        lambda s: SourceResult("downradar", results["downradar"]))
    monkeypatch.setattr(main.telegram_channel, "check",
                        lambda last, s: (SourceResult("telegram", OK), tg["posts"], tg["last_id"]))
    return results, tg


def test_first_run_sends_heartbeat_and_saves_state(tmp_path, sources):
    sent = []
    main.run(tmp_path / "state.json", sent.append, now=NOW)
    assert len(sent) == 1 and sent[0].startswith("💓")
    saved = st.load_state(tmp_path / "state.json")
    assert saved["telegram_last_id"] == 100
    assert saved["last_heartbeat"] == "2026-10-04"


def test_outage_and_official_post(tmp_path, sources):
    results, tg = sources
    path = tmp_path / "state.json"
    main.run(path, lambda text: None, now=NOW)
    results["detector404"] = OUTAGE
    tg["posts"] = [Post(101, "Наблюдаются затруднения", "outage")]
    sent = []
    main.run(path, sent.append, now=NOW)
    assert [m[0] for m in sent] == ["📢", "🔴"]


def test_send_failure_keeps_state_unsaved(tmp_path, sources):
    path = tmp_path / "state.json"

    def broken(text):
        raise RuntimeError("telegram down")

    with pytest.raises(RuntimeError):
        main.run(path, broken, now=NOW)
    assert not path.exists()


def test_crashing_source_is_isolated(tmp_path, sources, monkeypatch):
    def crash(s):
        raise ValueError("boom")

    monkeypatch.setattr(main.downreport, "check", crash)
    path = tmp_path / "state.json"
    main.run(path, lambda text: None, now=NOW)
    saved = st.load_state(path)
    assert saved["sources"]["downreport"]["last"] == ERROR
    assert saved["sources"]["downradar"]["last"] == OK
    assert saved["telegram_last_id"] == 100
