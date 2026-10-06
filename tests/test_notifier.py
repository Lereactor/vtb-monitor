import json
from datetime import datetime, timezone

import pytest

from monitor import notifier
from monitor.sources.base import ERROR, OK, OUTAGE, SourceResult
from monitor.sources.telegram_channel import Post
from tests.fakes import FakeResp, FakeSession

NOW = datetime(2026, 10, 4, 11, 50, tzinfo=timezone.utc)  # 14:50 MSK


def src(last, details="", url="https://u"):
    return {"last": last, "confirmed": last, "details": details, "url": url}


STATE = {
    "sources": {"downradar": src(OUTAGE, "есть проблемы, жалоб за час: 87"),
                "downreport": src(OK), "telegram": src(OK)},
    "incident": {"started_at": "2026-10-04T11:03:00+00:00", "sources": ["downradar"]},
}


def test_incident_started():
    assert notifier.incident_started(STATE, "vtb", ["downradar"], NOW) == (
        "🔴 ВТБ: похоже на сбой (14:50 МСК)\n"
        "DownRadar: есть проблемы, жалоб за час: 87\n"
        "https://u\n"
        "Сбой видят сайтов: 1 из 2.\n"
        "Пока только один сайт — возможна ложная тревога.")


def test_incident_confirmed():
    assert notifier.incident_confirmed(STATE, "vtb", "downradar", 1) == (
        "🔴 ВТБ: сбой подтверждает ещё один сайт\n"
        "DownRadar: есть проблемы, жалоб за час: 87\n"
        "https://u\n"
        "Сбой видят сайтов: 1 из 2.")


def test_tally_leaves_out_broken_sites():
    svc = {**STATE, "sources": {**STATE["sources"],
                                "downreport": {**src(ERROR), "error_reported": True}}}
    assert "сайтов: 1 из 1." in notifier.incident_confirmed(svc, "vtb", "downradar", 1)


def test_incident_resolved():
    assert notifier.incident_resolved(STATE, "vtb", NOW) == (
        "✅ ВТБ: всё в норме\nСбой длился 47 мин (14:03–14:50 МСК).")


def test_source_log_lines():
    result = SourceResult("downreport", ERROR, "HTTP 403")
    assert notifier.source_down("vtb", result) == "ВТБ · DownReport не отвечает (HTTP 403)"
    assert notifier.source_back("invest", result) == "ВТБ Мои Инвестиции · DownReport снова отвечает"


def test_official_post():
    text = notifier.official_post(Post(12, "Наблюдаются затруднения", "outage"))
    assert text.startswith("📢 ВТБ официально сообщает о проблемах")
    assert "«Наблюдаются затруднения»" in text
    assert "https://t.me/bankvtb/12" in text


def test_official_post_about_investments_is_tagged():
    text = notifier.official_post(Post(13, "Наблюдаются сбои в приложении ВТБ Мои Инвестиции", "outage"))
    assert text.startswith("📢 ВТБ официально сообщает о проблемах (Мои Инвестиции)")


def test_incident_titles_name_the_service():
    assert notifier.incident_started(STATE, "invest", ["downradar"], NOW).startswith(
        "🔴 ВТБ Мои Инвестиции: похоже на сбой")
    assert notifier.incident_resolved(STATE, "invest", NOW).startswith(
        "✅ ВТБ Мои Инвестиции: всё в норме")


BROKEN = {**src(ERROR), "error_reported": True}
# a one-off error (detector404 here) is still ✅: only checks written off after several failures are ❌
TWO_SERVICES = {"services": {
    "invest": {"sources": {"detector404": src(ERROR), "downradar": BROKEN}, "incident": None},
    "vtb": {"sources": {"downradar": BROKEN, "sboyrf": src(OK), "detector404": src(OK)},
            "incident": None},
}}


def test_heartbeat_when_all_is_well():
    state = {"services": {"vtb": {"sources": {"downradar": src(OK)}, "incident": None}}}
    assert notifier.heartbeat(state) == (
        "☀️ Оповещатель ВТБ работает, проверяет каждые 5 минут.\n\n"
        "Проверки:\nВТБ: ✅ DownRadar\n\n"
        "Сбоев сейчас нет.")


def test_heartbeat_names_open_incidents():
    state = {"services": {"vtb": STATE}}
    assert notifier.heartbeat(state) == (
        "☀️ Оповещатель ВТБ работает, проверяет каждые 5 минут.\n\n"
        "Проверки:\nВТБ: ✅ DownReport, ✅ DownRadar, ✅ Telegram ВТБ\n\n"
        "Сейчас идёт сбой: ВТБ (с 14:03 МСК).")


def test_sources_changed_shows_every_check():
    events = [("vtb", "downradar", True), ("invest", "downradar", True)]
    assert notifier.sources_changed(TWO_SERVICES, events) == (
        "⚠️ Перестал отвечать DownRadar (ВТБ, ВТБ Мои Инвестиции).\n"
        "Это сайт со статистикой жалоб, а не сам банк. Следим по остальным.\n\n"
        "Проверки:\n"
        "ВТБ: ✅ DETECTOR404, ❌ DownRadar, ✅ СБОЙ.РФ\n"
        "ВТБ Мои Инвестиции: ✅ DETECTOR404, ❌ DownRadar\n\n"
        "Сбоев сейчас нет.")


def test_sources_changed_on_recovery():
    state = {"services": {"vtb": {"sources": {"downradar": src(OK), "sboyrf": src(OK)},
                                  "incident": None}}}
    assert notifier.sources_changed(state, [("vtb", "downradar", False)]) == (
        "✅ Снова отвечает DownRadar (ВТБ).\n\n"
        "Проверки:\nВТБ: ✅ DownRadar, ✅ СБОЙ.РФ\n\n"
        "Сбоев сейчас нет.")


def test_sources_changed_for_the_channel():
    state = {"services": {"vtb": {"sources": {"telegram": BROKEN}, "incident": None}}}
    assert notifier.sources_changed(state, [("vtb", "telegram", True)]).startswith(
        "⚠️ Перестал отвечать Telegram ВТБ (ВТБ).\nПока не видим новых официальных постов ВТБ.\n")


def test_send_posts_to_bot_api():
    session = FakeSession(FakeResp(200, "{}"))
    notifier.send("TOKEN", "42", "привет", session)
    method, url, payload = session.calls[0]
    assert url == "https://api.telegram.org/botTOKEN/sendMessage"
    assert payload == {"chat_id": "42", "text": "привет", "disable_web_page_preview": True}


def test_send_failure_raises():
    with pytest.raises(RuntimeError, match="500"):
        notifier.send("T", "1", "x", FakeSession(FakeResp(500, "Internal Server Error")))


def test_send_bad_request_is_logged_not_raised(capsys):
    notifier.send("T", "1", "x", FakeSession(FakeResp(400, "Bad Request: message is too long")))
    assert "400" in capsys.readouterr().out


def test_send_clamps_long_text():
    session = FakeSession(FakeResp(200, "{}"))
    notifier.send("T", "1", "я" * 5000, session)
    text = session.calls[0][2]["text"]
    assert len(text) == 4000 and text.endswith("…")


def test_send_keeps_text_at_limit():
    session = FakeSession(FakeResp(200, "{}"))
    notifier.send("T", "1", "я" * 4000, session)
    assert session.calls[0][2]["text"] == "я" * 4000


def test_send_setup_error_400_raises():
    with pytest.raises(RuntimeError, match="chat not found"):
        notifier.send("T", "1", "x", FakeSession(FakeResp(400, "Bad Request: chat not found")))


def test_dispatch_github_posts_messages_as_json_input():
    session = FakeSession(FakeResp(204))
    notifier.dispatch_github("ghtok", "me/repo", ["🔴 сбой", "x" * 5000], session)
    method, url, payload = session.calls[0]
    assert url == "https://api.github.com/repos/me/repo/actions/workflows/notify.yml/dispatches"
    assert session.headers["Authorization"] == "Bearer ghtok"
    assert payload["ref"] == "main"
    messages = json.loads(payload["inputs"]["messages"])
    assert messages[0] == "🔴 сбой" and len(messages[1]) == 4000


def test_dispatch_github_failure_raises():
    with pytest.raises(RuntimeError, match="401"):
        notifier.dispatch_github("bad", "me/repo", ["x"], FakeSession(FakeResp(401, "Bad credentials")))
