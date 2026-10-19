"""Password hashing with scrypt from the standard library (D1: no bcrypt or argon2).

Stored as `scrypt$n$r$p$salt$hash`, so the cost can be raised later without
breaking the hashes already stored.

Owner: B
"""

import base64
import binascii
import hashlib
import hmac
import secrets
from functools import lru_cache

MIN_LENGTH = 12
_N, _R, _P = 2**14, 8, 1  # 16MB and about 50ms per hash


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, _N, _R, _P, 32)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison. A malformed hash is a mismatch, never an exception."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest, validate=True)
        actual = _scrypt(
            password, base64.b64decode(salt, validate=True), int(n), int(r), int(p), len(expected)
        )
    except (ValueError, binascii.Error):
        return False
    return hmac.compare_digest(actual, expected)


@lru_cache
def dummy_hash() -> str:
    """Checked when the username doesn't exist, so the answer takes as long either way."""
    return hash_password(secrets.token_hex(16))


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, dklen=length, maxmem=64 * 1024 * 1024
    )


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()
