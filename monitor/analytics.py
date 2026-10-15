"""Incidents and analytics for the live site, computed from the history."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import history
from .notifier import INVEST_RE

POST_BEFORE = timedelta(minutes=30)  # the bank can post a little before the detectors react
POST_AFTER = timedelta(minutes=60)


@dataclass
class Incident:
    service: str
    start: datetime
    end: datetime | None = None   # None while still open
    sources: list = field(default_factory=list)  # in the order they joined
    peak: int | None = None       # max complaints/hour among the count sites during it
    post: dict | None = None      # the matching official post

    def minutes(self, now):
        return int(((self.end or now) - self.start).total_seconds() // 60)


def _post_service(text):
    return "invest" if INVEST_RE.search(text) else "vtb"


def incidents(db, now):
    """All incidents, oldest first, rebuilt from the incident events."""
    found, open_ = [], {}
    for ts, kind, service, source in db.execute(
            "SELECT ts, kind, service, source FROM events WHERE kind LIKE 'incident_%' ORDER BY ts, rowid"):
        when = datetime.fromisoformat(ts)
        if kind == "incident_started":
            open_[service] = Incident(service, when, sources=[s for s in source.split(",") if s])
            found.append(open_[service])
        elif kind == "incident_confirmed" and service in open_:
            open_[service].sources.append(source)
        elif kind == "incident_resolved" and service in open_:
            open_.pop(service).end = when
    posts = db.execute("SELECT id, ts, kind, text, url FROM posts WHERE kind = 'outage' ORDER BY ts").fetchall()
    for incident in found:
        end = history.iso(incident.end or now)
        incident.peak = db.execute(
            "SELECT max(count) FROM checks WHERE service = ? AND ts BETWEEN ? AND ?",
            (incident.service, history.iso(incident.start), end)).fetchone()[0]
        for post_id, ts, kind, text, url in posts:
            when = datetime.fromisoformat(ts)
            if (incident.start - POST_BEFORE <= when <= incident.start + POST_AFTER
                    and _post_service(text) == incident.service):
                incident.post = {"id": post_id, "ts": ts, "text": text, "url": url}
                break
    return found
