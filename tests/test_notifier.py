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
    text = notifier.incident_started(STATE, "vtb", ["downradar"], NOW)
    assert text.startswith("🔴 ВТБ: возможный сбой")
    assert "Источник: DownRadar" in text
    assert "жалоб за час: 87" in text
    assert "14:50 МСК" in text
    assert "🔴 DownRadar" in text and "🟢 DownReport" in text


def test_incident_confirmed_counts_enabled_detectors():
    text = notifier.incident_confirmed(STATE, "vtb", "downradar", 1)
    assert text.startswith("➕ ВТБ: сбой подтверждает DownRadar (1 из 2 детекторов)")


def test_incident_resolved_duration():
    text = notifier.incident_resolved(STATE, "vtb", NOW)
    assert "47 мин" in text and "14:03" in text and "14:50" in text


def test_source_messages():
    result = SourceResult("downreport", ERROR, "HTTP 403")
    assert notifier.source_down("vtb", result) == ("⚙️ ВТБ · DownReport не отвечает (HTTP 403). "
                                                   "Сигналы этого источника не учитываются.")
    assert notifier.source_back("invest", result) == "⚙️ ВТБ Мои Инвестиции · DownReport снова работает"


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
        "🔴 ВТБ Мои Инвестиции: возможный сбой")
    assert notifier.incident_resolved(STATE, "invest", NOW).startswith(
        "🟢 ВТБ Мои Инвестиции: сбой завершён")


def test_heartbeat_lists_each_service():
    state = {"services": {"vtb": STATE,
                          "invest": {"sources": {"detector404": src(OK), "downradar": src(ERROR)},
                                     "incident": None}}}
    assert notifier.heartbeat(state) == (
        "💓 Оповещатель ВТБ работает\n\n"
        "ВТБ:\n🟢 DownReport\n🔴 DownRadar\n🟢 Telegram ВТБ\n\n"
        "ВТБ Мои Инвестиции:\n🟢 DETECTOR404\n⚙️ DownRadar")


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
