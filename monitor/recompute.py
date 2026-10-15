"""Rebuild the incidents in the history with the current alert rules.

Run it after an alert rule changes, with the timer stopped so no live run interleaves:

    systemctl stop vtb-monitor.timer
    python3 -m monitor.recompute --db /var/lib/vtb-monitor/history.db --state /var/lib/vtb-monitor/state.json
    systemctl start vtb-monitor.timer

Checks are re-read under the current source rules (DETECTOR404 sensors), replayed through the
alert state machine, and the incident and source events are replaced. Sent messages stay:
they are what really happened.
"""
import argparse
from collections import defaultdict
from datetime import datetime

from . import history
from . import state as st
from .services import SERVICES
from .sources import detector404
from .sources.base import OK, OUTAGE, SourceResult

REPLAYED = ("incident_started", "incident_confirmed", "incident_resolved", "source_down", "source_back")
RECOMPUTE_END = "закрыт при пересчёте истории"


def reclassify(source, status, details):
    """(status, details) under today's source rules."""
    if source == "detector404" and status == OUTAGE and detector404.COMPLAINTS_TEXT not in (details or ""):
        return OK, details + detector404.SENSORS_ONLY
    return status, details


def _reread_checks(db):
    rows = db.execute("SELECT rowid, source, status, details FROM checks WHERE status = ?", (OUTAGE,)).fetchall()
    for rowid, source, status, details in rows:
        new = reclassify(source, status, details)
        if new != (status, details):
            db.execute("UPDATE checks SET status = ?, details = ? WHERE rowid = ?", (*new, rowid))


def _replay(db):
    """[(run time, [Event])] and the final replay state."""
    runs = defaultdict(lambda: defaultdict(list))
    for ts, service_id, source, status, details in db.execute(
            "SELECT ts, service, source, status, details FROM checks ORDER BY ts, rowid"):
        runs[ts][service_id].append(SourceResult(source, status, details))
    state, out = st.new_state(), []
    for ts in sorted(runs):
        when, events = datetime.fromisoformat(ts), []
        for service_id, results in runs[ts].items():
            if service_id in SERVICES:  # retired services keep their old incidents
                st.process(state, service_id, results, when, events)
        if events:
            out.append((when, events))
    last = datetime.fromisoformat(max(runs)) if runs else None
    return out, state, last


def recompute(db, live_state):
    """live_state: the alerting state.json, so open incidents match what the live runs will close."""
    _reread_checks(db)
    replayed, state, last = _replay(db)
    db.execute(f"DELETE FROM events WHERE kind IN ({','.join('?' * len(REPLAYED))}) "
               f"AND service IN ({','.join('?' * len(SERVICES))})", (*REPLAYED, *SERVICES))
    for when, events in replayed:
        history.record_run(db, when, {}, events)
    for service_id in set(state["services"]) | set(live_state["services"]):
        replay_open = state["services"].get(service_id, {}).get("incident")
        live_open = live_state["services"].get(service_id, {}).get("incident")
        if replay_open and not live_open:
            history.record_run(db, last, {}, [st.Event("incident_resolved", service_id, "", RECOMPUTE_END)])
        elif live_open and not replay_open:
            history.record_run(db, datetime.fromisoformat(live_open["started_at"]), {},
                               [st.Event("incident_started", service_id, ",".join(live_open["sources"]))])
    db.commit()
    return sum(1 for _, events in replayed for e in events if e.kind == "incident_started")


def main():
    parser = argparse.ArgumentParser(description="Rebuild history incidents with the current rules")
    parser.add_argument("--db", required=True)
    parser.add_argument("--state", required=True, help="the live state.json")
    args = parser.parse_args()
    incidents = recompute(history.connect(args.db), st.load_state(args.state))
    print(f"incidents after recompute: {incidents}")


if __name__ == "__main__":
    main()
