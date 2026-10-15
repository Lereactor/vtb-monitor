"""What is monitored: each service has its own detectors (source name -> page on that site)
and its own websites, checked for availability from Russia and from abroad."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Service:
    title: str
    detectors: dict = field(default_factory=dict)
    sites: tuple = ()  # hosts of the service itself: an extra indicator, never an alert by itself


SERVICES = {
    # db.vtb.ru is the new Бизнес Платформа, vtbbo.ru the old ВТБ Бизнес Онлайн (read-only since 10.2026).
    # Neither DETECTOR404 nor СБОЙ.РФ has a page for it; DownRadar's vtbbo.ru page has no complaints.
    "business": Service("ВТБ Бизнес-онлайн", {"downreport": "vtb-business-platform",
                                              "downradar": "db.vtb.ru"},
                        ("db.vtb.ru", "vtbbo.ru")),
    # СБОЙ.РФ has no page for the investment app
    "invest": Service("ВТБ Мои Инвестиции", {"detector404": "vtbinvesticii",
                                             "downreport": "vtb-investments",
                                             "downradar": "broker.vtb.ru"},
                      ("invest.vtb.ru",)),
}
# the official channel's result is kept with this service
CHANNEL_SERVICE = "business"
# ВТБ itself (bank-vtb, vtb.ru) was monitored until 15.10.2026: its history stays in the database
# under "vtb" but is no longer shown or checked
