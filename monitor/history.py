"""Every check and event, in SQLite, for the live site. Callers must not let errors here block alerts."""
import re
import sqlite3
from datetime import timedelta, timezone

COUNT_RE = re.compile(r"жалоб за час:\s*(\d+)")
KEEP_CHECKS_DAYS = 90  # older checks are rolled up into hourly totals
SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (ts TEXT, service TEXT, source TEXT, status TEXT,
                                   count INTEGER, details TEXT);
CREATE INDEX IF NOT EXISTS checks_ts ON checks (ts);
CREATE TABLE IF NOT EXISTS hourly (hour TEXT, service TEXT, source TEXT, checks INTEGER,
                                   outages INTEGER, errors INTEGER, max_count INTEGER,
                                   PRIMARY KEY (hour, service, source));
CREATE TABLE IF NOT EXISTS events (ts TEXT, kind TEXT, service TEXT, source TEXT, text TEXT);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts);
CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, text TEXT, url TEXT);
CREATE TABLE IF NOT EXISTS reach (ts TEXT, service TEXT, host TEXT, region TEXT, up INTEGER,
                                  total INTEGER, ms INTEGER, details TEXT);
CREATE INDEX IF NOT EXISTS reach_ts ON reach (ts);
"""


def connect(path):
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def iso(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def count_from_details(details):
    """Complaints per hour, for the sites that give a number (DownRadar, СБОЙ.РФ)."""
    match = COUNT_RE.search(details or "")
    return int(match.group(1)) if match else None


def record_run(db, now, results, events, reach=None):
    """results: {service_id: [SourceResult]}; events: [state.Event];
    reach: {service_id: {host: {region: availability.Reach}}}."""
    ts = iso(now)
    db.executemany("INSERT INTO reach VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   [(ts, service_id, host, r.region, r.up, r.total, r.ms, r.details())
                    for service_id, hosts in (reach or {}).items()
                    for host, regions in hosts.items() for r in regions.values() if r.total])
    db.executemany("INSERT INTO checks VALUES (?, ?, ?, ?, ?, ?)",
                   [(ts, service_id, r.source, r.status, count_from_details(r.details), r.details)
                    for service_id, service_results in results.items() for r in service_results])
    db.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                   [(ts, e.kind, e.service, e.source, e.text) for e in events])
    db.commit()


def roll_up(db, now):
    """Whole hours older than KEEP_CHECKS_DAYS move from checks to hourly."""
    cutoff = iso((now - timedelta(days=KEEP_CHECKS_DAYS)).replace(minute=0, second=0, microsecond=0))
    db.execute("""INSERT OR REPLACE INTO hourly
                  SELECT substr(ts, 1, 13), service, source, count(*), sum(status = 'OUTAGE'),
                         sum(status = 'SOURCE_ERROR'), max(count)
                  FROM checks WHERE ts < ? GROUP BY 1, 2, 3""", (cutoff,))
    db.execute("DELETE FROM checks WHERE ts < ?", (cutoff,))
    db.execute("DELETE FROM reach WHERE ts < ?", (cutoff,))  # an extra indicator: no roll-up
    db.commit()
