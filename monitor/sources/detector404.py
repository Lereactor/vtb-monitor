"""DETECTOR404: the public VTB page carries a schema.org Dataset with two verdicts:
network unavailability from its own sensors in 34 Russian cities, and a
"too many user complaints" flag. No account or API token needed.
"""
import json
import re

import requests
from bs4 import BeautifulSoup

from .base import ERROR, OK, OUTAGE, FetchError, SourceResult, fetch

NAME = "detector404"
PAGE = "bank-vtb"
NETWORK = "Сервис недоступен по сети"
COMPLAINTS = "Много жалоб пользователей"


def _flags(html):
    """Returns {measured property name: property dict} or None."""
    for script in BeautifulSoup(html, "html.parser").find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "Dataset":
                return {prop.get("name"): prop for prop in node.get("variableMeasured", [])
                        if isinstance(prop, dict)}
    return None


def _url(page):
    return f"https://detector404.ru/{page}"


def parse(html, page=PAGE):
    url = _url(page)
    flags = _flags(html)
    if flags is None:
        return SourceResult(NAME, ERROR, "не найден блок данных на странице", url)
    network, complaints = flags.get(NETWORK), flags.get(COMPLAINTS)
    if network is None or complaints is None:
        return SourceResult(NAME, ERROR, "не найдены флаги статуса на странице", url)
    if not isinstance(network.get("value"), bool) or not isinstance(complaints.get("value"), bool):
        return SourceResult(NAME, ERROR, "неожиданный формат флагов", url)

    problems = []
    if network["value"]:
        cities = (network.get("valueReference") or {}).get("value")
        problems.append(f"сенсоры: недоступен в {cities} городах" if cities
                        else "сенсоры: недоступен по сети")
    if complaints["value"]:
        problems.append("много жалоб пользователей")
    if problems:
        return SourceResult(NAME, OUTAGE, "; ".join(problems), url)
    return SourceResult(NAME, OK, "сенсоры и жалобы в норме", url)


def check(session=requests, page=PAGE):
    try:
        resp = fetch(_url(page), session=session)
    except FetchError as exc:
        return SourceResult(NAME, ERROR, str(exc), _url(page))
    return parse(resp.content, page)
