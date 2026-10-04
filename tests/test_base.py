import pytest
import requests

from monitor.sources import base
from monitor.sources.base import FetchError, fetch
from tests.fakes import FakeResp, FakeSession


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(base, "sleep", slept.append)
    return slept


def test_returns_ok_response():
    session = FakeSession(FakeResp(200, "hi"))
    assert fetch("https://x", session=session).text == "hi"


def test_retries_once_after_network_error():
    session = FakeSession(requests.ConnectionError("boom"), FakeResp(200, "ok"))
    assert fetch("https://x", session=session).text == "ok"
    assert len(session.calls) == 2


def test_gives_up_after_two_network_errors():
    session = FakeSession(requests.ConnectionError(), requests.ConnectionError())
    with pytest.raises(FetchError, match="сеть"):
        fetch("https://x", session=session)


def test_no_retry_on_403():
    session = FakeSession(FakeResp(403))
    with pytest.raises(FetchError, match="HTTP 403"):
        fetch("https://x", session=session)
    assert len(session.calls) == 1


def test_429_honours_retry_after(no_sleep):
    session = FakeSession(FakeResp(429, headers={"Retry-After": "7"}), FakeResp(200, "ok"))
    assert fetch("https://x", session=session).text == "ok"
    assert no_sleep == [7]


def test_429_retry_after_is_capped(no_sleep):
    session = FakeSession(FakeResp(429, headers={"Retry-After": "600"}), FakeResp(200))
    fetch("https://x", session=session)
    assert no_sleep == [30]


def test_404_raises():
    with pytest.raises(FetchError, match="HTTP 404"):
        fetch("https://x", session=FakeSession(FakeResp(404)))


def test_429_negative_retry_after_is_zero(no_sleep):
    session = FakeSession(FakeResp(429, headers={"Retry-After": "-1"}), FakeResp(200))
    fetch("https://x", session=session)
    assert no_sleep == [0]
