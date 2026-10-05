"""One monitoring run.

python -m monitor.main [--state state.json] [--only detectors|channel] [--via telegram|github|print]

The VPS runs `--only detectors --via github` (Telegram is blocked there, so a
GitHub workflow relays the messages); GitHub Actions runs `--only channel`.
"""
import argparse
import os
import sys
from datetime import datetime, timezone

import requests

from . import notifier
from . import state as st
from .sources import detector404, downradar, downreport, sboyrf, telegram_channel
from .sources.base import ERROR, SourceResult


def _crash_result(name, exc):
    details = f"внутренняя ошибка: {exc.__class__.__name__}: {exc}"
    return SourceResult(name, ERROR, details[:200])


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


def run(state_path, deliver, now=None, session=None, detectors=True, channel=True):
    """deliver(messages) must raise on failure: then state is not saved and the run is retried."""
    session = session or requests.Session()
    now = now or datetime.now(timezone.utc)
    state = st.load_state(state_path)

    results, posts = [], []
    if detectors:
        results += [
            _safe_check(detector404.NAME, detector404.check, session),
            _safe_check(downreport.NAME, downreport.check, session),
            _safe_check(downradar.NAME, downradar.check, session),
            _safe_check(sboyrf.NAME, sboyrf.check, session),
        ]
    if channel:
        tg_result, posts, last_id = _safe_telegram(state["telegram_last_id"], session)
        results.append(tg_result)
        state["telegram_last_id"] = last_id
    for result in results:
        print(f"[{result.source}] {result.status} {result.details}")

    messages = [notifier.official_post(post) for post in posts]
    messages += st.process(state, results, now)
    if st.heartbeat_due(state, now):
        messages.append(notifier.heartbeat(state))
        state["last_heartbeat"] = now.astimezone(st.MSK).date().isoformat()

    if messages:
        deliver(messages)
    st.save_state(state_path, state)
    return messages


def _deliverer(via):
    if via == "print":
        return lambda messages: print("\n\n".join(messages))
    if via == "github":
        token, repo = os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPO"]
        return lambda messages: notifier.dispatch_github(token, repo, messages)
    token, chat_id = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]

    def deliver(messages):
        for message in messages:
            notifier.send(token, chat_id, message)
    return deliver


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # emoji on a cp1251 Windows console
    parser = argparse.ArgumentParser(description="VTB outage notifier")
    parser.add_argument("--state", default="state.json")
    parser.add_argument("--only", choices=("detectors", "channel"),
                        help="check only outage detectors or only the official Telegram channel")
    parser.add_argument("--via", choices=("telegram", "github", "print"), default="telegram",
                        help="send directly, relay through the GitHub notify workflow, or print")
    parser.add_argument("--dry-run", action="store_true", help="same as --via print")
    args = parser.parse_args()

    deliver = _deliverer("print" if args.dry_run else args.via)
    if os.environ.get("TEST_MESSAGE") == "true":
        deliver(["✅ Тестовое сообщение: оповещатель ВТБ подключён"])
    run(args.state, deliver,
        detectors=args.only in (None, "detectors"), channel=args.only in (None, "channel"))


if __name__ == "__main__":
    main()
