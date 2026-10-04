"""DETECTOR404 API: active events, includes its own sensors in 34 Russian cities.

The alert item format is not documented, so items are matched by text.
After getting a token, check a real response and tighten `_is_vtb` if needed.
"""
import json
import re

import requests

from .base import DISABLED, ERROR, OK, OUTAGE, FetchError, SourceResult, fetch

NAME = "detector404"
API_URL = "https://detector404.ru/api/v1/alerts"
URL = "https://detector404.ru/bank-vtb"
# "bank-vtb" but not other VTB-group slugs such as "bank-vtb-armenia"
VTB_RE = re.compile(r"Банк ВТБ|\bВТБ\b|bank-vtb(?![\w-])")
LIST_KEYS = ("alerts", "data", "items", "results")


def _alert_list(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return None
    for key in LIST_KEYS:
        if isinstance(data.get(key), list):
            return data[key]
    lists = [value for value in data.values() if isinstance(value, list)]
    return lists[0] if len(lists) == 1 else None


def _is_vtb(item):
    return bool(VTB_RE.search(json.dumps(item, ensure_ascii=False)))


def check(token, session=requests):
    if not token:
        return SourceResult(NAME, DISABLED, "нет токена", URL)
    try:
        resp = fetch(API_URL, headers={"Authorization": f"Bearer {token}"}, session=session)
    except FetchError as exc:
        hint = " (проверьте токен)" if str(exc) in ("HTTP 401", "HTTP 403") else ""
        return SourceResult(NAME, ERROR, f"{exc}{hint}", URL)
    try:
        alerts = _alert_list(resp.json())
    except ValueError:
        alerts = None
    if alerts is None:
        return SourceResult(NAME, ERROR, f"неожиданный ответ API: {resp.text[:150]}", URL)
    vtb = [item for item in alerts if _is_vtb(item)]
    if vtb:
        return SourceResult(NAME, OUTAGE, json.dumps(vtb[0], ensure_ascii=False)[:300], URL)
    return SourceResult(NAME, OK, "активных событий нет", URL)
