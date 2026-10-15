"""What the live site reads: public.json for everyone, and a private part for the password."""
from datetime import datetime, timedelta

from . import analytics, history
from .notifier import TITLES
from .services import SERVICES
from .sources import detector404, downradar, downreport, sboyrf
from .sources.base import DISABLED, OK, OUTAGE

# the page each tile links to: where its numbers come from
PAGE_URL = {m.NAME: m._url for m in (detector404, downradar, downreport, sboyrf)}

SPARK_HOURS = 24
PRIVATE_ALL_HOURS = 48     # every check
PRIVATE_ISSUES_DAYS = 30   # only checks that were not OK


def _status(source):
    """ok / outage / broken / disabled / unknown, as the alerting state sees it now."""
    if not source:
        return "unknown"
    if source.get("error_reported"):
        return "broken"
    if source.get("last") == DISABLED:
        return "disabled"
    return "outage" if source.get("confirmed") == OUTAGE else "ok"


def _sites_now(db, service_id, now):
    """Each bank site: the latest answer per region and 24 hours of (up, total) per region."""
    since = history.iso(now - timedelta(hours=SPARK_HOURS))
    sites = []
    for host in SERVICES[service_id].sites:
        regions = {}
        for region in ("ru", "world"):
            last = db.execute("SELECT ts, up, total, ms, details FROM reach WHERE service = ? AND host = ? "
                              "AND region = ? ORDER BY ts DESC LIMIT 1", (service_id, host, region)).fetchone()
            spark = db.execute("SELECT ts, up, total FROM reach WHERE service = ? AND host = ? AND region = ? "
                               "AND ts >= ? ORDER BY ts", (service_id, host, region, since)).fetchall()
            regions[region] = {"checked_at": last[0], "up": last[1], "total": last[2], "ms": last[3],
                               "details": last[4], "spark": [list(row) for row in spark]} if last else None
        sites.append({"host": host, "url": f"https://{host}/", **regions})
    return sites


def _now_block(db, state, service_id, now):
    svc = state["services"].get(service_id, {})
    since = history.iso(now - timedelta(hours=SPARK_HOURS))
    sources = {}
    for name in SERVICES[service_id].detectors:
        status = _status(svc.get("sources", {}).get(name))
        last = db.execute("SELECT ts, count, details FROM checks WHERE service = ? AND source = ? "
                          "ORDER BY ts DESC LIMIT 1", (service_id, name)).fetchone()
        spark = db.execute("SELECT ts, count, status FROM checks WHERE service = ? AND source = ? "
                           "AND ts >= ? ORDER BY ts", (service_id, name, since)).fetchall()
        sources[name] = {"status": status, "checked_at": last[0] if last else None,
                         "count": last[1] if last else None, "details": last[2] if last else "",
                         "spark": [list(row) for row in spark]}
    incident = svc.get("incident")
    if incident:
        incident = {"start": history.iso(datetime.fromisoformat(incident["started_at"])),
                    "sources": incident["sources"]}
    return {"incident": incident,
            "working": sum(1 for s in sources.values() if s["status"] in ("ok", "outage")),
            "total": len(sources), "sources": sources, "sites": _sites_now(db, service_id, now)}


def _incident(incident, now):
    return {"service": incident.service, "start": history.iso(incident.start),
            "end": history.iso(incident.end) if incident.end else None,
            "minutes": incident.minutes(now), "sources": incident.sources,
            "peak": incident.peak, "solo": len(incident.sources) == 1, "post": incident.post}


def build(db, state, now):
    """(public, private) payloads. state is the live alerting state."""
    public = {
        "generated_at": history.iso(now),
        "services": {sid: {"title": s.title,
                           "sources": [{"id": name, "title": TITLES[name], "url": PAGE_URL[name](page)}
                                       for name, page in s.detectors.items()]}
                     for sid, s in SERVICES.items()},
        "now": {sid: _now_block(db, state, sid, now) for sid in SERVICES},
        "incidents": [_incident(i, now) for i in reversed(analytics.incidents(db, now))],  # monitored only
        "analytics": analytics.report(db, now),
    }
    monitored = ",".join("?" * len(SERVICES))
    checks = db.execute(
        f"SELECT ts, service, source, status, count, details FROM checks WHERE service IN ({monitored}) "
        "AND (ts >= ? OR (ts >= ? AND status != ?)) ORDER BY ts DESC, rowid",
        (*SERVICES, history.iso(now - timedelta(hours=PRIVATE_ALL_HOURS)),
         history.iso(now - timedelta(days=PRIVATE_ISSUES_DAYS)), OK)).fetchall()
    private = {
        "checks": [list(row) for row in checks],
        "source_events": [list(row) for row in db.execute(
            f"SELECT ts, kind, service, source, text FROM events WHERE service IN ({monitored}) "
            "AND kind IN ('source_down', 'source_back') ORDER BY ts DESC, rowid", tuple(SERVICES))],
        # bank sites that did not answer from every point: 30 days, with which points failed
        "reach": [list(row) for row in db.execute(
            f"SELECT ts, service, host, region, up, total, details FROM reach WHERE service IN ({monitored}) "
            "AND ts >= ? AND up < total ORDER BY ts DESC, rowid",
            (*SERVICES, history.iso(now - timedelta(days=PRIVATE_ISSUES_DAYS))))],
        "messages": [list(row) for row in db.execute(
            "SELECT ts, text FROM events WHERE kind = 'message_sent' ORDER BY ts DESC, rowid")],
    }
    return public, private
