import json

from monitor.sources import detector404
from monitor.sources.base import DISABLED, ERROR, OK, OUTAGE
from tests.fakes import FakeResp, FakeSession


def resp(data):
    return FakeResp(200, json.dumps(data, ensure_ascii=False))


def test_no_token_is_disabled():
    session = FakeSession()
    assert detector404.check("", session).status == DISABLED
    assert session.calls == []


def test_sends_bearer_token():
    session = FakeSession(resp([]))
    detector404.check("secret", session)
    assert session.calls[0][2]["Authorization"] == "Bearer secret"


def test_vtb_alert_is_outage():
    data = [{"service": "Сбербанк"}, {"service": "Банк ВТБ", "reports": 87}]
    result = detector404.check("t", FakeSession(resp(data)))
    assert result.status == OUTAGE
    assert "87" in result.details


def test_alerts_wrapped_in_dict():
    result = detector404.check("t", FakeSession(resp({"data": [{"url": "/bank-vtb"}]})))
    assert result.status == OUTAGE


def test_no_vtb_alert_is_ok():
    result = detector404.check("t", FakeSession(resp([{"service": "Сбербанк"}])))
    assert result.status == OK


def test_bad_token_is_error():
    result = detector404.check("t", FakeSession(FakeResp(401)))
    assert result.status == ERROR
    assert "токен" in result.details


def test_unexpected_format_is_error():
    assert detector404.check("t", FakeSession(FakeResp(200, "<html>"))).status == ERROR
    assert detector404.check("t", FakeSession(resp({"x": 1}))).status == ERROR


def test_prefers_known_list_key():
    data = {"errors": [], "data": [{"service": "Банк ВТБ"}]}
    assert detector404.check("t", FakeSession(resp(data))).status == OUTAGE


def test_ambiguous_lists_are_error():
    assert detector404.check("t", FakeSession(resp({"a": [], "b": []}))).status == ERROR


def test_bare_vtb_name_is_outage():
    assert detector404.check("t", FakeSession(resp([{"name": "ВТБ Онлайн"}]))).status == OUTAGE


def test_other_vtb_slug_is_not_vtb():
    assert detector404.check("t", FakeSession(resp([{"url": "/bank-vtb-armenia"}]))).status == OK
