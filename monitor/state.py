"""Turns source results plus previous state into messages. No I/O except load/save."""
import json
from pathlib import Path

from . import notifier
from .notifier import DETECTORS, MSK
from .sources.base import DISABLED, ERROR, OK, OUTAGE

CROWD_CONFIRM_RUNS = 2
ERROR_ALERT_RUNS = 3
RECOVERY_RUNS = 2
IMMEDIATE = {"detector404"}
HEARTBEAT_HOUR_MSK = 9
SOURCE_DEFAULTS = {"last": OK, "confirmed": OK, "outage_streak": 0, "error_streak": 0,
                   "error_reported": False, "details": "", "url": ""}


def new_state():
    return {"sources": {}, "incident": None, "recovery_streak": 0,
            "telegram_last_id": None, "last_heartbeat": None}


def load_state(path):
    """Tolerates missing, corrupt, partial or old-format state files."""
    path = Path(path)
    state = new_state()
    if not path.exists():
        return state
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        print(f"WARNING: state file {path} is unreadable ({exc}); starting fresh")
        return new_state()
    if not isinstance(data, dict):
        print(f"WARNING: state file {path} is not an object; starting fresh")
        return new_state()
    state.update(data)
    if not isinstance(state["sources"], dict):
        state["sources"] = {}
    incident = state["incident"]
    if not (isinstance(incident, dict) and "started_at" in incident
            and isinstance(incident.get("sources"), list)):
        state["incident"] = None
    return state


def _source(state, name):
    """The source's entry with any missing keys filled from SOURCE_DEFAULTS."""
    existing = state["sources"].get(name)
    source = {**SOURCE_DEFAULTS, **(existing if isinstance(existing, dict) else {})}
    state["sources"][name] = source
    return source


def save_state(path, state):
    text = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    Path(path).write_text(text, encoding="utf-8")


def _update_source(state, result, messages, incident_open):
    source = _source(state, result.source)
    source["last"] = result.status
    if result.status == DISABLED:
        source.update(outage_streak=0, confirmed=OK)
        return
    if result.status == ERROR:
        # capped so a source that stays down does not rewrite state.json every run
        source["error_streak"] = min(source["error_streak"] + 1, ERROR_ALERT_RUNS)
        source["outage_streak"] = 0
        if source["error_streak"] >= ERROR_ALERT_RUNS and not source["error_reported"]:
            source["error_reported"] = True
            messages.append(notifier.source_down(result))
        if source["error_reported"]:
            source["confirmed"] = OK  # silent too long: its old OUTAGE no longer counts
        return  # otherwise keep the latest non-error status while the source blips
    if source["error_reported"]:
        messages.append(notifier.source_back(result))
    source.update(error_streak=0, error_reported=False)
    if result.status == OUTAGE:
        source.update(details=result.details, url=result.url)
        source["outage_streak"] += 1
        needed = 1 if result.source in IMMEDIATE or incident_open else CROWD_CONFIRM_RUNS
        if source["outage_streak"] >= needed:
            source["confirmed"] = OUTAGE
    else:
        # OK details change every run (hourly counts): don't store them, avoid state churn
        source.update(outage_streak=0, confirmed=OK, details="", url="")


def _counts(source):
    return (source.get("confirmed") == OUTAGE and source.get("last") != DISABLED
            and not source.get("error_reported"))


def _incomplete(state):
    # DISABLED (no token) is a deliberate setup, not missing data
    return any(state["sources"].get(name, {}).get("last") == ERROR for name in DETECTORS)


def process(state, results, now):
    messages = []
    incident_open = state["incident"] is not None
    for result in results:
        _update_source(state, result, messages, incident_open)

    in_outage = [name for name in DETECTORS if _counts(state["sources"].get(name, {}))]
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
                messages.append(notifier.incident_confirmed(state, name, len(in_outage)))
    else:
        state["recovery_streak"] += 1
        if state["recovery_streak"] >= RECOVERY_RUNS:
            messages.append(notifier.incident_resolved(state, now, _incomplete(state)))
            state["incident"] = None
            state["recovery_streak"] = 0
    return messages


def heartbeat_due(state, now):
    local = now.astimezone(MSK)
    return local.hour >= HEARTBEAT_HOUR_MSK and state["last_heartbeat"] != local.date().isoformat()
