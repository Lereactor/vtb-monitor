"""One-off: rebuild the history from journal lines written before the history existed.

    journalctl -u vtb-monitor.service -o short-iso --no-pager > journal.txt
    python3 -m monitor.backfill --db /var/lib/vtb-monitor/history.db journal.txt

Incidents are rebuilt by replaying the checks through the alert state machine.
"""
import argparse
import re
from datetime import datetime

from . import history
from . import state as st
from .services import SERVICES
from .sources.base import SourceResult

LINE_RE = re.compile(r"^(\S+) \S+ python3\[(\d+)\]: \[(\w+)/(\w+)\] "
                     r"(OK|OUTAGE|SOURCE_ERROR|DISABLED) ?(.*)$")
BACKFILL_END = "конец восстановленной истории"


def parse_journal(lines):
    """[(run time, {service: [SourceResult]})], one run per process id, oldest first."""
    runs = {}
    for line in lines:
        match = LINE_RE.match(line.strip())
        if not match or match.group(3) not in SERVICES:
            continue
        ts, pid, service_id, source, status, details = match.groups()
        _, results = runs.setdefault(pid, (datetime.fromisoformat(ts), {}))
        results.setdefault(service_id, []).append(SourceResult(source, status, details))
    return sorted(runs.values(), key=lambda run: run[0])


def backfill(db, lines):
    """Records the runs older than the first live check; returns how many."""
    first_live = db.execute("SELECT min(ts) FROM checks").fetchone()[0]
    state = st.new_state()
    done, last = 0, None
    for when, results in parse_journal(lines):
        if first_live and history.iso(when) >= first_live:
            break
        events = []
        for service_id, service_results in results.items():
            st.process(state, service_id, service_results, when, events)
        history.record_run(db, when, results, events)
        done, last = done + 1, when
    # the live history has its own state, so an incident left open here would never end
    still_open = [st.Event("incident_resolved", service_id, "", BACKFILL_END)
                  for service_id, svc in state["services"].items() if svc["incident"]]
    if still_open:
        history.record_run(db, last, {}, still_open)
    return done


def main():
    parser = argparse.ArgumentParser(description="Backfill the history from journal lines")
    parser.add_argument("--db", required=True)
    parser.add_argument("journal")
    args = parser.parse_args()
    with open(args.journal, encoding="utf-8") as f:
        lines = f.read().splitlines()
    print(f"backfilled runs: {backfill(history.connect(args.db), lines)}")


if __name__ == "__main__":
    main()
