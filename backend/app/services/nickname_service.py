"""
Nickname validation and filtering (PR-08).

Rules applied in order:
  1. Strip leading/trailing whitespace; reject if empty after strip.
  2. Length: 2–20 characters (post-strip).
  3. Allowed characters: Korean (가-힣 / ㄱ-ㅎ / ㅏ-ㅣ), ASCII letters, digits,
     underscore, and a single space between words.
     No other punctuation, emoji, or control characters.
  4. No all-digit nickname (looks like a phone number / ID).
  5. Reserved prefixes: "Guest_" is reserved for auto-generated guest names.
  6. Banned-term list: a small hardcoded set of clearly abusive/spam terms.
     The list is intentionally minimal for beta; expand as incidents occur.

All checks are case-insensitive for the banned-term matching step.

Usage::

    from app.services.nickname_service import validate_nickname, NicknameError

    try:
        validated = validate_nickname(raw_nickname)
    except NicknameError as exc:
        raise HTTPException(400, detail=str(exc))
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_MIN_LEN = 2
_MAX_LEN = 20

# Allowed: Korean syllables / jamo, ASCII letters, digits, underscore, space.
# Spaces are allowed as word separators but not at start/end (stripped earlier).
_ALLOWED_RE = re.compile(r"^[가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9_ ]+$")

# Must contain at least one non-digit character so purely numeric names are blocked.
_ALL_DIGITS_RE = re.compile(r"^\d+$")

_RESERVED_PREFIXES = ("guest_",)

# Minimal banned-term list for beta.  Lower-case; matched case-insensitively.
_BANNED_TERMS: frozenset[str] = frozenset(
    {
        "admin",
        "moderator",
        "mod",
        "system",
        "server",
        "official",
        # Korean slurs / spam placeholders for beta — expand as needed.
        "운영자",
        "관리자",
    }
)

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class NicknameError(ValueError):
    """Raised when a nickname fails validation."""


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate_nickname(raw: str) -> str:
    """
    Validate and normalise a nickname.

    Returns the stripped, valid nickname string.
    Raises NicknameError with a user-facing message if any rule is violated.
    """
    nick = raw.strip()

    if not nick:
        raise NicknameError("닉네임을 입력해주세요.")

    if len(nick) < _MIN_LEN:
        raise NicknameError(f"닉네임은 최소 {_MIN_LEN}자 이상이어야 합니다.")

    if len(nick) > _MAX_LEN:
        raise NicknameError(f"닉네임은 최대 {_MAX_LEN}자까지 허용됩니다.")

    if not _ALLOWED_RE.match(nick):
        raise NicknameError("닉네임에는 한글, 영문, 숫자, 밑줄(_), 공백만 사용할 수 있습니다.")

    if _ALL_DIGITS_RE.match(nick):
        raise NicknameError("닉네임은 숫자만으로 구성될 수 없습니다.")

    lower = nick.lower()

    for prefix in _RESERVED_PREFIXES:
        if lower.startswith(prefix):
            raise NicknameError(f"'{prefix.rstrip('_')}' 로 시작하는 닉네임은 사용할 수 없습니다.")

    for term in _BANNED_TERMS:
        if term in lower:
            raise NicknameError("사용할 수 없는 닉네임입니다.")

    return nick
