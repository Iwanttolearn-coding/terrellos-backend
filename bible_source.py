"""
bible_source.py — Real, legal Bible text retrieval.

Uses the free, public, no-auth CDN mirror at wldeh/bible-api (served via jsdelivr)
as the FIRST legal Bible source for verse/chapter text.

We only expose versions confirmed PUBLIC DOMAIN in /bibles.json (or unambiguously
public domain by age — pre-1923 translations) AND confirmed clean of embedded
footnote/cross-reference text that could corrupt the real scripture text on
display. The app never generates or hardcodes copyrighted translation text
(NIV, ESV, NLT, NASB, MSG, AMP, TPT, CSB, etc.) — those require licensing and are
intentionally NOT sourced or faked here.

PRODUCTION SWEEP NOTE (2026-07-06): the source CDN embeds footnotes/cross-refs
directly inline in verse text for some versions, with no separating field. For
en-kjv/en-asv this is safely stripped by a targeted regex (see clean_verse_text).
Several other candidate versions (World English Bible family, Berean Study
Bible, the RV09 Spanish text) were tested and found to have UNRELIABLE footnote
boundaries — in specific verses the footnote has no punctuation separating it
from the next real word, so a blunt strip would delete real scripture text
(confirmed destructive on en-web John 1:23 and en-bsb Genesis 1:3). Those are
intentionally NOT added below until a safer per-version parser exists. See
DEFERRED_VERSIONS for the list and reasons.
"""
import httpx
import logging
import re
from typing import Optional

logger = logging.getLogger("bible_source")

# KJV/ASV-style source data embeds translator footnotes and paragraph markers
# directly in the verse text (e.g. "...still waters.23.2 still...: Heb. waters
# of quietness", or a leading "¶" paragraph mark). Strip these so only the real
# verse text is shown. Verified safe (no destructive edge cases found) across
# en-kjv, en-asv, en-gnv, en-us-kjvcpb, en-dra, en-ojps, en-oke.
_FOOTNOTE_RE = re.compile(r'\d+\.\d+\s.*?:\s*Heb\.[^\d]*')
_PILCROW_RE  = re.compile(r'¶\s*')


def clean_verse_text(text: str) -> str:
    if not text:
        return text
    text = _FOOTNOTE_RE.sub('', text)
    text = _PILCROW_RE.sub('', text)
    return text.strip()


CDN_BASE = "https://cdn.jsdelivr.net/gh/wldeh/bible-api/bibles"

# Versions we allow end-users to select today. Every one of these was verified:
# (1) copyright field is "PUBLIC DOMAIN" or the translation is unambiguously
#     public domain by age (pre-1923), AND
# (2) sample chapters (Genesis 1, John 1/3, Psalms 23 where in scope) came back
#     with NO embedded footnote/cross-reference text corrupting the verse.
ALLOWED_VERSIONS = {
    "en-kjv":       "King James Version (1769, public domain)",
    "en-asv":       "American Standard Version (1901, public domain)",
    "en-gnv":       "Geneva Bible (1599, public domain)",
    "en-us-kjvcpb": "Cambridge Paragraph Bible — KJV, modern punctuation (public domain)",
    "en-dra":       "Douay-Rheims American Edition (1899, public domain, Catholic tradition)",
    "en-rv":        "Revised Version (1885, public domain)",
    "en-ojps":      "Old JPS TaNaKH (1917, public domain, Jewish translation — Old Testament only)",
    "en-oke":       "Targum Onkelos, Etheridge translation (public domain — Torah/Genesis-Deuteronomy only)",
}

# Real CDN bible id casing/values differ slightly from our public ids in one case
# (jsdelivr path is case-sensitive: "en-US-kjvcpb"). Map our clean id -> real path id.
_CDN_VERSION_ID = {
    "en-us-kjvcpb": "en-US-kjvcpb",
}

# Versions intentionally NOT enabled yet, and why — kept here so this isn't
# silently forgotten and someone re-discovers the same footnote bugs later.
DEFERRED_VERSIONS = {
    "en-web / en-webus / en-webbe": "World English Bible family — public domain, but footnotes are spliced "
        "inline with no reliable terminator in some verses (confirmed destructive strip risk on John 1:23, "
        "a bare 'Isaiah 40:3' citation footnote with no trailing period before real text resumes).",
    "en-bsb": "Berean Study Bible — public domain, but same inline-footnote issue, confirmed destructive on "
        "Genesis 1:3 ('1:3 Cited in 2 Corinthians 4:6 and there was light.' — no terminator before real text).",
    "en-engbrent / en-US-lxxup": "Brenton Septuagint family — public domain, but footnote splicing duplicates "
        "real words in some verses (Genesis 1:4), unsafe to auto-strip without a smarter parser.",
    "es-rv09": "Reina Valera 1909 (Spanish) — public domain, but cross-reference footnotes are glued to real "
        "text inconsistently (sometimes no space, sometimes a space, sometimes before a capital letter) — no "
        "single regex boundary works safely across all cases without risking dropped real words.",
    "en-wmb / en-wmbbe": "World Messianic Bible — public domain, but uses Hebraic book-name slugs (e.g. "
        "'yochanan' for John, 'jacob' for James, 'judah' for Jude) requiring a full custom book-name map "
        "before it can be wired in safely.",
}

# Per-version book-slug overrides, only where a version's real folder name differs
# from our generic normalize_book() output. Keyed by our public version id.
_BOOK_SLUG_OVERRIDES = {
    "en-rv": {
        "songofsolomon": "songofsongs",
    },
}

# Scope notes surfaced to the frontend so the UI can explain why e.g. Matthew
# isn't available in the Old JPS TaNaKH or Targum Onkelos.
VERSION_SCOPE = {
    "en-ojps": "Old Testament only",
    "en-oke":  "Torah only (Genesis–Deuteronomy)",
}


class BibleSourceError(Exception):
    """Raised for any Bible-source lookup failure. `.kind` lets callers map to a clean user message."""
    def __init__(self, kind: str, message: str):
        self.kind = kind  # invalid_version | invalid_book | invalid_chapter | invalid_verse | network_error
        self.message = message
        super().__init__(message)


def normalize_book(book: str, version: str = "") -> str:
    """Bible-api book slugs are just the book name, lowercased, with all spaces/punctuation
    stripped — e.g. '1 Corinthians' -> '1corinthians', 'Song of Solomon' -> 'songofsolomon' —
    except for the per-version overrides above."""
    slug = "".join(ch for ch in (book or "").lower() if ch.isalnum())
    overrides = _BOOK_SLUG_OVERRIDES.get(version, {})
    return overrides.get(slug, slug)


def _cdn_version_id(version: str) -> str:
    return _CDN_VERSION_ID.get(version, version)


def _check_version(version: str):
    if version not in ALLOWED_VERSIONS:
        raise BibleSourceError(
            "invalid_version",
            f"'{version}' is not a supported Bible version. Supported versions: {', '.join(ALLOWED_VERSIONS)}."
        )


async def get_bible_versions() -> list:
    """Return the list of versions this app currently supports (public-domain-safe,
    footnote-clean only)."""
    return [
        {"id": k, "name": v, "scope": VERSION_SCOPE.get(k, "Full Bible")}
        for k, v in ALLOWED_VERSIONS.items()
    ]


async def get_verse(version: str, book: str, chapter: int, verse: int) -> dict:
    _check_version(version)
    slug = normalize_book(book, version)
    cdn_id = _cdn_version_id(version)
    url = f"{CDN_BASE}/{cdn_id}/books/{slug}/chapters/{chapter}/verses/{verse}.json"
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
    slug = normalize_book(book, version)
    cdn_id = _cdn_version_id(version)
    url = f"{CDN_BASE}/{cdn_id}/books/{slug}/chapters/{chapter}.json"
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
                    r2 = await c2.get(f"{CDN_BASE}/{cdn_id}/books/{slug}/chapters/1.json")
                if r2.status_code == 200:
                    raise BibleSourceError("invalid_chapter", f"{book} doesn't have a chapter {chapter}.")
            except BibleSourceError:
                raise
            except Exception:
                pass
        scope_note = VERSION_SCOPE.get(version)
        extra = f" Note: {ALLOWED_VERSIONS.get(version, version)} only covers {scope_note}." if scope_note else ""
        raise BibleSourceError("invalid_book", f"Couldn't find the book '{book}'.{extra}")
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
