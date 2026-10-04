"""Common result type and HTTP helper shared by all sources."""
import time
from dataclasses import dataclass

import requests

OK = "OK"
OUTAGE = "OUTAGE"
ERROR = "SOURCE_ERROR"
DISABLED = "DISABLED"

USER_AGENT = "Mozilla/5.0 (compatible; vtb-outage-notifier/1.0)"
TIMEOUT = 15
MAX_RETRY_AFTER = 30

sleep = time.sleep  # replaced in tests


@dataclass
class SourceResult:
    source: str
    status: str
    details: str = ""
    url: str = ""


class FetchError(Exception):
    pass


def _retry_after(resp):
    try:
        return min(int(resp.headers.get("Retry-After", 5)), MAX_RETRY_AFTER)
    except ValueError:
        return 5


def fetch(url, headers=None, session=requests):
    """GET with one retry. No retry on 401/403. Raises FetchError."""
    all_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    error = None
    for attempt in range(2):
        last_attempt = attempt == 1
        try:
            resp = session.get(url, headers=all_headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            error = FetchError(f"сеть: {exc.__class__.__name__}")
            if not last_attempt:
                sleep(2)
            continue
        if resp.status_code == 200:
            return resp
        error = FetchError(f"HTTP {resp.status_code}")
        if resp.status_code == 429 and not last_attempt:
            sleep(_retry_after(resp))
        elif resp.status_code >= 500 and not last_attempt:
            sleep(2)
        else:
            raise error
    raise error
