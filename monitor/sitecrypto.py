"""Encryption of the site's private part: the agents-site scheme, so the same password works.

PBKDF2-SHA256 → AES-GCM-256, published as {v, iter, salt, iv, ct} in base64 (ct includes the tag).
The VPS only holds the derived key (SITE_KEY) and its salt, never the password.
"""
import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITERATIONS = 600_000


def _b64(raw):
    return base64.b64encode(raw).decode()


def derive_key(password, salt, iterations=ITERATIONS):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations, 32)


def encrypt_json(payload, key, salt, iterations=ITERATIONS):
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, json.dumps(payload, ensure_ascii=False).encode(), None)
    return {"v": 1, "iter": iterations, "salt": _b64(salt), "iv": _b64(iv), "ct": _b64(ct)}


def decrypt_json(blob, password):
    key = derive_key(password, base64.b64decode(blob["salt"]), blob["iter"])
    plain = AESGCM(key).decrypt(base64.b64decode(blob["iv"]), base64.b64decode(blob["ct"]), None)
    return json.loads(plain)
