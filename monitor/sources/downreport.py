"""DownReport: crowd complaints, verdict text on the VTB page."""
import requests
from bs4 import BeautifulSoup

from .base import ERROR, OK, OUTAGE, FetchError, SourceResult, fetch

NAME = "downreport"
URL = "https://downreport.ru/vtb"
# text-warning means isolated reports; it is shown for most services most of the time
CALM_CLASSES = {"text-success", "text-warning"}
OUTAGE_CLASSES = {"text-danger"}


def parse(html):
    status = BeautifulSoup(html, "html.parser").select_one("p.service_current_status_name")
    if status is None:
        return SourceResult(NAME, ERROR, "не найден статус на странице", URL)
    text = status.get_text(" ", strip=True)
    if not text:
        return SourceResult(NAME, ERROR, "пустой статус на странице", URL)
    classes = set(status.get("class", []))
    if OUTAGE_CLASSES & classes:
        return SourceResult(NAME, OUTAGE, text, URL)
    if CALM_CLASSES & classes:
        return SourceResult(NAME, OK, text, URL)
    return SourceResult(NAME, ERROR, f"неизвестный статус: {text}", URL)


def check(session=requests):
    try:
        resp = fetch(URL, session=session)
    except FetchError as exc:
        return SourceResult(NAME, ERROR, str(exc), URL)
    return parse(resp.content)
