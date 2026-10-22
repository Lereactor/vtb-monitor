import json
from datetime import datetime, timezone

import pytest

from monitor import history, main
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
    results[("detector404", "vtbinvesticii")] = OUTAGE
    tg["posts"] = [Post(101, "Наблюдаются затруднения", "outage")]
    sent = []
    main.run(path, sent.extend, now=NOW)
    assert [m[0] for m in sent] == ["📢", "🔴"]


def test_broken_site_on_both_services_is_one_message(tmp_path, sources):
    results, tg = sources
    path = tmp_path / "state.json"
    main.run(path, lambda messages: None, now=NOW)
    results[("downradar", "db.vtb.ru")] = results[("downradar", "broker.vtb.ru")] = ERROR
    sent = []
    for _ in range(st.ERROR_ALERT_RUNS):
        main.run(path, sent.extend, now=NOW)
    assert len(sent) == 1
    assert sent[0].startswith("⚠️ Перестал отвечать DownRadar (ВТБ Бизнес-онлайн, ВТБ Мои Инвестиции).")
    assert "ВТБ Бизнес-онлайн: ✅ DownReport, ❌ DownRadar, ✅ Telegram ВТБ" in sent[0]


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
    assert saved["services"]["business"]["sources"]["downreport"]["last"] == ERROR
    assert saved["services"]["business"]["sources"]["downradar"]["last"] == OK
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
    assert "telegram" not in saved["services"]["business"]["sources"] and saved["telegram_last_id"] is None
    assert not any(m.startswith("📢") for m in sent)


def test_only_channel_skips_detectors(tmp_path, sources):
    path = tmp_path / "state.json"
    main.run(path, lambda messages: None, now=NOW, detectors=False)
    saved = st.load_state(path)
    assert set(saved["services"]) == {"business"}
    assert set(saved["services"]["business"]["sources"]) == {"telegram"}


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
    assert calls == [("downreport", "vtb-business-platform"), ("downradar", "db.vtb.ru"),
                     ("detector404", "vtbinvesticii"), ("pause", 5), ("downreport", "vtb-investments"),
                     ("pause", 5), ("downradar", "broker.vtb.ru")]


def test_history_is_recorded(tmp_path, sources):
    main.run(tmp_path / "state.json", lambda messages: None, now=NOW, channel=False,
             history_path=tmp_path / "h.db")
    db = history.connect(tmp_path / "h.db")
    assert db.execute("SELECT count(*) FROM checks").fetchone() == (5,)  # 2 Бизнес-онлайн + 3 Инвестиции
    assert db.execute("SELECT kind FROM events").fetchall() == [("message_sent",)]  # the heartbeat


def test_history_records_incident_events(tmp_path, sources):
    results, tg = sources
    path = tmp_path / "state.json"
    main.run(path, lambda messages: None, now=NOW, history_path=tmp_path / "h.db")
    results[("detector404", "vtbinvesticii")] = OUTAGE
    main.run(path, lambda messages: None, now=NOW, history_path=tmp_path / "h.db")
    kinds = history.connect(tmp_path / "h.db").execute("SELECT kind FROM events").fetchall()
    assert ("incident_started",) in kinds


def test_history_failure_does_not_block_alerts(tmp_path, sources, monkeypatch, capsys):
    def broken(*args):
        raise OSError("disk full")

    monkeypatch.setattr(main.history, "record_run", broken)
    sent = []
    main.run(tmp_path / "state.json", sent.extend, now=NOW, history_path=tmp_path / "h.db")
    assert sent
    assert "history: OSError: disk full" in capsys.readouterr().out
    assert (tmp_path / "state.json").exists()


def test_no_history_without_path(tmp_path, sources):
    main.run(tmp_path / "state.json", lambda messages: None, now=NOW)
    assert list(tmp_path.iterdir()) == [tmp_path / "state.json"]


def test_channel_run_saves_posts_next_to_state(tmp_path, sources):
    results, tg = sources
    path = tmp_path / "state.json"
    main.run(path, lambda messages: None, now=NOW)
    tg["posts"] = [Post(101, "Наблюдаются затруднения", "outage")]
    main.run(path, lambda messages: None, now=NOW)
    saved = json.loads((tmp_path / "posts.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in saved] == [101]


def test_history_imports_posts_when_github_is_configured(tmp_path, sources, monkeypatch):
    calls = []
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPO", "me/repo")
    monkeypatch.setattr(main.official_posts, "import_from_github", lambda db, token, repo: calls.append((token, repo)))
    main.run(tmp_path / "state.json", lambda messages: None, now=NOW, channel=False,
             history_path=tmp_path / "h.db")
    assert calls == [("tok", "me/repo")]


def site_env(monkeypatch, tmp_path, remote):
    import base64
    from monitor import sitecrypto
    salt = b"1" * 16
    monkeypatch.setenv("SITE_REMOTE", str(remote))
    monkeypatch.setenv("SITE_KEY", base64.b64encode(sitecrypto.derive_key("pw", salt, 1000)).decode())
    monkeypatch.setenv("SITE_SALT", base64.b64encode(salt).decode())
    monkeypatch.setenv("SITE_ITER", "1000")
    monkeypatch.setenv("SITE_WORK_DIR", str(tmp_path / "site-data"))


def test_site_is_published_after_the_run(tmp_path, sources, monkeypatch):
    import subprocess
    from monitor import sitecrypto
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    site_env(monkeypatch, tmp_path, remote)
    main.run(tmp_path / "state.json", lambda messages: None, now=NOW, channel=False,
             history_path=tmp_path / "h.db")
    show = lambda name: subprocess.run(["git", "--git-dir", str(remote), "show", f"data:{name}"],
                                       check=True, capture_output=True, encoding="utf-8").stdout
    public = json.loads(show("public.json"))
    assert public["now"]["business"]["total"] == 2
    private = sitecrypto.decrypt_json(json.loads(show("private.enc")), "pw")
    assert len(private["checks"]) == 5


def test_site_failure_does_not_block_alerts(tmp_path, sources, monkeypatch, capsys):
    site_env(monkeypatch, tmp_path, tmp_path / "no-such-remote.git")
    sent = []
    main.run(tmp_path / "state.json", sent.extend, now=NOW, channel=False, history_path=tmp_path / "h.db")
    assert sent and "site: CalledProcessError" in capsys.readouterr().out
    assert history.connect(tmp_path / "h.db").execute("SELECT count(*) FROM checks").fetchone() == (5,)


def reach(host, ru=(4, 4), world=(4, 4)):
    from monitor.availability import Point, Reach
    out = {}
    for region, (up, total) in (("ru", ru), ("world", world)):
        out[region] = Reach(host, region, [Point(f"п{i}", i < up, 100 if i < up else None, "HTTP 200")
                                           for i in range(total)])
    return out


def test_site_availability_goes_to_history_and_messages(tmp_path, sources, monkeypatch):
    results, tg = sources
    asked = []

    def check_sites(hosts, session):
        asked.extend(hosts)
        return {h: reach(h, ru=(0, 4)) if h == "invest.vtb.ru" else reach(h) for h in hosts}

    monkeypatch.setattr(main, "check_sites", check_sites)
    path = tmp_path / "state.json"
    sent = []
    main.run(path, sent.extend, now=NOW, channel=False, history_path=tmp_path / "h.db")
    assert asked == ["db.vtb.ru", "vtbbo.ru", "invest.vtb.ru"]
    assert "ВТБ Мои Инвестиции: сайты открываются: invest.vtb.ru ❌ Россия 0/4, ✅ мир 4/4." in sent[0]
    rows = history.connect(tmp_path / "h.db").execute(
        "SELECT service, host, region, up, total FROM reach ORDER BY rowid").fetchall()
    assert ("invest", "invest.vtb.ru", "ru", 0, 4) in rows and len(rows) == 6
    results[("detector404", "vtbinvesticii")] = OUTAGE
    sent = []
    main.run(path, sent.extend, now=NOW, channel=False)
    assert sent[0].startswith("🔴 ВТБ Мои Инвестиции: похоже на сбой")
    assert sent[0].endswith("Сайты открываются: invest.vtb.ru ❌ Россия 0/4, ✅ мир 4/4.")


def test_site_availability_failure_does_not_block_alerts(tmp_path, sources, monkeypatch):
    def broken(hosts, session):
        raise RuntimeError("check-host down")

    monkeypatch.setattr(main, "check_sites", broken)
    sent = []
    main.run(tmp_path / "state.json", sent.extend, now=NOW, channel=False)
    assert sent and "Сайты открываются" not in sent[0]


def test_site_down_alert_from_the_run(tmp_path, sources, monkeypatch):
    monkeypatch.setattr(main, "check_sites",
                        lambda hosts, session: {h: reach(h, ru=(0, 4) if h == "db.vtb.ru" else (4, 4)) for h in hosts})
    path = tmp_path / "state.json"
    main.run(path, lambda m: None, now=NOW, channel=False)
    sent = []
    main.run(path, sent.extend, now=NOW.replace(minute=35), channel=False, history_path=tmp_path / "h.db")
    assert [m.splitlines()[0] for m in sent] == ["🔴 ВТБ Бизнес-онлайн: db.vtb.ru не открывается из России (с 09:30 МСК)"]
    kinds = history.connect(tmp_path / "h.db").execute("SELECT kind, source FROM events").fetchall()
    assert ("site_down", "db.vtb.ru") in kinds


def test_low_disk_alert_from_the_run(tmp_path, sources, monkeypatch):
    monkeypatch.setattr(main, "_free_mb", lambda path: 300)
    sent = []
    main.run(tmp_path / "state.json", sent.extend, now=NOW, channel=False)
    assert any(m.startswith("⚠️ На сервере оповещателя осталось 300 МБ") for m in sent)
    sent = []
    main.run(tmp_path / "state.json", sent.extend, now=NOW, channel=False)
    assert sent == []


def test_guarded_reports_the_third_failure_in_a_row_and_recovery(tmp_path):
    counter = tmp_path / "failures"
    sent = []

    def broken():
        raise OSError(28, "No space left on device")

    for _ in range(4):
        with pytest.raises(OSError):
            main.guarded(broken, sent.extend, counter)
    assert len(sent) == 1 and sent[0].startswith("⚠️ Оповещатель ВТБ не работает")
    assert "уже 3 раза подряд" in sent[0] and "No space left on device" in sent[0]
    assert main.guarded(lambda: "ok", sent.extend, counter) == "ok"
    assert sent[-1] == "✅ Оповещатель ВТБ снова работает (ошибок подряд до этого: 4)."
    assert counter.read_text() == "0"
    main.guarded(lambda: "ok", sent.extend, counter)
    assert len(sent) == 2


def test_guarded_stays_quiet_on_a_single_failure(tmp_path):
    counter = tmp_path / "failures"
    sent = []
    with pytest.raises(RuntimeError):
        main.guarded(lambda: (_ for _ in ()).throw(RuntimeError("blip")), sent.extend, counter)
    main.guarded(lambda: None, sent.extend, counter)
    assert sent == []


def test_guarded_failure_alert_that_cannot_be_sent_still_raises(tmp_path, capsys):
    counter = tmp_path / "failures"
    counter.write_text("2")

    def deliver(messages):
        raise RuntimeError("GitHub down")

    with pytest.raises(ValueError):
        main.guarded(lambda: (_ for _ in ()).throw(ValueError("x")), deliver, counter)
    assert "failure alert not sent: RuntimeError" in capsys.readouterr().out


def test_weekly_report_is_started_once(tmp_path, sources):
    started = []
    path = tmp_path / "state.json"
    main.run(path, lambda m: None, now=NOW, channel=False, start_weekly=lambda: started.append(1))
    main.run(path, lambda m: None, now=NOW, channel=False, start_weekly=lambda: started.append(1))
    assert started == [1]


def test_weekly_report_failure_is_retried_and_does_not_block(tmp_path, sources, capsys):
    path = tmp_path / "state.json"

    def broken():
        raise RuntimeError("GitHub down")

    sent = []
    main.run(path, sent.extend, now=NOW, channel=False, start_weekly=broken)
    assert sent and "weekly report: RuntimeError: GitHub down" in capsys.readouterr().out
    started = []
    main.run(path, lambda m: None, now=NOW, channel=False, start_weekly=lambda: started.append(1))
    assert started == [1]
