import json
from datetime import datetime, timezone

import pytest

from monitor import history, posts
from monitor.sources.telegram_channel import Post
from tests.fakes import FakeResp, FakeSession

NOW = datetime(2026, 10, 4, 6, 30, tzinfo=timezone.utc)
ROW = {"id": 5, "ts": "2026-10-04T06:30:00+00:00", "kind": "outage", "text": "x",
       "url": "https://t.me/bankvtb/5"}


def test_append_keeps_found_posts(tmp_path):
    path = tmp_path / "posts.json"
    posts.append(path, [Post(5, "Наблюдаются затруднения", "outage")], NOW)
    posts.append(path, [Post(6, "Работа восстановлена", "recovery")], NOW)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert [p["id"] for p in data] == [5, 6]
    assert data[1] == {"id": 6, "ts": "2026-10-04T06:30:00+00:00", "kind": "recovery",
                       "text": "Работа восстановлена", "url": "https://t.me/bankvtb/6"}


def test_append_keeps_only_the_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(posts, "KEEP", 2)
    path = tmp_path / "posts.json"
    posts.append(path, [Post(i, "сбой", "outage") for i in range(1, 4)], NOW)
    assert [p["id"] for p in json.loads(path.read_text(encoding="utf-8"))] == [2, 3]


def test_import_upserts(tmp_path):
    db = history.connect(tmp_path / "h.db")
    session = FakeSession(FakeResp(200, json.dumps([ROW])), FakeResp(200, json.dumps([ROW])))
    assert posts.import_from_github(db, "tok", "me/repo", session) == 1
    assert posts.import_from_github(db, "tok", "me/repo", session) == 1
    assert db.execute("SELECT id, kind, url FROM posts").fetchall() == [(5, "outage", ROW["url"])]
    method, url, headers = session.calls[0]
    assert url == "https://api.github.com/repos/me/repo/contents/posts.json"
    assert headers["Authorization"] == "Bearer tok"
    assert headers["Accept"] == "application/vnd.github.raw+json"


def test_import_without_file_is_empty(tmp_path):
    db = history.connect(tmp_path / "h.db")
    assert posts.import_from_github(db, "tok", "me/repo", FakeSession(FakeResp(404))) == 0


def test_import_failure_raises(tmp_path):
    db = history.connect(tmp_path / "h.db")
    with pytest.raises(RuntimeError, match="502"):
        posts.import_from_github(db, "tok", "me/repo", FakeSession(FakeResp(502, "bad gateway")))
