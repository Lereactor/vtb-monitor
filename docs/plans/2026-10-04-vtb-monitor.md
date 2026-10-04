# VTB Outage Notifier Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Every 5 minutes, check public outage detectors and the official VTB Telegram channel; send a Telegram message naming the source when VTB has an outage, when it ends, and when a source breaks.

**Architecture:** One Python script run by GitHub Actions cron. Each source module has a pure `parse()` (tested on saved HTML) and a `check()` that fetches and returns `SourceResult(source, status, details, url)`. A pure state engine (`monitor/state.py`) turns results plus the previous `state.json` into messages; the workflow commits `state.json` back to the repo.

**Tech Stack:** Python 3.11, requests, beautifulsoup4, pytest, GitHub Actions, Telegram Bot API.

**Design:** `docs/plans/2026-10-04-vtb-monitor-design.md`

**Facts verified on 2026-10-04 (do not re-research):**
- DownReport `https://downreport.ru/vtb`: status is `<p class="service_current_status_name ... text-success">Массовых жалоб нет</p>`. `text-warning` = «Жалобы на сбои в работе» — shown for most services, means isolated reports → treat as OK. Any other class → OUTAGE.
- DownRadar `https://downradar.ru/ne-rabotaet/vtb.ru`: `<div class="alert alert-success">&nbsp;Статус Vtb.ru : нет проблем &nbsp;` and `За последний час - <b>1</b>`. Status «есть проблемы» = above its own baseline.
- Telegram `https://t.me/s/bankvtb`: posts are `div.tgme_widget_message[data-post="bankvtb/3812"]` with `div.tgme_widget_message_text`.
- DETECTOR404 API: `GET https://detector404.ru/api/v1/alerts` (current active events), `Authorization: Bearer <token>`. Response format undocumented → match items by text «Банк ВТБ» / `bank-vtb`.
- Fixtures already saved: `tests/fixtures/downreport_ok.html`, `downreport_warning.html`, `downradar_ok.html`, `telegram_bankvtb.html`.

Run all commands from `C:\Claude\DownDetector` in Git Bash.

---

### Task 1: Scaffold and HTTP helper

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`
- Create: `monitor/__init__.py`, `monitor/sources/__init__.py`, `tests/__init__.py` (all empty)
- Create: `monitor/sources/base.py`
- Create: `tests/fakes.py`
- Test: `tests/test_base.py`

**Step 1: Create project files**

`requirements.txt`:
```
requests==2.32.3
beautifulsoup4==4.12.3
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest==8.3.3
```

`pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

`tests/fakes.py`:
```python
"""Fake HTTP objects for tests: no network."""
import json


class FakeResp:
    def __init__(self, status=200, text="", headers=None):
        self.status_code = status
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = headers or {}

    def json(self):
        return json.loads(self.text)


class FakeSession:
    """Returns queued responses (or raises queued exceptions) in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url, headers))
        return self._next()

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        return self._next()

    def _next(self):
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
```

Run: `pip install -r requirements-dev.txt`

**Step 2: Write the failing test** — `tests/test_base.py`:
```python
import pytest
import requests

from monitor.sources import base
from monitor.sources.base import FetchError, fetch
from tests.fakes import FakeResp, FakeSession


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(base, "sleep", slept.append)
    return slept


def test_returns_ok_response():
    session = FakeSession(FakeResp(200, "hi"))
    assert fetch("https://x", session=session).text == "hi"


def test_retries_once_after_network_error():
    session = FakeSession(requests.ConnectionError("boom"), FakeResp(200, "ok"))
    assert fetch("https://x", session=session).text == "ok"
    assert len(session.calls) == 2


def test_gives_up_after_two_network_errors():
    session = FakeSession(requests.ConnectionError(), requests.ConnectionError())
    with pytest.raises(FetchError, match="сеть"):
        fetch("https://x", session=session)


def test_no_retry_on_403():
    session = FakeSession(FakeResp(403))
    with pytest.raises(FetchError, match="HTTP 403"):
        fetch("https://x", session=session)
    assert len(session.calls) == 1


def test_429_honours_retry_after(no_sleep):
    session = FakeSession(FakeResp(429, headers={"Retry-After": "7"}), FakeResp(200, "ok"))
    assert fetch("https://x", session=session).text == "ok"
    assert no_sleep == [7]


def test_429_retry_after_is_capped(no_sleep):
    session = FakeSession(FakeResp(429, headers={"Retry-After": "600"}), FakeResp(200))
    fetch("https://x", session=session)
    assert no_sleep == [30]


def test_404_raises():
    with pytest.raises(FetchError, match="HTTP 404"):
        fetch("https://x", session=FakeSession(FakeResp(404)))
```

**Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'monitor.sources.base'`

**Step 4: Write implementation** — `monitor/sources/base.py`:
```python
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
```

**Step 5: Run tests**

Run: `python -m pytest tests/test_base.py -v`
Expected: 7 passed

**Step 6: Commit**
```bash
git add requirements.txt requirements-dev.txt pyproject.toml monitor tests/__init__.py tests/fakes.py tests/test_base.py
git commit -m "feat: project scaffold and HTTP fetch helper"
```

---

### Task 2: DownReport source

**Files:**
- Create: `monitor/sources/downreport.py`
- Test: `tests/test_downreport.py` (uses existing fixtures)

**Step 1: Write the failing test**
```python
from pathlib import Path

from monitor.sources import downreport
from monitor.sources.base import ERROR, OK, OUTAGE
from tests.fakes import FakeResp, FakeSession

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_ok_page():
    result = downreport.parse(load("downreport_ok.html"))
    assert result.status == OK
    assert "Массовых жалоб нет" in result.details


def test_warning_is_not_outage():
    result = downreport.parse(load("downreport_warning.html"))
    assert result.status == OK
    assert "Жалобы на сбои" in result.details


def test_danger_is_outage():
    html = (load("downreport_ok.html")
            .replace("text-success", "text-danger")
            .replace("Массовых жалоб нет", "Массовый сбой"))
    result = downreport.parse(html)
    assert result.status == OUTAGE
    assert "Массовый сбой" in result.details
    assert result.url == downreport.URL


def test_missing_status_is_error():
    assert downreport.parse("<html><body></body></html>").status == ERROR


def test_check_reports_fetch_error():
    result = downreport.check(FakeSession(FakeResp(403)))
    assert result.status == ERROR
    assert "403" in result.details


def test_check_parses_page():
    result = downreport.check(FakeSession(FakeResp(200, load("downreport_ok.html"))))
    assert result.status == OK
```

**Step 2: Run** `python -m pytest tests/test_downreport.py -v` — Expected: FAIL (ImportError)

**Step 3: Implement** `monitor/sources/downreport.py`:
```python
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
```

**Step 4: Run** `python -m pytest tests/test_downreport.py -v` — Expected: 6 passed

**Step 5: Commit**
```bash
git add monitor/sources/downreport.py tests/test_downreport.py tests/fixtures/downreport_*.html
git commit -m "feat: DownReport source"
```

---

### Task 3: DownRadar source

**Files:**
- Create: `monitor/sources/downradar.py`
- Test: `tests/test_downradar.py`

**Step 1: Write the failing test**
```python
import re
from pathlib import Path

from monitor.sources import downradar
from monitor.sources.base import ERROR, OK, OUTAGE
from tests.fakes import FakeResp, FakeSession

OK_HTML = (Path(__file__).parent / "fixtures" / "downradar_ok.html").read_text(encoding="utf-8")


def test_ok_page():
    result = downradar.parse(OK_HTML)
    assert result.status == OK
    assert re.search(r"нет проблем, жалоб за час: \d+", result.details)


def test_problems_is_outage():
    html = OK_HTML.replace("Статус Vtb.ru : нет проблем", "Статус Vtb.ru : есть проблемы")
    result = downradar.parse(html)
    assert result.status == OUTAGE
    assert result.details.startswith("есть проблемы")


def test_missing_status_is_error():
    assert downradar.parse("<html><body>пусто</body></html>").status == ERROR


def test_unknown_status_is_error():
    html = OK_HTML.replace("Статус Vtb.ru : нет проблем", "Статус Vtb.ru : загадка")
    assert downradar.parse(html).status == ERROR


def test_check_reports_fetch_error():
    result = downradar.check(FakeSession(FakeResp(500), FakeResp(502)))
    assert result.status == ERROR
```
Note: `test_check_reports_fetch_error` sleeps 2 s between retries; acceptable.

**Step 2: Run** `python -m pytest tests/test_downradar.py -v` — Expected: FAIL (ImportError)

**Step 3: Implement** `monitor/sources/downradar.py`:
```python
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
```

**Step 4: Run** `python -m pytest tests/test_downradar.py -v` — Expected: 5 passed

**Step 5: Commit**
```bash
git add monitor/sources/downradar.py tests/test_downradar.py tests/fixtures/downradar_ok.html
git commit -m "feat: DownRadar source"
```

---

### Task 4: Telegram channel source

**Files:**
- Create: `monitor/sources/telegram_channel.py`
- Test: `tests/test_telegram_channel.py`

**Step 1: Write the failing test**
```python
from pathlib import Path

import pytest

from monitor.sources import telegram_channel as tg
from monitor.sources.base import ERROR, OK
from tests.fakes import FakeResp, FakeSession

REAL = (Path(__file__).parent / "fixtures" / "telegram_bankvtb.html").read_text(encoding="utf-8")


def page(*posts):
    body = "".join(
        f'<div class="tgme_widget_message" data-post="bankvtb/{i}">'
        f'<div class="tgme_widget_message_text">{text}</div></div>'
        for i, text in posts)
    return f"<html><body>{body}</body></html>"


def test_parse_real_page():
    posts = tg.parse(REAL)
    assert posts and all(p_id > 0 for p_id, _ in posts)


@pytest.mark.parametrize("text, kind", [
    ("Наблюдаются затруднения в работе приложения", "outage"),
    ("Из-за технического сбоя не проходят переводы", "outage"),
    ("ВТБ Онлайн временно недоступен", "outage"),
    ("Работа приложения восстановлена", "recovery"),
    ("Сбой устранён, приносим извинения", "recovery"),
    ("Закажите кредитную карту", None),
    ("Начался сбор заявок на вклад", None),
])
def test_classify(text, kind):
    assert tg.classify(text) == kind


def test_first_run_only_remembers_last_id():
    session = FakeSession(FakeResp(200, page((10, "Наблюдаются затруднения"), (11, "Реклама"))))
    result, posts, last_id = tg.check(None, session)
    assert (result.status, posts, last_id) == (OK, [], 11)


def test_returns_new_matching_posts_only():
    html = page((10, "Наблюдаются затруднения"), (11, "Реклама"), (12, "Работа восстановлена"))
    result, posts, last_id = tg.check(10, FakeSession(FakeResp(200, html)))
    assert result.status == OK
    assert [(p.id, p.kind) for p in posts] == [(12, "recovery")]
    assert posts[0].url == "https://t.me/bankvtb/12"
    assert last_id == 12


def test_empty_page_is_error_and_keeps_last_id():
    result, posts, last_id = tg.check(5, FakeSession(FakeResp(200, "<html></html>")))
    assert (result.status, posts, last_id) == (ERROR, [], 5)
```

**Step 2: Run** `python -m pytest tests/test_telegram_channel.py -v` — Expected: FAIL (ImportError)

**Step 3: Implement** `monitor/sources/telegram_channel.py`:
```python
"""Official VTB Telegram channel via the public web preview t.me/s/."""
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from .base import ERROR, OK, FetchError, SourceResult, fetch

NAME = "telegram"
CHANNEL = "bankvtb"
URL = f"https://t.me/s/{CHANNEL}"

RECOVERY_RE = re.compile(
    r"восстановлен|восстановили|устранен|устранён|работа\w* в штатном режиме|работа\w* штатно")
OUTAGE_RE = re.compile(
    r"технически\w* (сбо|работ|неполад|проблем)|затруднени|временно недоступ|не проход"
    r"|наблюдаютс\w* (проблем|сбо|перебо)|перебо\w* в работе|\bсбо(й|я|е|ю|ем|ев|и)\b")


@dataclass
class Post:
    id: int
    text: str
    kind: str  # "outage" | "recovery"

    @property
    def url(self):
        return f"https://t.me/{CHANNEL}/{self.id}"


def classify(text):
    lowered = text.lower()
    if RECOVERY_RE.search(lowered):
        return "recovery"
    if OUTAGE_RE.search(lowered):
        return "outage"
    return None


def parse(html):
    """Returns [(post_id, text)] in page order."""
    posts = []
    for message in BeautifulSoup(html, "html.parser").select("div.tgme_widget_message[data-post]"):
        post_id = int(message["data-post"].rsplit("/", 1)[1])
        text_el = message.select_one(".tgme_widget_message_text")
        posts.append((post_id, text_el.get_text(" ", strip=True) if text_el else ""))
    return posts


def check(last_id, session=requests):
    """Returns (SourceResult, new matching posts, last seen post id)."""
    try:
        resp = fetch(URL, session=session)
    except FetchError as exc:
        return SourceResult(NAME, ERROR, str(exc), URL), [], last_id
    posts = parse(resp.content)
    if not posts:
        return SourceResult(NAME, ERROR, "не найдены посты на странице", URL), [], last_id
    newest = max(post_id for post_id, _ in posts)
    result = SourceResult(NAME, OK, f"последний пост #{newest}", URL)
    if last_id is None:  # first run: don't forward old posts
        return result, [], newest
    matched = []
    for post_id, text in posts:
        kind = classify(text)
        if post_id > last_id and kind:
            matched.append(Post(post_id, text, kind))
    return result, matched, max(newest, last_id)
```

**Step 4: Run** `python -m pytest tests/test_telegram_channel.py -v` — Expected: 11 passed

**Step 5: Commit**
```bash
git add monitor/sources/telegram_channel.py tests/test_telegram_channel.py tests/fixtures/telegram_bankvtb.html
git commit -m "feat: official VTB Telegram channel source"
```

---

### Task 5: DETECTOR404 source

**Files:**
- Create: `monitor/sources/detector404.py`
- Test: `tests/test_detector404.py`

**Step 1: Write the failing test**
```python
import json

from monitor.sources import detector404
from monitor.sources.base import DISABLED, ERROR, OK, OUTAGE
from tests.fakes import FakeResp, FakeSession


def resp(data):
    return FakeResp(200, json.dumps(data, ensure_ascii=False))


def test_no_token_is_disabled():
    session = FakeSession()
    assert detector404.check("", session).status == DISABLED
    assert session.calls == []


def test_sends_bearer_token():
    session = FakeSession(resp([]))
    detector404.check("secret", session)
    assert session.calls[0][2]["Authorization"] == "Bearer secret"


def test_vtb_alert_is_outage():
    data = [{"service": "Сбербанк"}, {"service": "Банк ВТБ", "reports": 87}]
    result = detector404.check("t", FakeSession(resp(data)))
    assert result.status == OUTAGE
    assert "87" in result.details


def test_alerts_wrapped_in_dict():
    result = detector404.check("t", FakeSession(resp({"data": [{"url": "/bank-vtb"}]})))
    assert result.status == OUTAGE


def test_no_vtb_alert_is_ok():
    result = detector404.check("t", FakeSession(resp([{"service": "Сбербанк"}])))
    assert result.status == OK


def test_bad_token_is_error():
    result = detector404.check("t", FakeSession(FakeResp(401)))
    assert result.status == ERROR
    assert "токен" in result.details


def test_unexpected_format_is_error():
    assert detector404.check("t", FakeSession(FakeResp(200, "<html>"))).status == ERROR
    assert detector404.check("t", FakeSession(resp({"x": 1}))).status == ERROR
```

**Step 2: Run** `python -m pytest tests/test_detector404.py -v` — Expected: FAIL (ImportError)

**Step 3: Implement** `monitor/sources/detector404.py`:
```python
"""DETECTOR404 API: active events, includes its own sensors in 34 Russian cities.

The alert item format is not documented, so items are matched by text.
After getting a token, check a real response and tighten `_is_vtb` if needed.
"""
import json

import requests

from .base import DISABLED, ERROR, OK, OUTAGE, FetchError, SourceResult, fetch

NAME = "detector404"
API_URL = "https://detector404.ru/api/v1/alerts"
URL = "https://detector404.ru/bank-vtb"
MARKERS = ("Банк ВТБ", "bank-vtb")


def _alert_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    return None


def _is_vtb(item):
    text = json.dumps(item, ensure_ascii=False)
    return any(marker in text for marker in MARKERS)


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
```

**Step 4: Run** `python -m pytest tests/test_detector404.py -v` — Expected: 7 passed

**Step 5: Commit**
```bash
git add monitor/sources/detector404.py tests/test_detector404.py
git commit -m "feat: DETECTOR404 API source"
```

---

### Task 6: Message formatting and Telegram sending

**Files:**
- Create: `monitor/notifier.py`
- Test: `tests/test_notifier.py`

`notifier` reads the state dict; its shape (built in Task 7):
```python
{"sources": {"downradar": {"last": "OUTAGE", "confirmed": "OUTAGE", "outage_streak": 2,
                           "error_streak": 0, "error_reported": False,
                           "details": "есть проблемы, жалоб за час: 87", "url": "https://..."}},
 "incident": {"started_at": "2026-10-04T11:03:00+00:00", "sources": ["downradar"]},
 "recovery_streak": 0, "telegram_last_id": 3812, "last_heartbeat": "2026-10-04"}
```

**Step 1: Write the failing test**
```python
from datetime import datetime, timezone

import pytest

from monitor import notifier
from monitor.sources.base import ERROR, OK, OUTAGE, SourceResult
from monitor.sources.telegram_channel import Post
from tests.fakes import FakeResp, FakeSession

NOW = datetime(2026, 10, 4, 11, 50, tzinfo=timezone.utc)  # 14:50 MSK


def src(last, details="", url="https://u"):
    return {"last": last, "confirmed": last, "details": details, "url": url}


STATE = {
    "sources": {"downradar": src(OUTAGE, "есть проблемы, жалоб за час: 87"),
                "downreport": src(OK), "telegram": src(OK)},
    "incident": {"started_at": "2026-10-04T11:03:00+00:00", "sources": ["downradar"]},
}


def test_incident_started():
    text = notifier.incident_started(STATE, ["downradar"], NOW)
    assert text.startswith("🔴 ВТБ: возможный сбой")
    assert "Источник: DownRadar" in text
    assert "жалоб за час: 87" in text
    assert "14:50 МСК" in text
    assert "🔴 DownRadar" in text and "🟢 DownReport" in text


def test_incident_confirmed_counts_enabled_detectors():
    text = notifier.incident_confirmed(STATE, "downradar")
    assert text.startswith("➕ ВТБ: сбой подтверждает DownRadar (1 из 2 детекторов)")


def test_incident_resolved_duration():
    text = notifier.incident_resolved(STATE, NOW)
    assert "47 мин" in text and "14:03" in text and "14:50" in text


def test_source_messages():
    result = SourceResult("downreport", ERROR, "HTTP 403")
    assert notifier.source_down(result) == "⚙️ DownReport не отвечает (HTTP 403). Сигналы этого источника не учитываются."
    assert notifier.source_back(result) == "⚙️ DownReport снова работает"


def test_official_post():
    text = notifier.official_post(Post(12, "Наблюдаются затруднения", "outage"))
    assert text.startswith("📢 ВТБ официально сообщает о проблемах")
    assert "«Наблюдаются затруднения»" in text
    assert "https://t.me/bankvtb/12" in text


def test_heartbeat():
    assert notifier.heartbeat(STATE).startswith("💓 Оповещатель ВТБ работает")


def test_send_posts_to_bot_api():
    session = FakeSession(FakeResp(200, "{}"))
    notifier.send("TOKEN", "42", "привет", session)
    method, url, payload = session.calls[0]
    assert url == "https://api.telegram.org/botTOKEN/sendMessage"
    assert payload == {"chat_id": "42", "text": "привет", "disable_web_page_preview": True}


def test_send_failure_raises():
    with pytest.raises(RuntimeError, match="400"):
        notifier.send("T", "1", "x", FakeSession(FakeResp(400, "Bad Request")))
```

**Step 2: Run** `python -m pytest tests/test_notifier.py -v` — Expected: FAIL (ImportError)

**Step 3: Implement** `monitor/notifier.py`:
```python
"""Message texts and Telegram Bot API sending. Plain text, no parse_mode."""
from datetime import datetime, timedelta, timezone

import requests

from .sources.base import DISABLED, ERROR, OK, OUTAGE

MSK = timezone(timedelta(hours=3))
DETECTORS = ("detector404", "downreport", "downradar")
TITLES = {"detector404": "DETECTOR404", "downreport": "DownReport",
          "downradar": "DownRadar", "telegram": "Telegram ВТБ"}
ICONS = {OK: "🟢", OUTAGE: "🔴", ERROR: "⚙️", DISABLED: "⚪"}


def _hm(moment):
    return moment.astimezone(MSK).strftime("%H:%M")


def _summary(state):
    lines = []
    for name in (*DETECTORS, "telegram"):
        source = state["sources"].get(name)
        if source:
            lines.append(f"{ICONS.get(source['last'], '❔')} {TITLES[name]}")
    return "\n".join(lines)


def _enabled_detectors(state):
    return sum(1 for name in DETECTORS
               if state["sources"].get(name, {}).get("last", DISABLED) != DISABLED)


def _source_line(state, name):
    source = state["sources"][name]
    line = f"• {TITLES[name]}: {source['details']}"
    return line + (f"\n  {source['url']}" if source["url"] else "")


def incident_started(state, names, now):
    return "\n".join([
        "🔴 ВТБ: возможный сбой",
        "Источник: " + ", ".join(TITLES[n] for n in names),
        *(_source_line(state, n) for n in names),
        f"Время: {_hm(now)} МСК",
        "",
        "Источники сейчас:",
        _summary(state),
    ])


def incident_confirmed(state, name):
    agreeing = len(state["incident"]["sources"])
    return (f"➕ ВТБ: сбой подтверждает {TITLES[name]} "
            f"({agreeing} из {_enabled_detectors(state)} детекторов)\n"
            + _source_line(state, name))


def incident_resolved(state, now):
    started = datetime.fromisoformat(state["incident"]["started_at"])
    minutes = int((now - started).total_seconds() // 60)
    return (f"🟢 ВТБ: сбой завершён\n"
            f"Длительность: {minutes} мин (с {_hm(started)} до {_hm(now)} МСК)")


def source_down(result):
    return (f"⚙️ {TITLES[result.source]} не отвечает ({result.details}). "
            "Сигналы этого источника не учитываются.")


def source_back(result):
    return f"⚙️ {TITLES[result.source]} снова работает"


def official_post(post):
    what = "о проблемах" if post.kind == "outage" else "о восстановлении"
    text = post.text if len(post.text) <= 700 else post.text[:700] + "…"
    return f"📢 ВТБ официально сообщает {what}\n«{text}»\n{post.url}"


def heartbeat(state):
    return "💓 Оповещатель ВТБ работает\n" + _summary(state)


def send(token, chat_id, text, session=requests):
    resp = session.post(f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": text,
                              "disable_web_page_preview": True},
                        timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API: HTTP {resp.status_code} {resp.text[:200]}")
```

**Step 4: Run** `python -m pytest tests/test_notifier.py -v` — Expected: 8 passed

**Step 5: Commit**
```bash
git add monitor/notifier.py tests/test_notifier.py
git commit -m "feat: alert message formatting and Telegram sending"
```

---

### Task 7: State engine

**Files:**
- Create: `monitor/state.py`
- Test: `tests/test_state.py`

**Step 1: Write the failing test**
```python
from datetime import datetime, timedelta, timezone

from monitor import state as st
from monitor.sources.base import DISABLED, ERROR, OK, OUTAGE, SourceResult

T0 = datetime(2026, 10, 4, 11, 0, tzinfo=timezone.utc)


def R(source, status, details="d"):
    return SourceResult(source, status, details, "https://u")


def run(state, *results, minute=0):
    return st.process(state, list(results), T0 + timedelta(minutes=minute))


def test_crowd_source_needs_two_runs():
    state = st.new_state()
    assert run(state, R("downradar", OUTAGE)) == []
    messages = run(state, R("downradar", OUTAGE), minute=5)
    assert len(messages) == 1 and messages[0].startswith("🔴")
    assert state["incident"]["sources"] == ["downradar"]


def test_single_crowd_spike_is_ignored():
    state = st.new_state()
    run(state, R("downradar", OUTAGE))
    assert run(state, R("downradar", OK), minute=5) == []
    assert state["incident"] is None


def test_detector404_is_immediate():
    messages = run(st.new_state(), R("detector404", OUTAGE))
    assert messages[0].startswith("🔴")


def test_second_source_confirms():
    state = st.new_state()
    run(state, R("detector404", OUTAGE), R("downreport", OUTAGE))
    messages = run(state, R("detector404", OUTAGE), R("downreport", OUTAGE), minute=5)
    assert len(messages) == 1
    assert messages[0].startswith("➕ ВТБ: сбой подтверждает DownReport (2 из 2")


def test_recovery_after_two_calm_runs():
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    assert run(state, R("detector404", OK), minute=5) == []
    messages = run(state, R("detector404", OK), minute=10)
    assert messages[0].startswith("🟢") and "10 мин" in messages[0]
    assert state["incident"] is None


def test_outage_returning_resets_recovery():
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    run(state, R("detector404", OK), minute=5)
    run(state, R("detector404", OUTAGE), minute=10)
    assert run(state, R("detector404", OK), minute=15) == []
    assert state["incident"] is not None


def test_source_error_reported_once_after_three_runs():
    state = st.new_state()
    assert run(state, R("downreport", ERROR, "HTTP 403")) == []
    assert run(state, R("downreport", ERROR, "HTTP 403")) == []
    messages = run(state, R("downreport", ERROR, "HTTP 403"))
    assert messages == ["⚙️ DownReport не отвечает (HTTP 403). Сигналы этого источника не учитываются."]
    assert run(state, R("downreport", ERROR)) == []
    assert run(state, R("downreport", OK)) == ["⚙️ DownReport снова работает"]


def test_erroring_source_keeps_incident_open():
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    run(state, R("detector404", ERROR), minute=5)
    run(state, R("detector404", ERROR), minute=10)
    assert state["incident"] is not None


def test_telegram_does_not_open_incident():
    state = st.new_state()
    run(state, R("telegram", OK))
    assert state["incident"] is None and state["sources"]["telegram"]["last"] == OK


def test_disabled_source_is_recorded_but_ignored():
    state = st.new_state()
    assert run(state, R("detector404", DISABLED)) == []
    assert state["sources"]["detector404"]["last"] == DISABLED


def test_heartbeat_due():
    state = st.new_state()
    assert st.heartbeat_due(state, datetime(2026, 10, 4, 6, 30, tzinfo=timezone.utc))  # 09:30 MSK
    assert not st.heartbeat_due(state, datetime(2026, 10, 4, 5, 0, tzinfo=timezone.utc))  # 08:00 MSK
    state["last_heartbeat"] = "2026-10-04"
    assert not st.heartbeat_due(state, datetime(2026, 10, 4, 6, 30, tzinfo=timezone.utc))


def test_save_and_load_roundtrip(tmp_path):
    state = st.new_state()
    run(state, R("detector404", OUTAGE))
    path = tmp_path / "state.json"
    st.save_state(path, state)
    assert st.load_state(path) == state
    assert st.load_state(tmp_path / "missing.json") == st.new_state()
```

**Step 2: Run** `python -m pytest tests/test_state.py -v` — Expected: FAIL (ImportError)

**Step 3: Implement** `monitor/state.py`:
```python
"""Turns source results plus previous state into messages. No I/O except load/save."""
import json
from datetime import datetime
from pathlib import Path

from . import notifier
from .notifier import DETECTORS, MSK
from .sources.base import DISABLED, ERROR, OK, OUTAGE

CROWD_CONFIRM_RUNS = 2
ERROR_ALERT_RUNS = 3
RECOVERY_RUNS = 2
IMMEDIATE = {"detector404"}
HEARTBEAT_HOUR_MSK = 9


def new_state():
    return {"sources": {}, "incident": None, "recovery_streak": 0,
            "telegram_last_id": None, "last_heartbeat": None}


def load_state(path):
    path = Path(path)
    state = new_state()
    if path.exists():
        state.update(json.loads(path.read_text(encoding="utf-8")))
    return state


def save_state(path, state):
    text = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    Path(path).write_text(text, encoding="utf-8")


def _update_source(state, result, messages):
    source = state["sources"].setdefault(result.source, {
        "last": OK, "confirmed": OK, "outage_streak": 0, "error_streak": 0,
        "error_reported": False, "details": "", "url": ""})
    source["last"] = result.status
    if result.status == DISABLED:
        return
    if result.status == ERROR:
        source["error_streak"] += 1
        if source["error_streak"] >= ERROR_ALERT_RUNS and not source["error_reported"]:
            source["error_reported"] = True
            messages.append(notifier.source_down(result))
        return  # keep last confirmed status while the source is silent
    if source["error_reported"]:
        messages.append(notifier.source_back(result))
    source.update(error_streak=0, error_reported=False,
                  details=result.details, url=result.url)
    if result.status == OUTAGE:
        source["outage_streak"] += 1
        needed = 1 if result.source in IMMEDIATE else CROWD_CONFIRM_RUNS
        if source["outage_streak"] >= needed:
            source["confirmed"] = OUTAGE
    else:
        source.update(outage_streak=0, confirmed=OK)


def process(state, results, now):
    messages = []
    for result in results:
        _update_source(state, result, messages)

    in_outage = [name for name in DETECTORS
                 if state["sources"].get(name, {}).get("confirmed") == OUTAGE]
    incident = state["incident"]
    if incident is None:
        if in_outage:
            state["incident"] = {"started_at": now.isoformat(), "sources": in_outage}
            state["recovery_streak"] = 0
            messages.append(notifier.incident_started(state, in_outage, now))
    elif in_outage:
        state["recovery_streak"] = 0
        for name in in_outage:
            if name not in incident["sources"]:
                incident["sources"].append(name)
                messages.append(notifier.incident_confirmed(state, name))
    else:
        state["recovery_streak"] += 1
        if state["recovery_streak"] >= RECOVERY_RUNS:
            messages.append(notifier.incident_resolved(state, now))
            state["incident"] = None
            state["recovery_streak"] = 0
    return messages


def heartbeat_due(state, now):
    local = now.astimezone(MSK)
    return local.hour >= HEARTBEAT_HOUR_MSK and state["last_heartbeat"] != local.date().isoformat()
```

**Step 4: Run** `python -m pytest tests/test_state.py -v` — Expected: 12 passed

**Step 5: Commit**
```bash
git add monitor/state.py tests/test_state.py
git commit -m "feat: state engine with incident transitions"
```

---

### Task 8: Entry point

**Files:**
- Create: `monitor/main.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing test**
```python
from datetime import datetime, timezone

import pytest

from monitor import main
from monitor import state as st
from monitor.sources.base import OK, OUTAGE, SourceResult
from monitor.sources.telegram_channel import Post

NOW = datetime(2026, 10, 4, 6, 30, tzinfo=timezone.utc)  # 09:30 MSK


@pytest.fixture
def sources(monkeypatch):
    results = {"detector404": OK, "downreport": OK, "downradar": OK}
    tg = {"posts": [], "last_id": 100}
    monkeypatch.setattr(main.detector404, "check",
                        lambda token, s: SourceResult("detector404", results["detector404"]))
    monkeypatch.setattr(main.downreport, "check",
                        lambda s: SourceResult("downreport", results["downreport"]))
    monkeypatch.setattr(main.downradar, "check",
                        lambda s: SourceResult("downradar", results["downradar"]))
    monkeypatch.setattr(main.telegram_channel, "check",
                        lambda last, s: (SourceResult("telegram", OK), tg["posts"], tg["last_id"]))
    return results, tg


def test_first_run_sends_heartbeat_and_saves_state(tmp_path, sources):
    sent = []
    main.run(tmp_path / "state.json", sent.append, now=NOW)
    assert len(sent) == 1 and sent[0].startswith("💓")
    saved = st.load_state(tmp_path / "state.json")
    assert saved["telegram_last_id"] == 100
    assert saved["last_heartbeat"] == "2026-10-04"


def test_outage_and_official_post(tmp_path, sources):
    results, tg = sources
    path = tmp_path / "state.json"
    main.run(path, lambda text: None, now=NOW)
    results["detector404"] = OUTAGE
    tg["posts"] = [Post(101, "Наблюдаются затруднения", "outage")]
    sent = []
    main.run(path, sent.append, now=NOW)
    assert [m[:2] for m in sent] == ["📢", "🔴"]


def test_send_failure_keeps_state_unsaved(tmp_path, sources):
    path = tmp_path / "state.json"

    def broken(text):
        raise RuntimeError("telegram down")

    with pytest.raises(RuntimeError):
        main.run(path, broken, now=NOW)
    assert not path.exists()
```

**Step 2: Run** `python -m pytest tests/test_main.py -v` — Expected: FAIL (ImportError)

**Step 3: Implement** `monitor/main.py`:
```python
"""One monitoring run: python -m monitor.main [--state state.json] [--dry-run]"""
import argparse
import os
from datetime import datetime, timezone

import requests

from . import notifier
from . import state as st
from .sources import detector404, downradar, downreport, telegram_channel


def run(state_path, send, now=None, session=None):
    session = session or requests.Session()
    now = now or datetime.now(timezone.utc)
    state = st.load_state(state_path)

    results = [
        detector404.check(os.environ.get("DETECTOR404_TOKEN", ""), session),
        downreport.check(session),
        downradar.check(session),
    ]
    tg_result, posts, last_id = telegram_channel.check(state["telegram_last_id"], session)
    results.append(tg_result)
    for result in results:
        print(f"[{result.source}] {result.status} {result.details}")

    messages = [notifier.official_post(post) for post in posts]
    messages += st.process(state, results, now)
    state["telegram_last_id"] = last_id
    if st.heartbeat_due(state, now):
        messages.append(notifier.heartbeat(state))
        state["last_heartbeat"] = now.astimezone(st.MSK).date().isoformat()

    for message in messages:
        send(message)  # raises on failure -> state not saved -> retried next run
    st.save_state(state_path, state)
    return messages


def main():
    parser = argparse.ArgumentParser(description="VTB outage notifier")
    parser.add_argument("--state", default="state.json")
    parser.add_argument("--dry-run", action="store_true", help="print messages instead of sending")
    args = parser.parse_args()

    if args.dry_run:
        send = print
    else:
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        chat_id = os.environ["TELEGRAM_CHAT_ID"]
        send = lambda text: notifier.send(token, chat_id, text)  # noqa: E731

    if os.environ.get("TEST_MESSAGE") == "true":
        send("✅ Тестовое сообщение: оповещатель ВТБ подключён")
    run(args.state, send)


if __name__ == "__main__":
    main()
```

**Step 4: Run** `python -m pytest -v` — Expected: all tests pass (≈59)

**Step 5: Live dry run against real sites (no Telegram needed)**

Run: `python -m monitor.main --dry-run --state "$TEMP/dry_state.json"`
Expected: four log lines; `[detector404] DISABLED нет токена`, `[downreport] OK Массовых жалоб нет` (or `Жалобы на сбои в работе`), `[downradar] OK нет проблем, жалоб за час: N`, `[telegram] OK последний пост #N`; then a printed 💓 message if after 09:00 MSK. If any source prints SOURCE_ERROR, check whether the site blocks the `vtb-outage-notifier` User-Agent; if so, switch `USER_AGENT` in `base.py` to a plain `"Mozilla/5.0"` and rerun.

**Step 6: Commit**
```bash
git add monitor/main.py tests/test_main.py
git commit -m "feat: entry point wiring sources, state and notifier"
```

---

### Task 9: GitHub Actions workflow, state file, README

**Files:**
- Create: `.github/workflows/monitor.yml`
- Create: `state.json`
- Create: `README.md`

**Step 1:** `state.json` — initial content:
```json
{
  "incident": null,
  "last_heartbeat": null,
  "recovery_streak": 0,
  "sources": {},
  "telegram_last_id": null
}
```

**Step 2:** `.github/workflows/monitor.yml`:
```yaml
name: vtb-monitor

on:
  schedule:
    - cron: "*/5 * * * *"
  workflow_dispatch:
    inputs:
      test_message:
        description: "Отправить тестовое сообщение"
        type: boolean
        default: false

permissions:
  contents: write

concurrency:
  group: vtb-monitor
  cancel-in-progress: false

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Check sources
        run: python -m monitor.main
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          DETECTOR404_TOKEN: ${{ secrets.DETECTOR404_TOKEN }}
          TEST_MESSAGE: ${{ inputs.test_message }}
      - name: Save state
        run: |
          git config user.name "vtb-monitor"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add state.json
          git diff --cached --quiet || (git commit -m "state: update" && git push)
```

**Step 3:** `README.md` (Russian): what it does, sources table, and setup:
1. Создать бота: @BotFather → `/newbot` → токен.
2. Написать боту любое сообщение, открыть `https://api.telegram.org/bot<TOKEN>/getUpdates`, взять `message.chat.id`.
3. DETECTOR404: зарегистрироваться на detector404.ru → профиль → API → сгенерировать токен (необязательно).
4. Публичный репозиторий на GitHub, запушить код.
5. Settings → Secrets and variables → Actions: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DETECTOR404_TOKEN`.
6. Actions → vtb-monitor → Run workflow с галкой «Отправить тестовое сообщение».
7. Локальная проверка: `python -m monitor.main --dry-run --state /tmp/s.json`.
Also: alert rules table from the design doc, and the note that state.json is public.

**Step 4: Validate YAML**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/monitor.yml', encoding='utf-8')); print('ok')"` (if PyYAML missing: `pip install pyyaml` first)
Expected: `ok`

**Step 5: Commit**
```bash
git add .github state.json README.md
git commit -m "feat: GitHub Actions workflow, initial state and README"
```

---

### Task 10: Publish to GitHub (needs the user)

Outward-facing — ask the user before each step.

1. Check `gh auth status`. If logged in, offer: `gh repo create vtb-monitor --public --source . --push`. Otherwise give manual steps.
2. User adds secrets (README step 5). With gh: `gh secret set TELEGRAM_BOT_TOKEN` etc. — the user types values themselves (`! gh secret set ...`), never pasted into chat.
3. `gh workflow run vtb-monitor -f test_message=true`, then `gh run watch` — expect success and a ✅ message in Telegram.
4. Confirm the scheduled runs appear in `gh run list --workflow vtb-monitor` after ~10–15 min.
5. When the DETECTOR404 token exists: run once locally with the token, inspect the real `/api/v1/alerts` JSON, and tighten `detector404._is_vtb` + tests to the real format.
