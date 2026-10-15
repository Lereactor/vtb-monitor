import json
import subprocess

from monitor import publish


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, encoding="utf-8").stdout.strip()


def test_publish_force_pushes_one_commit(tmp_path):
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", str(remote))
    work = tmp_path / "work"
    publish.publish(work, str(remote), {"n": 1, "text": "мир"}, {"ct": "x"})
    publish.publish(work, str(remote), {"n": 2, "text": "мир"}, {"ct": "y"})
    assert json.loads(git("--git-dir", str(remote), "show", "data:public.json")) == {"n": 2, "text": "мир"}
    assert json.loads(git("--git-dir", str(remote), "show", "data:private.enc")) == {"ct": "y"}
    assert git("--git-dir", str(remote), "rev-list", "--count", "data") == "1"


def test_ssh_command_uses_the_deploy_key(tmp_path):
    env = publish.git_env(str(tmp_path / "key"))
    assert f"-i {tmp_path / 'key'}" in env["GIT_SSH_COMMAND"]
    assert "IdentitiesOnly=yes" in env["GIT_SSH_COMMAND"]
