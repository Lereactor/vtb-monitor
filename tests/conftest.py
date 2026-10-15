import pytest

from monitor import main


@pytest.fixture(autouse=True)
def no_site_checks(monkeypatch):
    """The availability check goes to the network: tests that need it patch it themselves."""
    monkeypatch.setattr(main, "check_sites", lambda hosts, session=None: {})


@pytest.fixture
def legacy_vtb():
    """ВТБ itself as it was monitored until 15.10.2026: the generic alert, history and analytics
    tests were written against it, and it still has every detector (СБОЙ.РФ only here)."""
    from monitor.services import SERVICES, Service
    saved = dict(SERVICES)
    vtb = Service("ВТБ", {"detector404": "bank-vtb", "downreport": "vtb", "downradar": "vtb.ru",
                          "sboyrf": "bank-vtb"})
    SERVICES.clear()
    SERVICES.update({"vtb": vtb, **saved})  # first, as it was
    yield
    SERVICES.clear()
    SERVICES.update(saved)
