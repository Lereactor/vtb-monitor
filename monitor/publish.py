"""Force-push public.json + private.enc as a single commit to the site repo's `data` branch.

Not GitHub Pages: Pages allows about 10 builds an hour and this runs every 5 minutes, so the
site reads the branch from raw.githubusercontent.com instead.
"""
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path


def git_env(ssh_key=None):
    env = dict(os.environ)
    if ssh_key:
        known_hosts = Path(ssh_key).parent / "known_hosts"
        env["GIT_SSH_COMMAND"] = (f"ssh -i {ssh_key} -o IdentitiesOnly=yes -o UserKnownHostsFile={known_hosts} "
                                  "-o StrictHostKeyChecking=accept-new")
    return env


def _force_writable(func, path, _):
    os.chmod(path, stat.S_IWRITE)  # git objects are read-only, which blocks deleting on Windows
    func(path)


def publish(work_dir, remote, public, private_blob, ssh_key=None):
    work = Path(work_dir)
    if work.exists():
        shutil.rmtree(work, onerror=_force_writable)  # a fresh single commit each time: nothing grows
    work.mkdir(parents=True)
    (work / "public.json").write_text(json.dumps(public, ensure_ascii=False), encoding="utf-8")
    (work / "private.enc").write_text(json.dumps(private_blob), encoding="utf-8")
    env = git_env(ssh_key)

    def git(*args):
        subprocess.run(["git", "-C", str(work), *args], check=True, env=env,
                       capture_output=True, text=True, timeout=60)

    git("init", "-q", "-b", "data")
    git("add", "-A")
    git("-c", "user.name=vtb-monitor", "-c", "user.email=vtb-monitor@localhost", "commit", "-q", "-m", "data")
    git("push", "-q", "-f", remote, "data")
