import json

import requests

from monitor import availability
from tests.fakes import FakeResp


class Session:
    """Routes by URL: check-host start, check-host result, or the site itself (the VPS check)."""

    def __init__(self, results, vps=None, start_error=None):
        self.results = list(results)   # successive check-result answers
        self.vps = vps if vps is not None else FakeResp(200)
        self.start_error = start_error
        self.calls = []

    def get(self, url, headers=None, timeout=None, verify=None, allow_redirects=True):
        self.calls.append(url)
        if "/check-http" in url:
            if self.start_error:
                raise self.start_error
            return FakeResp(200, json.dumps({"request_id": "r1", "nodes": {
                "ru1.node.check-host.net": ["ru", "Russia", "Moscow", "1.1.1.1", "AS1"],
                "de4.node.check-host.net": ["de", "Germany", "Frankfurt", "2.2.2.2", "AS2"],
                "us1.node.check-host.net": ["us", "USA", "Los Angeles", "3.3.3.3", "AS3"]}}))
        if "/check-result/" in url:
            return FakeResp(200, json.dumps(self.results.pop(0) if len(self.results) > 1 else self.results[0]))
        assert verify and verify.endswith(".pem")  # the bundle with the Russian root
        if isinstance(self.vps, Exception):
            raise self.vps
        return self.vps


def no_sleep(monkeypatch):
    monkeypatch.setattr(availability, "sleep", lambda seconds: None)


def test_regions_from_vps_and_check_host(monkeypatch):
    no_sleep(monkeypatch)
    session = Session([{
        "ru1.node.check-host.net": [[1, 0.12, "OK", "200", "1.1.1.1"]],
        "de4.node.check-host.net": [[0, 10.0, "Connection timed out", None, None]],
        "us1.node.check-host.net": [[1, 0.9, "Found", "302", "1.1.1.1"]]}])
    out = availability.check(["db.vtb.ru"], session)["db.vtb.ru"]
    assert (out["ru"].up, out["ru"].total) == (2, 2)  # the VPS and Moscow
    assert (out["world"].up, out["world"].total) == (1, 2)
    assert out["world"].details() == "Франкфурт ❌ Connection timed out; Лос-Анджелес ✅ HTTP 302, 900 мс"
    assert out["ru"].details().startswith("Новосибирск (сервер) ✅ HTTP 200")


def test_waits_for_slow_nodes_then_leaves_them_out(monkeypatch):
    no_sleep(monkeypatch)
    pending = {"ru1.node.check-host.net": [[1, 0.1, "OK", "200", "x"]],
               "de4.node.check-host.net": None, "us1.node.check-host.net": None}
    session = Session([pending])
    out = availability.check(["db.vtb.ru"], session)["db.vtb.ru"]
    assert sum("/check-result/" in c for c in session.calls) == availability.POLL_TRIES
    assert out["world"].total == 0 and out["ru"].total == 2


def test_server_errors_and_bot_walls(monkeypatch):
    no_sleep(monkeypatch)
    session = Session([{
        "ru1.node.check-host.net": [[0, 0.2, "Service Unavailable", "503", "x"]],
        "de4.node.check-host.net": [[0, 0.2, "Forbidden", "403", "x"]],  # bot protection: it answered
        "us1.node.check-host.net": [[None]]}], vps=FakeResp(502))
    out = availability.check(["db.vtb.ru"], session)["db.vtb.ru"]
    assert out["ru"].up == 0 and out["ru"].total == 2
    assert out["world"].up == 1 and "нет ответа" in out["world"].details()


def test_check_host_down_keeps_the_vps_point(monkeypatch, capsys):
    no_sleep(monkeypatch)
    session = Session([{}], vps=requests.Timeout(), start_error=requests.ConnectionError())
    out = availability.check(["vtbbo.ru"], session)["vtbbo.ru"]
    assert out["ru"].details() == "Новосибирск (сервер) ❌ таймаут"
    assert out["world"].total == 0
    assert "check-host vtbbo.ru: ConnectionError" in capsys.readouterr().out


def test_ca_bundle_has_the_russian_root():
    text = open(availability._ca_bundle(), encoding="ascii").read()
    assert availability.RUSSIAN_ROOT.read_text(encoding="ascii").strip() in text
    assert text.count("BEGIN CERTIFICATE") > 100  # and the usual roots
