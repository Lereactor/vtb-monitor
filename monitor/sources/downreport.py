"""DownReport: crowd complaints, verdict text on the VTB page."""
import requests
from bs4 import BeautifulSoup

from .base import ERROR, OK, OUTAGE, FetchError, SourceResult, fetch

NAME = "downreport"
PAGE = "vtb"
# text-warning means isolated reports; it is shown for most services most of the time
CALM_CLASSES = {"text-success", "text-warning"}
OUTAGE_CLASSES = {"text-danger"}


def _url(page):
    return f"https://downreport.ru/{page}"


def parse(html, page=PAGE):
    url = _url(page)
    status = BeautifulSoup(html, "html.parser").select_one("p.service_current_status_name")
    if status is None:
        return SourceResult(NAME, ERROR, "не найден статус на странице", url)
    text = status.get_text(" ", strip=True)
    if not text:
        return SourceResult(NAME, ERROR, "пустой статус на странице", url)
    classes = set(status.get("class", []))
    if OUTAGE_CLASSES & classes:
        return SourceResult(NAME, OUTAGE, text, url)
    if CALM_CLASSES & classes:
        return SourceResult(NAME, OK, text, url)
    return SourceResult(NAME, ERROR, f"неизвестный статус: {text}", url)


def check(session=requests, page=PAGE):
    try:
        resp = fetch(_url(page), session=session)
    except FetchError as exc:
        return SourceResult(NAME, ERROR, str(exc), _url(page))
    return parse(resp.content, page)
