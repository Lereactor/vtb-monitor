"""One monitoring run.

python -m monitor.main [--state state.json] [--only detectors|channel] [--via telegram|github|print]

The VPS runs `--only detectors --via github` (Telegram is blocked there, so a
GitHub workflow relays the messages); GitHub Actions runs `--only channel`.
"""
import argparse
import base64
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import export, history, notifier, publish, sitecrypto, posts as official_posts
from . import state as st
from .services import CHANNEL_SERVICE, SERVICES
from .sources import detector404, downradar, downreport, sboyrf, telegram_channel
from .sources.base import ERROR, SourceResult

SOURCES = {module.NAME: module for module in (detector404, downreport, downradar, sboyrf)}
# DownRadar starts timing out on back-to-back requests: space out a second page on the same site
SAME_SITE_PAUSE = 5
sleep = time.sleep  # replaced in tests


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


def run(state_path, deliver, now=None, session=None, detectors=True, channel=True,
        history_path=None):
    """deliver(messages) must raise on failure: then state is not saved and the run is retried.

    history_path: also record every check and event there (the VPS run).
    """
    session = session or requests.Session()
    now = now or datetime.now(timezone.utc)
    state = st.load_state(state_path)

    results = {service_id: [] for service_id in SERVICES}
    posts = []
    if detectors:
        visited = set()
        for service_id, service in SERVICES.items():
            for name, page in service.detectors.items():
                if name in visited:
                    sleep(SAME_SITE_PAUSE)
                visited.add(name)
                result = _safe_check(name, SOURCES[name].check, session, page)
                print(f"[{service_id}/{result.source}] {result.status} {result.details}")
                results[service_id].append(result)
    if channel:
        tg_result, posts, last_id = _safe_telegram(state["telegram_last_id"], session)
        print(f"[{tg_result.source}] {tg_result.status} {tg_result.details}")
        results[CHANNEL_SERVICE].append(tg_result)
        state["telegram_last_id"] = last_id

    messages = [notifier.official_post(post) for post in posts]
    events = []
    for service_id, service_results in results.items():
        if service_results:
            messages += st.process(state, service_id, service_results, now, events)
    source_events = [e for e in events if e.kind in ("source_down", "source_back")]
    if source_events:
        messages.append(notifier.sources_changed(state, source_events))
    if st.heartbeat_due(state, now):
        messages.append(notifier.heartbeat(state))
        state["last_heartbeat"] = now.astimezone(st.MSK).date().isoformat()

    if messages:
        deliver(messages)
    st.save_state(state_path, state)
    if posts:  # for the site's history on the VPS, which cannot reach Telegram
        official_posts.append(Path(state_path).with_name("posts.json"), posts, now)
    if history_path:
        sent = [st.Event("message_sent", "", "", message) for message in messages]
        checked = {service_id: rs for service_id, rs in results.items() if rs}
        _after_run(history_path, now, checked, events + sent, state)
    return messages


def _after_run(history_path, now, results, events, state):
    """History and the site are extras: never let them break alerting."""
    try:
        db = history.connect(history_path)
    except Exception as exc:  # noqa: BLE001
        print(f"history: {exc.__class__.__name__}: {exc}")
        return
    try:
        try:
            history.record_run(db, now, results, events)
            history.roll_up(db, now)
            token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPO")
            if token and repo:
                official_posts.import_from_github(db, token, repo)
        except Exception as exc:  # noqa: BLE001
            print(f"history: {exc.__class__.__name__}: {exc}")
        try:
            _publish_site(db, state, now)
        except Exception as exc:  # noqa: BLE001
            print(f"site: {exc.__class__.__name__}: {exc}")
    finally:
        db.close()


def _publish_site(db, state, now):
    """Only where the site is configured (the VPS): SITE_REMOTE, SITE_KEY, SITE_SALT."""
    env = os.environ
    if not all(env.get(name) for name in ("SITE_REMOTE", "SITE_KEY", "SITE_SALT")):
        return
    public, private = export.build(db, state, now)
    key, salt = base64.b64decode(env["SITE_KEY"]), base64.b64decode(env["SITE_SALT"])
    blob = sitecrypto.encrypt_json(private, key, salt, int(env.get("SITE_ITER", sitecrypto.ITERATIONS)))
    publish.publish(env.get("SITE_WORK_DIR", "/var/lib/vtb-monitor/site-data"), env["SITE_REMOTE"],
                    public, blob, env.get("SITE_DEPLOY_KEY"))


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
    parser.add_argument("--history", help="SQLite file to record every check and event in")
    args = parser.parse_args()

    deliver = _deliverer("print" if args.dry_run else args.via)
    if os.environ.get("TEST_MESSAGE") == "true":
        deliver(["✅ Тестовое сообщение: оповещатель ВТБ подключён"])
    run(args.state, deliver,
        detectors=args.only in (None, "detectors"), channel=args.only in (None, "channel"),
        history_path=args.history)


if __name__ == "__main__":
    main()
