"""Do the bank's own websites open: from the VPS (Novosibirsk) and from check-host.net nodes
in Russia and abroad. An extra indicator for messages and the site: it never raises an alert.

From Russia VTB serves certificates of the Russian Trusted Root CA (Минцифры), which is not in
the usual trust stores, so the VPS check trusts it in addition to certifi's roots.
"""
import os
import statistics
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import certifi
import requests

from .sources.base import USER_AGENT

RUSSIAN_ROOT = Path(__file__).with_name("certs") / "russian_trusted_root_ca.pem"
CHECK_HOST = "https://check-host.net"
NODES = {"ru": ("ru1", "ru2", "ru3"), "world": ("de4", "nl1", "uk1", "us1")}
REGIONS = tuple(NODES)
CITIES = {"Moscow": "Москва", "Saint Petersburg": "Санкт-Петербург", "Frankfurt": "Франкфурт",
          "Amsterdam": "Амстердам", "London": "Лондон", "Los Angeles": "Лос-Анджелес"}
VPS_PLACE = "Новосибирск (сервер)"
TIMEOUT = 15
POLL_WAIT = 5    # seconds between check-host result polls
POLL_TRIES = 4   # nodes still silent after that are left out of the total

sleep = time.sleep  # replaced in tests
_bundle = None


@dataclass
class Point:
    place: str
    up: bool
    ms: int | None = None
    note: str = ""   # HTTP code or the error

    def text(self):
        if self.up:
            return f"{self.place} ✅ {self.note}" + (f", {self.ms} мс" if self.ms is not None else "")
        return f"{self.place} ❌ {self.note}"


@dataclass
class Reach:
    host: str
    region: str             # ru | world
    points: list = field(default_factory=list)

    @property
    def up(self):
        return sum(p.up for p in self.points)

    @property
    def total(self):
        return len(self.points)

    @property
    def ms(self):
        times = [p.ms for p in self.points if p.up and p.ms is not None]
        return round(statistics.median(times)) if times else None

    def details(self):
        return "; ".join(p.text() for p in self.points)


def _ca_bundle():
    """certifi's roots plus the Russian root, written once per process."""
    global _bundle
    if _bundle is None:
        handle, path = tempfile.mkstemp(prefix="vtb-ca-", suffix=".pem")
        with os.fdopen(handle, "w", encoding="ascii") as out:
            out.write(Path(certifi.where()).read_text(encoding="ascii") + "\n"
                      + RUSSIAN_ROOT.read_text(encoding="ascii"))
        _bundle = path
    return _bundle


def _up(code):
    """The server answered: anything but a 5xx (a 403 from bot protection still means it is up)."""
    return code is not None and int(code) < 500


def check_from_vps(host, session=requests):
    started = time.monotonic()
    try:
        resp = session.get(f"https://{host}/", headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
                           verify=_ca_bundle(), allow_redirects=False)
    except requests.RequestException as exc:
        return Point(VPS_PLACE, False, note=_error_text(exc))
    ms = round((time.monotonic() - started) * 1000)
    return Point(VPS_PLACE, _up(resp.status_code), ms, f"HTTP {resp.status_code}")


def _error_text(exc):
    if isinstance(exc, requests.Timeout):
        return "таймаут"
    if isinstance(exc, requests.exceptions.SSLError):
        return "ошибка сертификата"
    if isinstance(exc, requests.ConnectionError):
        return "нет соединения"
    return exc.__class__.__name__


def _start(host, session):
    """check-host request id and {node: place} for one host, all regions at once."""
    nodes = "&".join(f"node={n}.node.check-host.net" for region in REGIONS for n in NODES[region])
    resp = session.get(f"{CHECK_HOST}/check-http?host=https://{host}/&{nodes}",
                       headers={"Accept": "application/json"}, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    places = {node: CITIES.get(info[2], info[2]) for node, info in data.get("nodes", {}).items()}
    return data["request_id"], places


def _point(place, answer):
    """check-host answer for one node: [[1|0, seconds, message, code, ip]]."""
    try:
        ok, seconds, message, code = answer[0][:4]
    except (TypeError, ValueError, IndexError):
        return Point(place, False, note="нет ответа")
    if code is not None and _up(code):
        return Point(place, True, round(seconds * 1000) if seconds is not None else None, f"HTTP {code}")
    return Point(place, False, note=f"HTTP {code}" if code else (message or "нет ответа"))


def check(hosts, session=requests):
    """{host: {region: Reach}}. check-host failures leave only the VPS point (or nothing abroad)."""
    out = {host: {region: Reach(host, region) for region in REGIONS} for host in hosts}
    pending = {}
    for host in hosts:
        try:
            pending[host] = _start(host, session)
        except (requests.RequestException, ValueError, KeyError) as exc:
            print(f"availability: check-host {host}: {exc.__class__.__name__}")
    for host in hosts:
        out[host]["ru"].points.append(check_from_vps(host, session))
    answers = {host: {} for host in pending}
    for _ in range(POLL_TRIES if pending else 0):
        sleep(POLL_WAIT)
        for host, (request_id, places) in pending.items():
            if len(answers[host]) == len(places):
                continue
            try:
                resp = session.get(f"{CHECK_HOST}/check-result/{request_id}", timeout=TIMEOUT)
                resp.raise_for_status()
                result = resp.json()
            except (requests.RequestException, ValueError) as exc:
                print(f"availability: check-host result {host}: {exc.__class__.__name__}")
                continue
            answers[host].update({node: answer for node, answer in result.items() if answer is not None})
        if all(len(answers[h]) == len(pending[h][1]) for h in pending):
            break
    for host, (_, places) in pending.items():
        for node, place in places.items():
            if node in answers[host]:
                region = "ru" if node.startswith("ru") else "world"
                out[host][region].points.append(_point(place, answers[host][node]))
    return out
