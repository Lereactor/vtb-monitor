import json
import re
from pathlib import Path

from monitor.sources import detector404
from monitor.sources.base import ERROR, OK, OUTAGE
from tests.fakes import FakeResp, FakeSession

OK_HTML = (Path(__file__).parent / "fixtures" / "detector404_ok.html").read_text(encoding="utf-8")
LD_RE = re.compile(r'(<script[^>]*application/ld\+json[^>]*>)(.*?)(</script>)', re.S)


def with_flags(network=None, cities=None, complaints=None):
    """OK page with the dataset flags overridden (None = keep)."""
    def edit(match):
        data = json.loads(match.group(2))
        for node in data["@graph"]:
            for prop in node.get("variableMeasured", []) if isinstance(node, dict) else []:
                if prop["name"] == "Сервис недоступен по сети":
                    if network is not None:
                        prop["value"] = network
                    if cities is not None:
                        prop["valueReference"]["value"] = cities
                if prop["name"] == "Много жалоб пользователей" and complaints is not None:
                    prop["value"] = complaints
        return match.group(1) + json.dumps(data, ensure_ascii=False) + match.group(3)
    return LD_RE.sub(edit, OK_HTML, count=1)


def test_ok_page():
    result = detector404.parse(OK_HTML)
    assert result.status == OK
    assert result.url == "https://detector404.ru/bank-vtb"


def test_network_down_is_outage_with_city_count():
    result = detector404.parse(with_flags(network=True, cities=7))
    assert result.status == OUTAGE
    assert "сенсоры: недоступен в 7 городах" in result.details


def test_many_complaints_is_outage():
    result = detector404.parse(with_flags(complaints=True))
    assert result.status == OUTAGE
    assert "много жалоб" in result.details


def test_missing_dataset_is_error():
    assert detector404.parse("<html><body>нет данных</body></html>").status == ERROR


def test_missing_flag_is_error():
    html = OK_HTML.replace("Много жалоб пользователей", "Что-то другое")
    assert detector404.parse(html).status == ERROR


def test_broken_json_is_error():
    html = '<script type="application/ld+json">{not json</script>'
    assert detector404.parse(html).status == ERROR


def test_check_reports_fetch_error():
    result = detector404.check(FakeSession(FakeResp(403)))
    assert result.status == ERROR
    assert "403" in result.details


def test_check_parses_page():
    assert detector404.check(FakeSession(FakeResp(200, OK_HTML))).status == OK


INVEST_HTML = (Path(__file__).parent / "fixtures" / "detector404_invest_ok.html").read_bytes()


def test_invest_page():
    result = detector404.parse(INVEST_HTML, "vtbinvesticii")
    assert result.status == OK
    assert result.url == "https://detector404.ru/vtbinvesticii"


def test_check_fetches_given_page():
    session = FakeSession(FakeResp(200, INVEST_HTML.decode("utf-8")))
    detector404.check(session, "vtbinvesticii")
    assert session.calls[0][1] == "https://detector404.ru/vtbinvesticii"
