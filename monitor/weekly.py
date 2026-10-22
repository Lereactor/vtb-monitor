"""Weekly report: a picture of the site's «Аналитика» tab for 7 days, sent to the chat.

python -m monitor.weekly [--dry-run out.png]

Runs in the GitHub `weekly` workflow (Telegram is blocked on the VPS); the VPS starts it on
Monday mornings, like everything else here. Needs Playwright with Chromium.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

import requests

from .notifier import MSK

SITE = "https://lereactor.github.io/vtb-monitor-live/"
PAGE = SITE + "#tab=analytics&s=all&p=7d"
PUBLIC_JSON = "https://raw.githubusercontent.com/Lereactor/vtb-monitor-live/data/public.json"
WIDTH = 1000  # CSS pixels: every table column fits with the wider fonts of the Linux runner
SCALE = 2
MAX_CAPTION = 1024  # Telegram's limit for a photo caption


def caption(public):
    """Title with the dates, the plain-language summary of the 7 days, and the link."""
    end = datetime.fromisoformat(public["generated_at"]).astimezone(MSK)
    start = end - timedelta(days=7)
    title = f"📊 Сбои ВТБ за неделю {start:%d.%m}–{end:%d.%m}"
    summary = public["analytics"]["7d|all"]["summary"]
    link = f"Подробнее: {PAGE}"
    room = MAX_CAPTION - len(title) - len(link) - 4
    if len(summary) > room:
        summary = summary[:room - 1] + "…"
    return f"{title}\n\n{summary}\n\n{link}"


def screenshot(path):
    from playwright.sync_api import sync_playwright  # only in the workflow

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.environ.get("BROWSER_CHANNEL") or None)
        page = browser.new_page(viewport={"width": WIDTH, "height": 900}, device_scale_factor=SCALE,
                                locale="ru-RU", timezone_id="Europe/Moscow", color_scheme="light")
        page.goto(PAGE, wait_until="networkidle")
        page.wait_for_selector(".summary", timeout=30_000)
        page.wait_for_timeout(1500)  # charts measure their width after the first paint
        page.screenshot(path=path, full_page=True)
        browser.close()


def send_photo(token, chat_id, path, text, session=requests):
    with open(path, "rb") as photo:
        resp = session.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                            data={"chat_id": chat_id, "caption": text},
                            files={"photo": ("vtb-week.png", photo, "image/png")}, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API: HTTP {resp.status_code} {resp.text[:200]}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Send the weekly analytics picture")
    parser.add_argument("--dry-run", metavar="PNG", help="only save the picture and print the caption")
    args = parser.parse_args()

    resp = requests.get(PUBLIC_JSON, timeout=30)
    resp.raise_for_status()
    text = caption(resp.json())
    path = args.dry_run or "vtb-week.png"
    screenshot(path)
    print(text)
    if not args.dry_run:
        send_photo(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"], path, text)


if __name__ == "__main__":
    main()
