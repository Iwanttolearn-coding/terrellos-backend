"""
bible_source.py — Real, legal Bible text retrieval.

Uses the free, public, no-auth CDN mirror at wldeh/bible-api (served via jsdelivr)
as the FIRST legal Bible source for verse/chapter text.

We only expose public-domain-safe versions by default (en-kjv, en-asv) so the app
never generates or hardcodes copyrighted translation text (NIV, ESV, NLT, NASB,
MSG, AMP, TPT, CSB, etc.). Those commercial translations require licensing and are
intentionally NOT sourced or faked here.
"""
import httpx
import logging
import re
from typing import Optional

logger = logging.getLogger("bible_source")

# KJV/ASV source data embeds translator footnotes and paragraph markers directly
# in the verse text (e.g. "...still waters.23.2 still...: Heb. waters of quietness",
# or a leading "¶" paragraph mark). Strip these so only the real verse text is shown.
_FOOTNOTE_RE = re.compile(r'\d+\.\d+\s.*?:\s*Heb\.[^\d]*')
_PILCROW_RE  = re.compile(r'¶\s*')


def clean_verse_text(text: str) -> str:
    if not text:
        return text
    text = _FOOTNOTE_RE.sub('', text)
    text = _PILCROW_RE.sub('', text)
    return text.strip()

CDN_BASE = "https://cdn.jsdelivr.net/gh/wldeh/bible-api/bibles"

# Versions we allow end-users to select today. Both are public domain — safe to
# display verbatim. To add a version, confirm its `copyright` field from
# /bibles.json reads "PUBLIC DOMAIN" (or equivalent explicit permission) first.
ALLOWED_VERSIONS = {
    "en-kjv": "King James Version (1769, public domain)",
    "en-asv": "American Standard Version (1901, public domain)",
}


class BibleSourceError(Exception):
    """Raised for any Bible-source lookup failure. `.kind` lets callers map to a clean user message."""
    def __init__(self, kind: str, message: str):
        self.kind = kind  # invalid_version | invalid_book | invalid_chapter | invalid_verse | network_error
        self.message = message
        super().__init__(message)


def normalize_book(book: str) -> str:
    """Bible-api book slugs are just the book name, lowercased, with all spaces/punctuation
    stripped — e.g. '1 Corinthians' -> '1corinthians', 'Song of Solomon' -> 'songofsolomon'."""
    return "".join(ch for ch in (book or "").lower() if ch.isalnum())


def _check_version(version: str):
    if version not in ALLOWED_VERSIONS:
        raise BibleSourceError(
            "invalid_version",
            f"'{version}' is not a supported Bible version. Supported versions: {', '.join(ALLOWED_VERSIONS)}."
        )


async def get_bible_versions() -> list:
    """Return the list of versions this app currently supports (public-domain-safe only)."""
    return [{"id": k, "name": v} for k, v in ALLOWED_VERSIONS.items()]


async def get_verse(version: str, book: str, chapter: int, verse: int) -> dict:
    _check_version(version)
    slug = normalize_book(book)
    url = f"{CDN_BASE}/{version}/books/{slug}/chapters/{chapter}/verses/{verse}.json"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url)
    except Exception as e:
        raise BibleSourceError("network_error", f"Could not reach the Bible text source: {e}")

    if r.status_code == 404:
        raise BibleSourceError(
            "invalid_verse",
            f"Couldn't find {book} {chapter}:{verse} in {version}. Check the book name, chapter, and verse number."
        )
    if r.status_code != 200:
        raise BibleSourceError("network_error", f"Bible text source returned an unexpected error ({r.status_code}).")

    data = r.json()
    return {
        "version": version,
        "book": book,
        "chapter": chapter,
        "verse": verse,
        "text": clean_verse_text(data.get("text", "")),
        "reference": f"{book} {chapter}:{verse}",
    }


async def get_chapter(version: str, book: str, chapter: int) -> dict:
    _check_version(version)
    slug = normalize_book(book)
    url = f"{CDN_BASE}/{version}/books/{slug}/chapters/{chapter}.json"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url)
    except Exception as e:
        raise BibleSourceError("network_error", f"Could not reach the Bible text source: {e}")

    if r.status_code == 404:
        # Distinguish invalid book vs invalid chapter with one extra check on chapter 1
        if chapter != 1:
            try:
                async with httpx.AsyncClient(timeout=10) as c2:
                    r2 = await c2.get(f"{CDN_BASE}/{version}/books/{slug}/chapters/1.json")
                if r2.status_code == 200:
                    raise BibleSourceError("invalid_chapter", f"{book} doesn't have a chapter {chapter}.")
            except BibleSourceError:
                raise
            except Exception:
                pass
        raise BibleSourceError("invalid_book", f"Couldn't find the book '{book}'. Check the spelling.")
    if r.status_code != 200:
        raise BibleSourceError("network_error", f"Bible text source returned an unexpected error ({r.status_code}).")

    payload = r.json()
    verses = payload.get("data", [])
    cleaned = [{"verse": v.get("verse"), "text": clean_verse_text(v.get("text", ""))} for v in verses]
    full_text = "\n".join(f"{v['verse']}. {v['text']}" for v in cleaned)
    return {
        "version": version,
        "book": book,
        "chapter": chapter,
        "verses": cleaned,
        "full_text": full_text,
        "reference": f"{book} {chapter}",
    }
