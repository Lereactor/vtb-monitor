"""Message texts and Telegram Bot API sending. Plain text, no parse_mode."""
import json
import re
from datetime import datetime, timedelta, timezone

import requests

from .services import CHANNEL_SERVICE, SERVICES
from .sources.base import DISABLED

MSK = timezone(timedelta(hours=3))
TITLES = {"detector404": "DETECTOR404", "downreport": "DownReport",
          "downradar": "DownRadar", "sboyrf": "СБОЙ.РФ", "telegram": "Telegram ВТБ"}
INVEST_RE = re.compile(r"инвест|брокер", re.I)


def _hm(moment):
    return moment.astimezone(MSK).strftime("%H:%M")


def _title(service_id):
    return SERVICES[service_id].title


def _working_detectors(svc, service_id):
    """Sites whose verdict counts now: not switched off and not written off as broken."""
    return sum(1 for name in SERVICES[service_id].detectors
               if (source := svc["sources"].get(name))
               and source.get("last", DISABLED) != DISABLED and not source.get("error_reported"))


def _evidence(svc, name):
    source = svc["sources"][name]
    line = f"{TITLES[name]}: {source['details']}"
    return line + (f"\n{source['url']}" if source["url"] else "")


def _tally(svc, service_id, agreeing):
    return f"Сбой видят сайтов: {agreeing} из {_working_detectors(svc, service_id)}."


def incident_started(svc, service_id, names, now):
    lines = [f"🔴 {_title(service_id)}: похоже на сбой ({_hm(now)} МСК)",
             *(_evidence(svc, n) for n in names),
             _tally(svc, service_id, len(names))]
    if len(names) == 1:
        lines.append("Пока только один сайт — возможна ложная тревога.")
    return "\n".join(lines)


def incident_confirmed(svc, service_id, name, agreeing):
    """agreeing: detectors in outage right now (not all that ever joined)."""
    return "\n".join([f"🔴 {_title(service_id)}: сбой подтверждает ещё один сайт",
                      _evidence(svc, name),
                      _tally(svc, service_id, agreeing)])


def incident_resolved(svc, service_id, now):
    started = datetime.fromisoformat(svc["incident"]["started_at"])
    minutes = int((now - started).total_seconds() // 60)
    return (f"✅ {_title(service_id)}: всё в норме\n"
            f"Сбой длился {minutes} мин ({_hm(started)}–{_hm(now)} МСК).")


def source_down(service_id, result):
    """Log line; the chat gets sources_changed, with the status of every check."""
    return f"{_title(service_id)} · {TITLES[result.source]} не отвечает ({result.details})"


def source_back(service_id, result):
    return f"{_title(service_id)} · {TITLES[result.source]} снова отвечает"


def _checks(state):
    """One line per service: which checks answer (✅) and which are written off as broken (❌)."""
    lines = []
    for service_id, service in SERVICES.items():
        sources = state["services"].get(service_id, {}).get("sources", {})
        names = [n for n in [*service.detectors, "telegram"]
                 if n in sources and sources[n].get("last") != DISABLED]
        if names:
            marks = ", ".join(("❌ " if sources[n].get("error_reported") else "✅ ") + TITLES[n]
                              for n in names)
            lines.append(f"{_title(service_id)}: {marks}")
    return lines


def _outage_line(state):
    open_incidents = [f"{_title(sid)} (с {_hm(datetime.fromisoformat(svc['incident']['started_at']))} МСК)"
                      for sid, svc in state["services"].items()
                      if sid in SERVICES and svc.get("incident")]
    return ("Сейчас идёт сбой: " + ", ".join(open_incidents) + "." if open_incidents
            else "Сбоев сейчас нет.")


def sources_changed(state, events):
    """events: (service_id, source name, broke) for checks that stopped or resumed answering."""
    grouped = {}
    for service_id, name, broke in events:
        grouped.setdefault((broke, name), []).append(_title(service_id))
    lines = [("⚠️ Перестал отвечать " if broke else "✅ Снова отвечает ")
             + f"{TITLES[name]} ({', '.join(services)})."
             for (broke, name), services in grouped.items()]
    broken = {name for broke, name in grouped if broke}
    if broken - {"telegram"}:
        lines.append("Это сайт со статистикой жалоб, а не сам банк. Следим по остальным.")
    if "telegram" in broken:
        lines.append("Пока не видим новых официальных постов ВТБ.")
    return "\n".join([*lines, "", "Проверки:", *_checks(state), "", _outage_line(state)])


def official_post(post):
    what = "о проблемах" if post.kind == "outage" else "о восстановлении"
    about = " (Мои Инвестиции)" if INVEST_RE.search(post.text) else ""
    text = post.text if len(post.text) <= 700 else post.text[:700] + "…"
    return f"📢 ВТБ официально сообщает {what}{about}\n«{text}»\n{post.url}"


def heartbeat(state):
    return "\n".join(["☀️ Оповещатель ВТБ работает, проверяет каждые 5 минут.",
                      "", "Проверки:", *_checks(state), "", _outage_line(state)])


MAX_TEXT = 4000  # Telegram's limit is 4096

UNDELIVERABLE = ("message is too long", "text must be non-empty")


def send(token, chat_id, text, session=requests):
    """Raises on transient failures (state not saved, retried next run).

    A 400 about the message text itself can never succeed: log it and move on,
    otherwise it would block every later message forever. Any other 400
    (chat not found, group migrated) is a setup error and must fail loudly.
    """
    text = _clamp(text)
    resp = session.post(f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": text,
                              "disable_web_page_preview": True},
                        timeout=15)
    if resp.status_code == 400 and any(reason in resp.text for reason in UNDELIVERABLE):
        print(f"Telegram API rejected a message, dropping it: HTTP 400 {resp.text[:200]}")
        return
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API: HTTP {resp.status_code} {resp.text[:200]}")


def _clamp(text):
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT - 1] + "…"


def dispatch_github(token, repo, messages, session=requests):
    """Hand messages to the `notify` workflow, which sends them to Telegram.

    Used where api.telegram.org is blocked but api.github.com is not.
    """
    resp = session.post(
        f"https://api.github.com/repos/{repo}/actions/workflows/notify.yml/dispatches",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"ref": "main",
              "inputs": {"messages": json.dumps([_clamp(m) for m in messages], ensure_ascii=False)}},
        timeout=15)
    if resp.status_code != 204:
        raise RuntimeError(f"GitHub dispatch: HTTP {resp.status_code} {resp.text[:200]}")

