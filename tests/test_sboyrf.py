import re
from pathlib import Path

from monitor.sources import base, sboyrf
from monitor.sources.base import ERROR, OK, OUTAGE
from tests.fakes import FakeResp, FakeSession

OK_HTML = (Path(__file__).parent / "fixtures" / "sboyrf_ok.html").read_text(encoding="utf-8")
DAY_CHART = "getElementById('myChart')"


def with_day_series(html, data):
    """Replaces the 15-minute series of the 24-hour chart (not the 14-day one)."""
    start = html.index(DAY_CHART)
    tail = re.sub(r"var data = \[[^\]]*\]", f"var data = {data}", html[start:], count=1)
    return html[:start] + tail


def quiet_day(last_hour):
    return [0] * 92 + last_hour


def test_ok_page():
    result = sboyrf.parse(OK_HTML)
    assert result.status == OK
    assert re.fullmatch(r"жалоб за час: \d+, за сегодня: \d+", result.details)


def test_spike_in_last_hour_is_outage():
    result = sboyrf.parse(with_day_series(OK_HTML, quiet_day([10, 20, 15, 5])))
    assert result.status == OUTAGE
    assert result.details.startswith("жалоб за час: 50,")


def test_routine_burst_is_ok():
    # 20-40 complaints in an hour happen several times on a normal day
    assert sboyrf.parse(with_day_series(OK_HTML, quiet_day([0, 21, 15, 2]))).status == OK


def test_old_spike_outside_last_hour_is_ok():
    data = [0] * 88 + [40, 40, 40, 40] + [0, 1, 0, 0]
    assert sboyrf.parse(with_day_series(OK_HTML, data)).status == OK


def test_fourteen_day_chart_is_ignored():
    html = OK_HTML.replace("var data = [248,", "var data = [999,999,999,999,248,", 1)
    assert sboyrf.parse(html).status == OK


def test_missing_chart_is_error():
    assert sboyrf.parse("<html><body>пусто</body></html>").status == ERROR


def test_short_series_is_error():
    assert sboyrf.parse(with_day_series(OK_HTML, [1, 2])).status == ERROR


def test_check_bypasses_page_cache():
    session = FakeSession(FakeResp(200, OK_HTML))
    assert sboyrf.check(session).status == OK
    url = session.calls[0][1]
    assert url.startswith("https://xn--90aqok.xn--p1ai/bank-vtb?")


def test_check_reports_fetch_error(monkeypatch):
    monkeypatch.setattr(base, "sleep", lambda seconds: None)
    result = sboyrf.check(FakeSession(FakeResp(500), FakeResp(502)))
    assert result.status == ERROR
