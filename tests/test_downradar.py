import re
from pathlib import Path

from monitor.sources import downradar
from monitor.sources.base import ERROR, OK, OUTAGE
from tests.fakes import FakeResp, FakeSession

OK_HTML = (Path(__file__).parent / "fixtures" / "downradar_ok.html").read_text(encoding="utf-8")


def test_ok_page():
    result = downradar.parse(OK_HTML)
    assert result.status == OK
    assert re.search(r"нет проблем, жалоб за час: \d+", result.details)


def test_problems_is_outage():
    html = OK_HTML.replace("Статус Vtb.ru : нет проблем", "Статус Vtb.ru : есть проблемы")
    result = downradar.parse(html)
    assert result.status == OUTAGE
    assert result.details.startswith("есть проблемы")


def test_missing_status_is_error():
    assert downradar.parse("<html><body>пусто</body></html>").status == ERROR


def test_unknown_status_is_error():
    html = OK_HTML.replace("Статус Vtb.ru : нет проблем", "Статус Vtb.ru : загадка")
    assert downradar.parse(html).status == ERROR


def test_check_reports_fetch_error():
    result = downradar.check(FakeSession(FakeResp(500), FakeResp(502)))
    assert result.status == ERROR
