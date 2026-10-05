"""What is monitored: each service has its own detectors (source name -> page on that site)."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Service:
    title: str
    detectors: dict = field(default_factory=dict)


SERVICES = {
    "vtb": Service("ВТБ", {"detector404": "bank-vtb", "downreport": "vtb",
                           "downradar": "vtb.ru", "sboyrf": "bank-vtb"}),
    # DownReport and СБОЙ.РФ have no page for the investment app
    "invest": Service("ВТБ Мои Инвестиции", {"detector404": "vtbinvesticii",
                                             "downradar": "broker.vtb.ru"}),
}
# the official channel's result is kept with this service
CHANNEL_SERVICE = "vtb"
