import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from monitor import sitecrypto

SALT = b"0" * 16
FIXTURE = Path(__file__).parent.parent / "site" / "src" / "__fixtures__" / "enc.json"


def test_round_trip():
    key = sitecrypto.derive_key("пароль", SALT, 1000)
    blob = sitecrypto.encrypt_json({"hello": "мир"}, key, SALT, 1000)
    assert set(blob) == {"v", "iter", "salt", "iv", "ct"} and blob["iter"] == 1000
    assert sitecrypto.decrypt_json(blob, "пароль") == {"hello": "мир"}


def test_wrong_password_fails():
    blob = sitecrypto.encrypt_json({"a": 1}, sitecrypto.derive_key("right", SALT, 1000), SALT, 1000)
    with pytest.raises(InvalidTag):
        sitecrypto.decrypt_json(blob, "wrong")


def test_each_encryption_uses_a_fresh_iv():
    key = sitecrypto.derive_key("p", SALT, 1000)
    assert sitecrypto.encrypt_json({}, key, SALT, 1000)["iv"] != sitecrypto.encrypt_json({}, key, SALT, 1000)["iv"]


def test_browser_fixture_matches():
    """site/src/__fixtures__/enc.json is decrypted by the browser test with password «test»."""
    assert sitecrypto.decrypt_json(json.loads(FIXTURE.read_text(encoding="utf-8")), "test") == {"hello": "мир"}
