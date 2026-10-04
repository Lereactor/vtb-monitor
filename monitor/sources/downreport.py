"""DownReport: crowd complaints, verdict text on the VTB page."""
import requests
from bs4 import BeautifulSoup

from .base import ERROR, OK, OUTAGE, FetchError, SourceResult, fetch

NAME = "downreport"
URL = "https://downreport.ru/vtb"
# text-warning means isolated reports; it is shown for most services most of the time
CALM_CLASSES = {"text-success", "text-warning"}


def parse(html):
    status = BeautifulSoup(html, "html.parser").select_one("p.service_current_status_name")
    if status is None:
        return SourceResult(NAME, ERROR, "не найден статус на странице", URL)
    text = status.get_text(" ", strip=True)
    if CALM_CLASSES & set(status.get("class", [])):
        return SourceResult(NAME, OK, text, URL)
    return SourceResult(NAME, OUTAGE, text, URL)


def check(session=requests):
    try:
        resp = fetch(URL, session=session)
    except FetchError as exc:
        return SourceResult(NAME, ERROR, str(exc), URL)
    return parse(resp.content)
