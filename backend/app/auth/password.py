"""
Password hashing and verification using bcrypt.

Uses the bcrypt library directly (no passlib wrapper) to avoid the
bcrypt 4.x / passlib compatibility issue present in Python 3.12.
"""

import bcrypt


def hash_password(plain: str) -> str:
    """Hash a plain-text password. Returns a UTF-8 bcrypt hash string."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False
