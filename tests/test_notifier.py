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
    text = notifier.incident_started(STATE, ["downradar"], NOW)
    assert text.startswith("🔴 ВТБ: возможный сбой")
    assert "Источник: DownRadar" in text
    assert "жалоб за час: 87" in text
    assert "14:50 МСК" in text
    assert "🔴 DownRadar" in text and "🟢 DownReport" in text


def test_incident_confirmed_counts_enabled_detectors():
    text = notifier.incident_confirmed(STATE, "downradar", 1)
    assert text.startswith("➕ ВТБ: сбой подтверждает DownRadar (1 из 2 детекторов)")


def test_incident_resolved_duration():
    text = notifier.incident_resolved(STATE, NOW)
    assert "47 мин" in text and "14:03" in text and "14:50" in text


def test_source_messages():
    result = SourceResult("downreport", ERROR, "HTTP 403")
    assert notifier.source_down(result) == "⚙️ DownReport не отвечает (HTTP 403). Сигналы этого источника не учитываются."
    assert notifier.source_back(result) == "⚙️ DownReport снова работает"


def test_official_post():
    text = notifier.official_post(Post(12, "Наблюдаются затруднения", "outage"))
    assert text.startswith("📢 ВТБ официально сообщает о проблемах")
    assert "«Наблюдаются затруднения»" in text
    assert "https://t.me/bankvtb/12" in text


def test_heartbeat():
    assert notifier.heartbeat(STATE).startswith("💓 Оповещатель ВТБ работает")


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
