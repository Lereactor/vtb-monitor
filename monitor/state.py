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
