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


def incident_resolved(state, now, partial=False):
    started = datetime.fromisoformat(state["incident"]["started_at"])
    minutes = int((now - started).total_seconds() // 60)
    text = (f"🟢 ВТБ: сбой завершён\n"
            f"Длительность: {minutes} мин (с {_hm(started)} до {_hm(now)} МСК)")
    if partial:
        text += "\n(часть источников не отвечает — данные неполные)"
    return text


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
