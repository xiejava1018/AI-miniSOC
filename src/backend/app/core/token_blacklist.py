"""
Token Blacklist Module
Provides in-memory token revocation status checks.
In a production environment, this should be replaced with Redis.
"""

import time
from typing import Dict

# In-memory blacklist: {jti: exp_timestamp}
_blacklist: Dict[str, float] = {}


def revoke(jti: str, exp_ts: float) -> None:
    """
    Revoke a token by adding its JTI to the blacklist with its expiration timestamp.

    Args:
        jti: The unique token identifier.
        exp_ts: Unix timestamp when the token expires.
    """
    if jti:
        _blacklist[jti] = exp_ts
        purge_expired()


def is_revoked(jti: str) -> bool:
    """
    Check if a JTI is present in the blacklist and not yet expired.

    Args:
        jti: The unique token identifier.

    Returns:
        bool: True if revoked, False otherwise.
    """
    if not jti:
        return False

    exp_ts = _blacklist.get(jti)
    if exp_ts is None:
        return False

    # If the token has naturally expired, remove it from blacklist and return False
    if time.time() > exp_ts:
        _blacklist.pop(jti, None)
        return False

    return True


def purge_expired() -> None:
    """
    Remove expired JTIs from the blacklist to release memory.
    """
    now = time.time()
    expired_keys = [k for k, exp in _blacklist.items() if now > exp]
    for k in expired_keys:
        _blacklist.pop(k, None)
