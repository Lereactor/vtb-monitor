"""Turns source results plus previous state into messages. No I/O except load/save and log lines.

Each monitored service keeps its own sources and incident under state["services"].
"""
import json
from pathlib import Path

from . import notifier
from .notifier import MSK
from .services import SERVICES
from .sources.base import DISABLED, ERROR, OK, OUTAGE

CROWD_CONFIRM_RUNS = 2
ERROR_ALERT_RUNS = 3
RECOVERY_RUNS = 2
IMMEDIATE = {"detector404"}
HEARTBEAT_HOUR_MSK = 9
SOURCE_DEFAULTS = {"last": OK, "confirmed": OK, "outage_streak": 0, "error_streak": 0,
                   "error_reported": False, "details": "", "url": ""}
SERVICE_KEYS = ("sources", "incident", "recovery_streak")


def new_state():
    return {"services": {}, "telegram_last_id": None, "last_heartbeat": None}


def new_service_state():
    return {"sources": {}, "incident": None, "recovery_streak": 0}


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
    if "services" not in data and any(key in data for key in SERVICE_KEYS):
        # before Мои Инвестиции there was one service: VTB, kept at the top level
        data["services"] = {"vtb": {key: data.pop(key) for key in SERVICE_KEYS if key in data}}
    state.update(data)
    if not isinstance(state["services"], dict):
        state["services"] = {}
    for service_id in list(state["services"]):
        service(state, service_id)
    return state


def service(state, service_id):
    """The service's entry, created or repaired as needed."""
    existing = state["services"].get(service_id)
    svc = {**new_service_state(), **(existing if isinstance(existing, dict) else {})}
    if not isinstance(svc["sources"], dict):
        svc["sources"] = {}
    incident = svc["incident"]
    if not (isinstance(incident, dict) and "started_at" in incident
            and isinstance(incident.get("sources"), list)):
        svc["incident"] = None
    state["services"][service_id] = svc
    return svc


def _source(svc, name):
    """The source's entry with any missing keys filled from SOURCE_DEFAULTS."""
    existing = svc["sources"].get(name)
    source = {**SOURCE_DEFAULTS, **(existing if isinstance(existing, dict) else {})}
    svc["sources"][name] = source
    return source


def save_state(path, state):
    text = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    Path(path).write_text(text, encoding="utf-8")


def _update_source(svc, service_id, result, incident_open, events):
    source = _source(svc, result.source)
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
            print(notifier.source_down(service_id, result))
            events.append((service_id, result.source, True))
        if source["error_reported"]:
            source["confirmed"] = OK  # silent too long: its old OUTAGE no longer counts
        return  # otherwise keep the latest non-error status while the source blips
    if source["error_reported"]:
        print(notifier.source_back(service_id, result))
        events.append((service_id, result.source, False))
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


def process(state, service_id, results, now, events=None):
    """events collects (service_id, source, broke) for checks that stopped or resumed answering."""
    events = [] if events is None else events
    svc = service(state, service_id)
    detectors = SERVICES[service_id].detectors
    messages = []
    incident_open = svc["incident"] is not None
    for result in results:
        _update_source(svc, service_id, result, incident_open, events)

    in_outage = [name for name in detectors if _counts(svc["sources"].get(name, {}))]
    incident = svc["incident"]
    if incident is None:
        if in_outage:
            svc["incident"] = {"started_at": now.isoformat(), "sources": in_outage}
            svc["recovery_streak"] = 0
            messages.append(notifier.incident_started(svc, service_id, in_outage, now))
    elif in_outage:
        svc["recovery_streak"] = 0
        for name in in_outage:
            if name not in incident["sources"]:
                incident["sources"].append(name)
                messages.append(notifier.incident_confirmed(svc, service_id, name, len(in_outage)))
    else:
        svc["recovery_streak"] += 1
        if svc["recovery_streak"] >= RECOVERY_RUNS:
            messages.append(notifier.incident_resolved(svc, service_id, now))
            svc["incident"] = None
            svc["recovery_streak"] = 0
    return messages


def heartbeat_due(state, now):
    local = now.astimezone(MSK)
    return local.hour >= HEARTBEAT_HOUR_MSK and state["last_heartbeat"] != local.date().isoformat()
