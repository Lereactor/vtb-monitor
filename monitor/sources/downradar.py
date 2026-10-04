"""DownRadar: crowd complaints compared with the site's own hourly baseline."""
import re

import requests
from bs4 import BeautifulSoup

from .base import ERROR, OK, OUTAGE, FetchError, SourceResult, fetch

NAME = "downradar"
URL = "https://downradar.ru/ne-rabotaet/vtb.ru"
STATUS_RE = re.compile(r"Статус\s+Vtb\.ru\s*:\s*(.+)", re.I | re.S)
HOUR_RE = re.compile(r"За последний час\s*-\s*(\d+)")


def _find_status(soup):
    """Status text from the VTB alert block; other alert blocks are ignored."""
    for alert in soup.select("div.alert"):
        for string in alert.find_all(string=True):
            match = STATUS_RE.search(string)
            if match:
                return " ".join(match.group(1).split()).lower().rstrip(".")
    return None


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    status = _find_status(soup)
    if status is None:
        return SourceResult(NAME, ERROR, "не найден статус на странице", URL)
    hour = HOUR_RE.search(soup.get_text(" "))
    details = status + (f", жалоб за час: {hour.group(1)}" if hour else "")
    if status == "нет проблем":
        return SourceResult(NAME, OK, details, URL)
    if "есть проблем" in status:
        return SourceResult(NAME, OUTAGE, details, URL)
    return SourceResult(NAME, ERROR, f"неизвестный статус: {status}", URL)


def check(session=requests):
    try:
        resp = fetch(URL, session=session)
    except FetchError as exc:
        return SourceResult(NAME, ERROR, str(exc), URL)
    return parse(resp.content)
