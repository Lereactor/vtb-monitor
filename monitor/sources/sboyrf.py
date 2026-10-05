"""СБОЙ.РФ: crowd complaints per 15 minutes over the last 24 hours.

The page's own verdict ("наблюдаются проблемы") only means "more than ~100
complaints today", which VTB exceeds almost every day, so the 24-hour chart
data is read instead and only a spike in the last hour counts as an outage.
"""
import json
import re
import time

import requests

from .base import ERROR, OK, OUTAGE, FetchError, SourceResult, fetch

NAME = "sboyrf"
URL = "https://сбой.рф/bank-vtb"
FETCH_URL = "https://xn--90aqok.xn--p1ai/bank-vtb"
# a normal day has several 20-40 complaint bursts per hour
HOUR_THRESHOLD = 50
BUCKETS_PER_HOUR = 4
DAY_CHART_RE = re.compile(r"getElementById\('myChart'\).*?var data = (\[[^\]]*\])", re.S)
TODAY_RE = re.compile(r"жалоб за сегодня:\s*<b>(\d+)")


def parse(html):
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    match = DAY_CHART_RE.search(html)
    if match is None:
        return SourceResult(NAME, ERROR, "не найден график жалоб на странице", URL)
    try:
        series = json.loads(match.group(1))
    except ValueError:
        return SourceResult(NAME, ERROR, "не удалось прочитать график жалоб", URL)
    if len(series) < BUCKETS_PER_HOUR or not all(isinstance(n, int) for n in series):
        return SourceResult(NAME, ERROR, "неожиданный формат графика жалоб", URL)
    hour = sum(series[-BUCKETS_PER_HOUR:])
    today = TODAY_RE.search(html)
    details = f"жалоб за час: {hour}" + (f", за сегодня: {today.group(1)}" if today else "")
    return SourceResult(NAME, OUTAGE if hour >= HOUR_THRESHOLD else OK, details, URL)


def check(session=requests):
    # the site serves a page cache that can be hours old; a query string bypasses it
    try:
        resp = fetch(f"{FETCH_URL}?t={int(time.time())}", session=session)
    except FetchError as exc:
        return SourceResult(NAME, ERROR, str(exc), URL)
    return parse(resp.content)
