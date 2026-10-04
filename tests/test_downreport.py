from pathlib import Path

from monitor.sources import downreport
from monitor.sources.base import ERROR, OK, OUTAGE
from tests.fakes import FakeResp, FakeSession

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_ok_page():
    result = downreport.parse(load("downreport_ok.html"))
    assert result.status == OK
    assert "Массовых жалоб нет" in result.details


def test_warning_is_not_outage():
    result = downreport.parse(load("downreport_warning.html"))
    assert result.status == OK
    assert "Жалобы на сбои" in result.details


def test_danger_is_outage():
    html = (load("downreport_ok.html")
            .replace("text-success", "text-danger")
            .replace("Массовых жалоб нет", "Массовый сбой"))
    result = downreport.parse(html)
    assert result.status == OUTAGE
    assert "Массовый сбой" in result.details
    assert result.url == downreport.URL


def test_missing_status_is_error():
    assert downreport.parse("<html><body></body></html>").status == ERROR


def test_check_reports_fetch_error():
    result = downreport.check(FakeSession(FakeResp(403)))
    assert result.status == ERROR
    assert "403" in result.details


def test_check_parses_page():
    result = downreport.check(FakeSession(FakeResp(200, load("downreport_ok.html"))))
    assert result.status == OK
