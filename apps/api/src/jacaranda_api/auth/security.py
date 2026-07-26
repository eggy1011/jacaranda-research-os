from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from pwdlib import PasswordHash

SESSION_COOKIE = "jacaranda_session"
SESSION_TTL = timedelta(days=14)

# member < reviewer < admin; higher roles inherit lower permissions.
ROLE_ORDER = {"member": 0, "reviewer": 1, "admin": 2}

_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


def new_invite_code() -> str:
    return secrets.token_urlsafe(12)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def digest(value: str) -> str:
    """Codes and session tokens are stored only as sha256 digests."""
    return hashlib.sha256(value.encode()).hexdigest()


def role_allows(role: str, required: str) -> bool:
    return ROLE_ORDER.get(role, -1) >= ROLE_ORDER.get(required, 99)
