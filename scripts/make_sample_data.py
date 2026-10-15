"""Sample site data for `npm run dev`, from a copy of the VPS history (password «test»).

    scp root@vps:/var/lib/vtb-monitor/history.db root@vps:/var/lib/vtb-monitor/state.json <dir>
    python scripts/make_sample_data.py --db <dir>/history.db --state <dir>/state.json

Writes site/public/sample/public.json and private.enc (git-ignored).
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from monitor import export, history, sitecrypto  # noqa: E402
from monitor import state as st  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "site" / "public" / "sample"

parser = argparse.ArgumentParser()
parser.add_argument("--db", required=True)
parser.add_argument("--state", required=True)
args = parser.parse_args()

public, private = export.build(history.connect(args.db), st.load_state(args.state), datetime.now(timezone.utc))
salt = os.urandom(16)
blob = sitecrypto.encrypt_json(private, sitecrypto.derive_key("test", salt, 1000), salt, 1000)  # fast for dev
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "public.json").write_text(json.dumps(public, ensure_ascii=False), encoding="utf-8")
(OUT / "private.enc").write_text(json.dumps(blob), encoding="utf-8")
print(f"written to {OUT}")
