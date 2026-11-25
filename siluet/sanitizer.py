from __future__ import annotations

import re

from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE


ESCAPED_BREAKS_RE = re.compile(r"(?i)_x000[ad]_|&#(?:10|13);|&#x(?:a|d);")
MULTI_BREAK_RE = re.compile(r"\n{3,}")
HORIZONTAL_SPACE_RE = re.compile(r"[^\S\n]+")


def sanitize_text(value: str) -> str:
    text = ESCAPED_BREAKS_RE.sub("\n", value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = ILLEGAL_CHARACTERS_RE.sub("", text)
    lines = [HORIZONTAL_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    return MULTI_BREAK_RE.sub("\n\n", "\n".join(lines)).strip()


def has_unsafe_text(value: str) -> bool:
    return bool(ESCAPED_BREAKS_RE.search(value) or ILLEGAL_CHARACTERS_RE.search(value) or "\r" in value)

