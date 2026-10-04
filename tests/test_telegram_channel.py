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
