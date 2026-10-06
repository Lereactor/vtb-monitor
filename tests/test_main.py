from datetime import datetime, timezone

import pytest

from monitor import main
from monitor import state as st
from monitor.sources.base import ERROR, OK, OUTAGE, SourceResult
from monitor.sources.telegram_channel import Post

NOW = datetime(2026, 10, 4, 6, 30, tzinfo=timezone.utc)  # 09:30 MSK


@pytest.fixture
def sources(monkeypatch):
    """results[(source, page)] = status; anything not set is OK."""
    results = {}
    tg = {"posts": [], "last_id": 100}
    monkeypatch.setattr(main, "sleep", lambda seconds: None)
    for module in (main.detector404, main.downreport, main.downradar, main.sboyrf):
        monkeypatch.setattr(module, "check",
                            lambda s, page, name=module.NAME: SourceResult(name, results.get((name, page), OK)))
    monkeypatch.setattr(main.telegram_channel, "check",
                        lambda last, s: (SourceResult("telegram", OK), tg["posts"], tg["last_id"]))
    return results, tg


def test_first_run_sends_heartbeat_and_saves_state(tmp_path, sources):
    sent = []
    main.run(tmp_path / "state.json", sent.extend, now=NOW)
    assert len(sent) == 1 and sent[0].startswith("☀️")
    saved = st.load_state(tmp_path / "state.json")
    assert saved["telegram_last_id"] == 100
    assert saved["last_heartbeat"] == "2026-10-04"


def test_outage_and_official_post(tmp_path, sources):
    results, tg = sources
    path = tmp_path / "state.json"
    main.run(path, lambda messages: None, now=NOW)
    results[("detector404", "bank-vtb")] = OUTAGE
    tg["posts"] = [Post(101, "Наблюдаются затруднения", "outage")]
    sent = []
    main.run(path, sent.extend, now=NOW)
    assert [m[0] for m in sent] == ["📢", "🔴"]


def test_broken_site_on_both_services_is_one_message(tmp_path, sources):
    results, tg = sources
    path = tmp_path / "state.json"
    main.run(path, lambda messages: None, now=NOW)
    results[("downradar", "vtb.ru")] = results[("downradar", "broker.vtb.ru")] = ERROR
    sent = []
    for _ in range(3):
        main.run(path, sent.extend, now=NOW)
    assert len(sent) == 1
    assert sent[0].startswith("⚠️ Перестал отвечать DownRadar (ВТБ, ВТБ Мои Инвестиции).")
    assert "✅ DETECTOR404, ✅ DownReport, ❌ DownRadar, ✅ СБОЙ.РФ, ✅ Telegram ВТБ" in sent[0]


def test_send_failure_keeps_state_unsaved(tmp_path, sources):
    path = tmp_path / "state.json"

    def broken(messages):
        raise RuntimeError("telegram down")

    with pytest.raises(RuntimeError):
        main.run(path, broken, now=NOW)
    assert not path.exists()


def test_crashing_source_is_isolated(tmp_path, sources, monkeypatch):
    def crash(s, page):
        raise ValueError("boom")

    monkeypatch.setattr(main.downreport, "check", crash)
    path = tmp_path / "state.json"
    main.run(path, lambda messages: None, now=NOW)
    saved = st.load_state(path)
    assert saved["services"]["vtb"]["sources"]["downreport"]["last"] == ERROR
    assert saved["services"]["vtb"]["sources"]["downradar"]["last"] == OK
    assert saved["services"]["invest"]["sources"]["downradar"]["last"] == OK
    assert saved["telegram_last_id"] == 100


def test_crash_details_are_truncated():
    def crash(s):
        raise ValueError("x" * 1000)

    result = main._safe_check("downreport", crash, None)
    assert result.status == ERROR
    assert result.details.startswith("внутренняя ошибка: ValueError: x")
    assert len(result.details) <= 200


def test_only_detectors_skips_channel(tmp_path, sources):
    results, tg = sources
    tg["posts"] = [Post(101, "Наблюдаются затруднения", "outage")]
    path = tmp_path / "state.json"
    sent = []
    main.run(path, sent.extend, now=NOW, channel=False)
    saved = st.load_state(path)
    assert "telegram" not in saved["services"]["vtb"]["sources"] and saved["telegram_last_id"] is None
    assert not any(m.startswith("📢") for m in sent)


def test_only_channel_skips_detectors(tmp_path, sources):
    path = tmp_path / "state.json"
    main.run(path, lambda messages: None, now=NOW, detectors=False)
    saved = st.load_state(path)
    assert set(saved["services"]) == {"vtb"}
    assert set(saved["services"]["vtb"]["sources"]) == {"telegram"}


def test_nothing_to_send_does_not_call_deliver(tmp_path, sources):
    path = tmp_path / "state.json"
    main.run(path, lambda messages: None, now=NOW)  # heartbeat sent here

    def must_not_call(messages):
        raise AssertionError(messages)

    main.run(path, must_not_call, now=NOW)


def test_invest_outage_is_separate(tmp_path, sources):
    results, tg = sources
    path = tmp_path / "state.json"
    main.run(path, lambda messages: None, now=NOW)
    results[("detector404", "vtbinvesticii")] = OUTAGE
    sent = []
    main.run(path, sent.extend, now=NOW)
    assert len(sent) == 1 and sent[0].startswith("🔴 ВТБ Мои Инвестиции: похоже на сбой")


def test_each_service_checks_its_pages(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "sleep", lambda seconds: calls.append(("pause", seconds)))
    for module in (main.detector404, main.downreport, main.downradar, main.sboyrf):
        monkeypatch.setattr(module, "check",
                            lambda s, page, name=module.NAME: calls.append((name, page)) or SourceResult(name, OK))
    main.run(tmp_path / "state.json", lambda messages: None, now=NOW, channel=False)
    assert calls == [("detector404", "bank-vtb"), ("downreport", "vtb"), ("downradar", "vtb.ru"),
                     ("sboyrf", "bank-vtb"), ("pause", 5), ("detector404", "vtbinvesticii"),
                     ("pause", 5), ("downreport", "vtb-investments"),
                     ("pause", 5), ("downradar", "broker.vtb.ru")]
