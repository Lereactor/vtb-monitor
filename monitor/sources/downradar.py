"""DownRadar: crowd complaints compared with the site's own hourly baseline."""
import re

import requests
from bs4 import BeautifulSoup

from .base import ERROR, OK, OUTAGE, FetchError, SourceResult, fetch

NAME = "downradar"
PAGE = "vtb.ru"
HOUR_RE = re.compile(r"За последний час\s*-\s*(\d+)")
# "есть проблемы" means "more than usual for this hour": on a quiet page (broker.vtb.ru had
# no complaints in 30 days) one complaint is enough, and on vtb.ru it lingers at 4-9 an hour
MIN_HOUR_COMPLAINTS = 10


def _url(page):
    return f"https://downradar.ru/ne-rabotaet/{page}"


def _find_status(soup, page):
    """Status text from this domain's alert block; other alert blocks are ignored."""
    status_re = re.compile(r"Статус\s+" + re.escape(page) + r"\s*:\s*(.+)", re.I | re.S)
    for alert in soup.select("div.alert"):
        for string in alert.find_all(string=True):
            match = status_re.search(string)
            if match:
                return " ".join(match.group(1).split()).lower().rstrip(".")
    return None


def parse(html, page=PAGE):
    url = _url(page)
    soup = BeautifulSoup(html, "html.parser")
    status = _find_status(soup, page)
    if status is None:
        return SourceResult(NAME, ERROR, "не найден статус на странице", url)
    hour = HOUR_RE.search(soup.get_text(" "))
    details = status + (f", жалоб за час: {hour.group(1)}" if hour else "")
    if status == "нет проблем":
        return SourceResult(NAME, OK, details, url)
    if "есть проблем" in status:
        if hour and int(hour.group(1)) < MIN_HOUR_COMPLAINTS:
            return SourceResult(NAME, OK, details + " (мало для тревоги)", url)
        return SourceResult(NAME, OUTAGE, details, url)
    return SourceResult(NAME, ERROR, f"неизвестный статус: {status}", url)


def check(session=requests, page=PAGE):
    try:
        resp = fetch(_url(page), session=session)
    except FetchError as exc:
        return SourceResult(NAME, ERROR, str(exc), _url(page))
    return parse(resp.content, page)
