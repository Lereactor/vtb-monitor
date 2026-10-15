"""Derive the site key from the site password, once, on the owner's PC.

    python scripts/derive_site_key.py | ssh root@vps 'cat >> /etc/vtb-monitor.env'

Prints SITE_KEY / SITE_SALT / SITE_ITER lines. The password is read without echo and never
printed or stored; the key cannot open the agents site (its salt differs).
"""
import base64
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from monitor.sitecrypto import ITERATIONS, derive_key  # noqa: E402

password = getpass.getpass("Пароль сайта (как у сайта агентов): ")
if not password:
    sys.exit("Пустой пароль")
salt = os.urandom(16)
print(f"SITE_KEY={base64.b64encode(derive_key(password, salt)).decode()}")
print(f"SITE_SALT={base64.b64encode(salt).decode()}")
print(f"SITE_ITER={ITERATIONS}")
