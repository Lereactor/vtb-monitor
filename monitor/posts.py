"""Official posts for the history: the GitHub channel run appends them to posts.json in the repo,
the VPS imports that file (Telegram is blocked on the VPS)."""
import json
from pathlib import Path

import requests

from .history import iso

KEEP = 300


def append(path, new_posts, now):
    """ts is when the post was found: within ~5 min of publication."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    data += [{"id": p.id, "ts": iso(now), "kind": p.kind, "text": p.text, "url": p.url}
             for p in new_posts]
    path.write_text(json.dumps(data[-KEEP:], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def import_from_github(db, token, repo, session=requests):
    """Upserts posts.json from the repo into the posts table; returns how many it read."""
    resp = session.get(f"https://api.github.com/repos/{repo}/contents/posts.json",
                       headers={"Authorization": f"Bearer {token}",
                                "Accept": "application/vnd.github.raw+json"}, timeout=15)
    if resp.status_code == 404:
        return 0
    if resp.status_code != 200:
        raise RuntimeError(f"posts.json: HTTP {resp.status_code} {resp.text[:100]}")
    rows = [(p["id"], p["ts"], p["kind"], p["text"], p["url"]) for p in json.loads(resp.text)]
    db.executemany("INSERT OR REPLACE INTO posts VALUES (?, ?, ?, ?, ?)", rows)
    db.commit()
    return len(rows)
