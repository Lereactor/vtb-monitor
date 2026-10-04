"""One monitoring run: python -m monitor.main [--state state.json] [--dry-run]"""
import argparse
import os
from datetime import datetime, timezone

import requests

from . import notifier
from . import state as st
from .sources import detector404, downradar, downreport, telegram_channel
from .sources.base import ERROR, SourceResult


def _crash_result(name, exc):
    return SourceResult(name, ERROR, f"внутренняя ошибка: {exc.__class__.__name__}: {exc}")


def _safe_check(name, check, *args):
    """One source's crash must not abort the run."""
    try:
        return check(*args)
    except Exception as exc:  # noqa: BLE001
        return _crash_result(name, exc)


def _safe_telegram(last_id, session):
    try:
        return telegram_channel.check(last_id, session)
    except Exception as exc:  # noqa: BLE001
        return _crash_result(telegram_channel.NAME, exc), [], last_id


def run(state_path, send, now=None, session=None):
    session = session or requests.Session()
    now = now or datetime.now(timezone.utc)
    state = st.load_state(state_path)

    results = [
        _safe_check(detector404.NAME, detector404.check,
                    os.environ.get("DETECTOR404_TOKEN", ""), session),
        _safe_check(downreport.NAME, downreport.check, session),
        _safe_check(downradar.NAME, downradar.check, session),
    ]
    tg_result, posts, last_id = _safe_telegram(state["telegram_last_id"], session)
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
