"""DownRadar: crowd complaints compared with the site's own hourly baseline."""
import re

import requests
from bs4 import BeautifulSoup

from .base import ERROR, OK, OUTAGE, FetchError, SourceResult, fetch

NAME = "downradar"
URL = "https://downradar.ru/ne-rabotaet/vtb.ru"
STATUS_RE = re.compile(r"Статус\s+\S+\s*:\s*(.+)", re.S)
HOUR_RE = re.compile(r"За последний час\s*-\s*(\d+)")


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    line = soup.find(string=STATUS_RE)
    if line is None:
        return SourceResult(NAME, ERROR, "не найден статус на странице", URL)
    status = STATUS_RE.search(line).group(1).strip(" \xa0\n\t")
    hour = HOUR_RE.search(soup.get_text(" "))
    details = status + (f", жалоб за час: {hour.group(1)}" if hour else "")
    if status == "нет проблем":
        return SourceResult(NAME, OK, details, URL)
    if "проблем" in status:
        return SourceResult(NAME, OUTAGE, details, URL)
    return SourceResult(NAME, ERROR, f"неизвестный статус: {status}", URL)


def check(session=requests):
    try:
        resp = fetch(URL, session=session)
    except FetchError as exc:
        return SourceResult(NAME, ERROR, str(exc), URL)
    return parse(resp.content)
