"""Checks for user-written text that other people read: names, feed lines and the digest email.

Control characters (``Cc``) can break out of an email header or fake a line of the digest, and
format characters (``Cf``) such as right-to-left overrides can make one name look like another.
Both are rejected, as are the Unicode line and paragraph separators.
"""

import unicodedata

INVALID_CHARACTERS_MESSAGE = "{label} contains invalid characters"

# The zero-width joiner holds emoji sequences such as 👩‍🌾 together.
_ALLOWED_FORMAT_CHARACTERS = frozenset("‍")
_MULTILINE_CONTROL_CHARACTERS = frozenset("\n\t")
_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


def has_invalid_characters(value: str, *, multiline: bool = False) -> bool:
    """Whether ``value`` holds a control, format or separator character. ``multiline`` allows newline and tab."""
    for char in value:
        if char in _ALLOWED_FORMAT_CHARACTERS or (multiline and char in _MULTILINE_CONTROL_CHARACTERS):
            continue
        if unicodedata.category(char) in _FORBIDDEN_CATEGORIES:
            return True
    return False


def normalise_newlines(value: str) -> str:
    """``\\r\\n`` and lone ``\\r`` become ``\\n``."""
    return value.replace("\r\n", "\n").replace("\r", "\n")
