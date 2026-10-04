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
