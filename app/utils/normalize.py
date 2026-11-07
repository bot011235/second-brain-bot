from __future__ import annotations

import re
import unicodedata

_NON_ALNUM_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")
_LEADING_ARTICLES_RE = re.compile(r"^(the|a|an)\s+", flags=re.IGNORECASE)


def normalize_text(value: str | None, strip_articles: bool = True) -> str:
    """Нормализует название/автора: NFC, casefold, ё->е, без пунктуации и лишних пробелов."""
    if not value:
        return ""
    text = unicodedata.normalize("NFC", value).casefold()
    text = text.replace("ё", "е")
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if strip_articles:
        text = _LEADING_ARTICLES_RE.sub("", text).strip()
    return text
