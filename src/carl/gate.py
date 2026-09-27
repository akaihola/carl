"""Access passes (First working Carl spec, section 2, Access passes).

The whole site is behind an access pass, except the health endpoint and the
loading page. Each pass is a scrypt entry `salt:hash` in the comma-separated
`CARL_PASSWORDS` secret variable, made by `carl hash-password`. A correct
pass sets a stateless cookie, HMAC(TOKEN_SECRET, salt of the entry), so
deleting an entry revokes that pass's cookies and rotating TOKEN_SECRET
revokes them all. A wrong pass is answered after a 1 s wait, with no lockout:
brute force meets the passphrase's ~72 bits instead.

Taken from akaihola/drum-transcribe's gate.py.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from collections.abc import Mapping

SCRYPT = {"n": 2**14, "r": 8, "p": 1}
COOKIE = "carl_pass"
COOKIE_MAX_AGE_S = 365 * 24 * 3600
WRONG_PASS_WAIT_S = 1.0
MIN_PASS_LENGTH = 12
MIN_TOKEN_SECRET_LENGTH = 32
# The four-word passphrase: each word three syllables from 13 × 5 = 65, so
# 65 ** 12 ≈ 2 ** 72.
SYLLABLES = [c + v for c in "bdfgklmnprstv" for v in "aeiou"]
ENTRY = re.compile(r"[0-9a-f]{16}:[0-9a-f]{128}")


class GateError(Exception):
    pass


def hash_password(password: str, salt: str | None = None) -> str:
    """A CARL_PASSWORDS entry for `password`: `salt:hash`."""
    salt = salt or secrets.token_hex(8)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), **SCRYPT)
    return f"{salt}:{digest.hex()}"


def generate_passphrase() -> str:
    return "-".join("".join(secrets.choice(SYLLABLES) for _ in range(3)) for _ in range(4))


class Passes:
    def __init__(self, entries: str, token_secret: str):
        self._entries = [e.strip() for e in entries.split(",") if e.strip()]
        if not self._entries:
            raise GateError("CARL_PASSWORDS holds no access pass")
        for entry in self._entries:
            if not ENTRY.fullmatch(entry):
                raise GateError("CARL_PASSWORDS: an entry isn't `salt:hash` from `carl hash-password`")
        if len(token_secret) < MIN_TOKEN_SECRET_LENGTH:
            raise GateError(f"TOKEN_SECRET must be at least {MIN_TOKEN_SECRET_LENGTH} characters")
        self._secret = token_secret.encode()
        self._tokens = [self.token(entry.split(":")[0]) for entry in self._entries]

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> Passes:
        missing = [name for name in ("CARL_PASSWORDS", "TOKEN_SECRET") if not environ.get(name)]
        if missing:
            raise GateError(f"{' and '.join(missing)} not set: Carl never runs without its access passes")
        return cls(environ["CARL_PASSWORDS"], environ["TOKEN_SECRET"])

    def check(self, password: str) -> str | None:
        """The salt of the entry `password` matches, or None.

        Slow on purpose (scrypt): call it off the event loop.
        """
        for entry in self._entries:
            salt = entry.split(":")[0]
            if hmac.compare_digest(hash_password(password, salt), entry):
                return salt
        return None

    def token(self, salt: str) -> str:
        return hmac.new(self._secret, salt.encode(), hashlib.sha256).hexdigest()

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        # Check every entry, so the time taken doesn't tell which one matched.
        return sum(hmac.compare_digest(token, t) for t in self._tokens) > 0
