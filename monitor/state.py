"""Turns source results plus previous state into messages. No I/O except load/save and log lines.

Each monitored service keeps its own sources and incident under state["services"].
"""
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import notifier
from .notifier import MSK
from .services import SERVICES
from .sources.base import DISABLED, ERROR, OK, OUTAGE

CROWD_CONFIRM_RUNS = 2
ERROR_ALERT_RUNS = 6  # 30 min: DownRadar times out for 5-15 min several times a day
RECOVERY_RUNS = 2
IMMEDIATE = {"detector404"}  # its complaints flag is rare and has been right every time
# СБОЙ.РФ alone is not trusted: 11 of its 12 alerts over 10-15.10 were 15-minute bursts of
# 100-250 complaints with DownRadar at its usual 0-4, partly deleted by the site later.
# It can only confirm an outage that another site started, and cannot keep one open.
CONFIRM_ONLY = {"sboyrf"}
HEARTBEAT_HOUR_MSK = 9  # also the hour of the Monday weekly report
# a bank site alerts when no point in Russia gets an answer this many runs in a row (10 min),
# with at least this many points answering at all (check-host down leaves only the VPS)
SITE_DOWN_RUNS = 2
SITE_UP_RUNS = 2
SITE_MIN_POINTS = 2
SITE_ALERT_REGION = "ru"
# free space on the VPS: warn below the first, all clear above the second
DISK_LOW_MB = 500
DISK_OK_MB = 1000
SOURCE_DEFAULTS = {"last": OK, "confirmed": OK, "outage_streak": 0, "error_streak": 0,
                   "error_reported": False, "details": "", "url": ""}
SERVICE_KEYS = ("sources", "incident", "recovery_streak")


@dataclass(frozen=True)
class Event:
    """Something that happened in a run: kept in the history and used for messages.

    kind: incident_started | incident_confirmed | incident_resolved |
          source_down | source_back | site_down | site_back | message_sent
    """
    kind: str
    service: str
    source: str = ""
    text: str = ""


def new_state():
    return {"services": {}, "telegram_last_id": None, "last_heartbeat": None, "disk_low": False,
            "last_weekly": None}


def new_service_state():
    # sites: {host: {region: [up, total]}} from the latest availability check, for the messages;
    # site_alerts: {host: {"down": runs, "up": runs, "since": iso of the first failed check, "alerted": bool}}
    return {"sources": {}, "incident": None, "recovery_streak": 0, "sites": {}, "site_alerts": {}}


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
        if service_id in SERVICES:
            service(state, service_id)
        else:  # a service no longer monitored (ВТБ itself since 15.10.2026)
            del state["services"][service_id]
    return state


def service(state, service_id):
    """The service's entry, created or repaired as needed."""
    existing = state["services"].get(service_id)
    svc = {**new_service_state(), **(existing if isinstance(existing, dict) else {})}
    for key in ("sources", "sites", "site_alerts"):
        if not isinstance(svc[key], dict):
            svc[key] = {}
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
    """Via a temporary file, so a failed write (e.g. a full disk) keeps the previous state."""
    text = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = Path(f"{path}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


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
            events.append(Event("source_down", service_id, result.source, result.details))
        if source["error_reported"]:
            source["confirmed"] = OK  # silent too long: its old OUTAGE no longer counts
        return  # otherwise keep the latest non-error status while the source blips
    if source["error_reported"]:
        print(notifier.source_back(service_id, result))
        events.append(Event("source_back", service_id, result.source))
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
    """Returns the messages; events collects an Event for everything that happened."""
    events = [] if events is None else events
    svc = service(state, service_id)
    detectors = SERVICES[service_id].detectors
    messages = []
    incident_open = svc["incident"] is not None
    for result in results:
        _update_source(svc, service_id, result, incident_open, events)

    in_outage = [name for name in detectors if _counts(svc["sources"].get(name, {}))]
    leading = [name for name in in_outage if name not in CONFIRM_ONLY]
    incident = svc["incident"]
    if incident is None:
        if leading:
            svc["incident"] = {"started_at": now.isoformat(), "sources": in_outage}
            svc["recovery_streak"] = 0
            text = notifier.incident_started(svc, service_id, in_outage, now)
            messages.append(text)
            events.append(Event("incident_started", service_id, ",".join(in_outage), text))
    elif leading:
        svc["recovery_streak"] = 0
        for name in in_outage:
            if name not in incident["sources"]:
                incident["sources"].append(name)
                text = notifier.incident_confirmed(svc, service_id, name, len(in_outage))
                messages.append(text)
                events.append(Event("incident_confirmed", service_id, name, text))
    else:
        svc["recovery_streak"] += 1
        if svc["recovery_streak"] >= RECOVERY_RUNS:
            text = notifier.incident_resolved(svc, service_id, now)
            messages.append(text)
            events.append(Event("incident_resolved", service_id, "", text))
            svc["incident"] = None
            svc["recovery_streak"] = 0
    return messages


def set_sites(state, service_id, reach):
    """reach: {host: {region: availability.Reach}}; regions with no answers are left out."""
    service(state, service_id)["sites"] = {
        host: {region: [r.up, r.total] for region, r in regions.items() if r.total}
        for host, regions in reach.items()}


def heartbeat_due(state, now):
    local = now.astimezone(MSK)
    return local.hour >= HEARTBEAT_HOUR_MSK and state["last_heartbeat"] != local.date().isoformat()


def process_sites(state, service_id, reach, now, events=None):
    """reach: {host: {region: availability.Reach}} from this run. Returns the messages.

    A site is down when no point in Russia answered SITE_DOWN_RUNS runs in a row, and back
    after SITE_UP_RUNS runs with an answer. Too few points answering at all says nothing.
    """
    events = [] if events is None else events
    alerts = service(state, service_id)["site_alerts"]
    messages = []
    for host, regions in reach.items():
        home = regions.get(SITE_ALERT_REGION)
        if home is None or home.total < SITE_MIN_POINTS:
            continue
        alert = {"down": 0, "up": 0, "since": None, "alerted": False, **alerts.get(host, {})}
        alerts[host] = alert
        if home.up == 0:
            alert["up"] = 0
            alert["down"] = min(alert["down"] + 1, SITE_DOWN_RUNS)
            alert["since"] = alert["since"] or now.isoformat()
            if alert["down"] >= SITE_DOWN_RUNS and not alert["alerted"]:
                alert["alerted"] = True
                text = notifier.site_down(service_id, host, regions, datetime.fromisoformat(alert["since"]))
                messages.append(text)
                events.append(Event("site_down", service_id, host, text))
            continue
        alert["down"] = 0
        if not alert["alerted"]:
            alert.update(up=0, since=None)
            continue
        alert["up"] += 1
        if alert["up"] >= SITE_UP_RUNS:
            text = notifier.site_back(service_id, host, datetime.fromisoformat(alert["since"]), now)
            messages.append(text)
            events.append(Event("site_back", service_id, host, text))
            alert.update(up=0, since=None, alerted=False)
    return messages


def check_disk(state, free_mb):
    """A message when free space on the VPS gets low, and once more when it is back."""
    if free_mb is None:
        return []
    if free_mb < DISK_LOW_MB and not state.get("disk_low"):
        state["disk_low"] = True
        return [notifier.disk_low(free_mb)]
    if free_mb >= DISK_OK_MB and state.get("disk_low"):
        state["disk_low"] = False
        return [notifier.disk_ok(free_mb)]
    return []


def _week(local):
    year, week, _ = local.isocalendar()
    return f"{year}-W{week:02d}"


def weekly_due(state, now):
    """Once a week, from Monday HEARTBEAT_HOUR_MSK on (a later day if the VPS was down then)."""
    local = now.astimezone(MSK)
    started = local.weekday() > 0 or local.hour >= HEARTBEAT_HOUR_MSK
    return started and state.get("last_weekly") != _week(local)


def weekly_sent(state, now):
    state["last_weekly"] = _week(now.astimezone(MSK))
