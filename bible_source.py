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
from urllib.parse import quote as _urlquote
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
    # Sourced from bible-api.com's parameterized data API (clean, footnote-free —
    # see BIBLE_API_COM_VERSIONS below) rather than the wldeh CDN, which embeds
    # unreliable inline footnotes for these specific versions.
    "en-web":       "World English Bible (public domain)",
    "en-webbe":     "World English Bible, British Edition (public domain)",
    "en-bbe":       "Bible in Basic English (1949, public domain)",
    "en-darby":     "Darby Bible (1890, public domain)",
    "en-ylt":       "Young's Literal Translation (1898, public domain — New Testament only)",
    # Spanish — verified clean (2026-07-08): no footnote-splicing across Genesis,
    # John, Ephesians, Romans, Hebrews, Revelation, Psalms. Same eBible.org public
    # domain archive (archivist Kahunapule Michael Johnson) as several of our
    # already-approved English versions above. Used for the English/Spanish
    # parallel reading view, always paired with en-kjv (never a stand-alone
    # substitute for an AI translation of KJV).
    "es-bes":       "La Biblia en Español Sencillo (public domain, Spanish)",
}

# Real CDN bible id casing/values differ slightly from our public ids in one case
# (jsdelivr path is case-sensitive: "en-US-kjvcpb"). Map our clean id -> real path id.
_CDN_VERSION_ID = {
    "en-us-kjvcpb": "en-US-kjvcpb",
}

# Versions intentionally NOT enabled yet, and why — kept here so this isn't
# silently forgotten and someone re-discovers the same footnote bugs later.
DEFERRED_VERSIONS = {
    # en-web/en-webbe RESOLVED 2026-07-07: no longer sourced from the wldeh CDN
    # (which has the footnote-splicing bug described below) -- now sourced from
    # bible-api.com's parameterized data API instead, which returns genuinely
    # clean, footnote-free text for these translations. See BIBLE_API_COM_VERSIONS.
    "en-bsb": "Berean Study Bible — public domain, but same inline-footnote issue as the old wldeh en-web "
        "problem, confirmed destructive on Genesis 1:3 ('1:3 Cited in 2 Corinthians 4:6 and there was light.' "
        "— no terminator before real text). Not available on bible-api.com either, so still deferred; would "
        "need its own clean source before enabling.",
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
    "en-ylt":  "New Testament only",
}

# es-bes book folders are named in Spanish, not English — full map required
# (normalize_book() only handles English book names). Keyed by the same
# normalized English slug normalize_book() produces (lowercase, no punctuation).
ES_BES_BOOK_SLUGS = {
    "genesis": "génesis", "exodus": "éxodo", "leviticus": "levítico",
    "numbers": "números", "deuteronomy": "deuteronomio", "joshua": "josué",
    "judges": "jueces", "ruth": "rut", "1samuel": "1samuel", "2samuel": "2samuel",
    "1kings": "1reyes", "2kings": "2reyes", "1chronicles": "1crónicas",
    "2chronicles": "2crónicas", "ezra": "esdras", "nehemiah": "nehemías",
    "esther": "ester", "job": "job", "psalms": "salmos", "psalm": "salmos",
    "proverbs": "proverbios", "ecclesiastes": "eclesiastés",
    "songofsolomon": "cantares", "songofsongs": "cantares", "isaiah": "isaías",
    "jeremiah": "jeremías", "lamentations": "lamentaciones", "ezekiel": "ezequiel",
    "daniel": "daniel", "hosea": "oseas", "joel": "joel", "amos": "amós",
    "obadiah": "abdías", "jonah": "jonás", "micah": "miqueas", "nahum": "nahum",
    "habakkuk": "habacuc", "zephaniah": "sofonías", "haggai": "hageo",
    "zechariah": "zacarías", "malachi": "malaquías", "matthew": "mateo",
    "mark": "marcos", "luke": "lucas", "john": "juan", "acts": "hechos",
    "romans": "romanos", "1corinthians": "1corintios", "2corinthians": "2corintios",
    "galatians": "gálatas", "ephesians": "efesios", "philippians": "filipenses",
    "colossians": "colosenses", "1thessalonians": "1tesalonicenses",
    "2thessalonians": "2tesalonicenses", "1timothy": "1timoteo",
    "2timothy": "2timoteo", "titus": "tito", "philemon": "filemón",
    "hebrews": "hebreos", "james": "santiago", "1peter": "1pedro",
    "2peter": "2pedro", "1john": "1juan", "2john": "2juan", "3john": "3juan",
    "jude": "judas", "revelation": "apocalipsis", "revelations": "apocalipsis",
}


# ══════════════════════════════════════════════════════════════════════════════
# Secondary source: bible-api.com's parameterized data API. Used ONLY for the
# specific versions below, where the primary wldeh CDN mirror embeds inline
# footnotes with no reliable terminator (confirmed destructive strip risk —
# see DEFERRED_VERSIONS history). bible-api.com's /data/{translation}/{BOOK}/{n}
# endpoint returns genuinely clean, footnote-free verse text for these same
# public-domain translations, sourced from the open-bibles project.
# Rate-limited to 15 req/30s per their terms — we cache full chapters
# in-memory indefinitely (Bible text never changes) so repeat reads never
# re-hit the network.
# ══════════════════════════════════════════════════════════════════════════════
BIBLE_API_COM_BASE = "https://bible-api.com/data"

BIBLE_API_COM_VERSIONS = {"en-web", "en-webbe", "en-bbe", "en-darby", "en-ylt"}

_BIBLE_API_COM_ID = {
    "en-web": "web", "en-webbe": "webbe", "en-bbe": "bbe",
    "en-darby": "darby", "en-ylt": "ylt",
}

# Standard 66-book Protestant canon -> bible-api.com 3-letter book IDs.
_BOOK_ID_MAP = {
    "genesis": "GEN", "exodus": "EXO", "leviticus": "LEV", "numbers": "NUM",
    "deuteronomy": "DEU", "joshua": "JOS", "judges": "JDG", "ruth": "RUT",
    "1samuel": "1SA", "2samuel": "2SA", "1kings": "1KI", "2kings": "2KI",
    "1chronicles": "1CH", "2chronicles": "2CH", "ezra": "EZR", "nehemiah": "NEH",
    "esther": "EST", "job": "JOB", "psalms": "PSA", "psalm": "PSA",
    "proverbs": "PRO", "ecclesiastes": "ECC", "songofsolomon": "SNG",
    "songofsongs": "SNG", "isaiah": "ISA", "jeremiah": "JER",
    "lamentations": "LAM", "ezekiel": "EZK", "daniel": "DAN", "hosea": "HOS",
    "joel": "JOL", "amos": "AMO", "obadiah": "OBA", "jonah": "JON",
    "micah": "MIC", "nahum": "NAM", "habakkuk": "HAB", "zephaniah": "ZEP",
    "haggai": "HAG", "zechariah": "ZEC", "malachi": "MAL",
    "matthew": "MAT", "mark": "MRK", "luke": "LUK", "john": "JHN",
    "acts": "ACT", "romans": "ROM", "1corinthians": "1CO", "2corinthians": "2CO",
    "galatians": "GAL", "ephesians": "EPH", "philippians": "PHP",
    "colossians": "COL", "1thessalonians": "1TH", "2thessalonians": "2TH",
    "1timothy": "1TI", "2timothy": "2TI", "titus": "TIT", "philemon": "PHM",
    "hebrews": "HEB", "james": "JAS", "1peter": "1PE", "2peter": "2PE",
    "1john": "1JN", "2john": "2JN", "3john": "3JN", "jude": "JUD",
    "revelation": "REV", "revelations": "REV",
}

_bible_api_com_chapter_cache: dict = {}


async def _fetch_bible_api_com_chapter(version: str, book: str, chapter: int) -> dict:
    slug = normalize_book(book, version)
    book_id = _BOOK_ID_MAP.get(slug)
    if not book_id:
        raise BibleSourceError("invalid_book", f"Couldn't find the book '{book}'.")

    cache_key = (version, book_id, chapter)
    if cache_key in _bible_api_com_chapter_cache:
        return _bible_api_com_chapter_cache[cache_key]

    translation_id = _BIBLE_API_COM_ID[version]
    url = f"{BIBLE_API_COM_BASE}/{translation_id}/{book_id}/{chapter}"
    try:
        async with httpx.AsyncClient(timeout=15) as h:
            r = await h.get(url)
    except Exception as e:
        raise BibleSourceError("network_error", f"Could not reach the Bible text source: {e}")

    if r.status_code == 404:
        scope_note = VERSION_SCOPE.get(version)
        extra = f" Note: {ALLOWED_VERSIONS.get(version, version)} only covers {scope_note}." if scope_note else ""
        raise BibleSourceError("invalid_chapter", f"Couldn't find {book} {chapter}.{extra}")
    if r.status_code == 429:
        raise BibleSourceError("network_error", "Bible text source is temporarily rate-limited. Please try again in a moment.")
    if r.status_code != 200:
        raise BibleSourceError("network_error", f"Bible text source returned an unexpected error ({r.status_code}).")

    payload = r.json()
    verses = payload.get("verses", [])
    if not verses:
        scope_note = VERSION_SCOPE.get(version)
        extra = f" Note: {ALLOWED_VERSIONS.get(version, version)} only covers {scope_note}." if scope_note else ""
        raise BibleSourceError("invalid_chapter", f"Couldn't find {book} {chapter}.{extra}")

    cleaned = [{"verse": v.get("verse"), "text": (v.get("text") or "").strip()} for v in verses]
    full_text = "\n".join(f"{v['verse']}. {v['text']}" for v in cleaned)
    result = {
        "version": version, "book": book, "chapter": chapter,
        "verses": cleaned, "full_text": full_text,
        "reference": f"{book} {chapter}",
    }
    _bible_api_com_chapter_cache[cache_key] = result
    return result


async def _fetch_bible_api_com_verse(version: str, book: str, chapter: int, verse: int) -> dict:
    chapter_data = await _fetch_bible_api_com_chapter(version, book, chapter)
    match = next((v for v in chapter_data["verses"] if str(v["verse"]) == str(verse)), None)
    if not match:
        raise BibleSourceError(
            "invalid_verse",
            f"Couldn't find {book} {chapter}:{verse}. Check the book name, chapter, and verse number."
        )
    return {
        "version": version, "book": book, "chapter": chapter, "verse": verse,
        "text": match["text"], "reference": f"{book} {chapter}:{verse}",
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


def _cdn_book_path(book: str, version: str) -> str:
    """Return the URL-safe book path segment for a given version's CDN folder.
    es-bes uses full Spanish book names (with accents) instead of English slugs —
    everything else uses normalize_book() as before."""
    if version == "es-bes":
        eng_slug = "".join(ch for ch in (book or "").lower() if ch.isalnum())
        es_name = ES_BES_BOOK_SLUGS.get(eng_slug)
        if not es_name:
            raise BibleSourceError("invalid_book", f"Couldn't find the book '{book}' in the Spanish text.")
        return _urlquote(es_name)
    return normalize_book(book, version)


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
    if version in BIBLE_API_COM_VERSIONS:
        return await _fetch_bible_api_com_verse(version, book, chapter, verse)
    slug = _cdn_book_path(book, version)
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
    if version in BIBLE_API_COM_VERSIONS:
        return await _fetch_bible_api_com_chapter(version, book, chapter)
    slug = _cdn_book_path(book, version)
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


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCTION SWEEP ADDITION — shared reference resolver for OTHER generation
# endpoints (Bible Study Builder, Word Study passage mode) so they ground on
# the SAME real, verified public-domain text instead of asking the AI to
# recite scripture from memory under a copyrighted version label like "NIV".
# ══════════════════════════════════════════════════════════════════════════════
import re as _re

DEFAULT_VERSION = "en-kjv"

# Versions historically passed around the app as free-text defaults/labels that
# aren't real sourceable versions (NIV, ESV, etc. require licensing we don't have).
# Map them to our nearest real, public-domain equivalent rather than erroring —
# these callers pass a version as a hint/label, not a hard requirement.
_VERSION_ALIASES = {
    # Still-copyrighted translations we don't have a license for — these map to
    # our nearest real, public-domain equivalent rather than erroring. The
    # DISPLAY label the user picked is preserved separately (see routers/bible.py);
    # this alias only controls which real text is quoted.
    "niv": "en-kjv", "esv": "en-kjv", "nlt": "en-kjv", "nasb": "en-kjv",
    "msg": "en-kjv", "amp": "en-kjv", "tpt": "en-kjv", "csb": "en-kjv",
    "kjv": "en-kjv", "asv": "en-asv", "geneva": "en-gnv",
    # Genuinely public domain — resolve to the REAL thing, not a KJV substitute.
    "web": "en-web", "webbe": "en-webbe", "bbe": "en-bbe",
    "darby": "en-darby", "ylt": "en-ylt",
}

_REF_RE = _re.compile(
    r'^\s*(?P<book>(?:[1-3]\s?)?[A-Za-z][A-Za-z\s]*?)\s+(?P<chapter>\d+)'
    r'(?::(?P<vstart>\d+)(?:-(?P<vend>\d+))?)?\s*$'
)


def resolve_version(version: Optional[str]) -> str:
    """Map any incoming version hint (including copyrighted labels like 'NIV') to
    one of our real, sourced, public-domain versions. Never raises."""
    if not version:
        return DEFAULT_VERSION
    v = version.strip()
    if v in ALLOWED_VERSIONS:
        return v
    return _VERSION_ALIASES.get(v.lower(), DEFAULT_VERSION)


def parse_reference(ref: str):
    """Parse a free-text reference like 'John 3:16', 'John 3:16-21', or 'Romans 8'
    into {book, chapter, verse_start, verse_end}. Returns None if it doesn't look
    like a single, specific passage (e.g. a topic name like 'Faith' or 'Prayer')."""
    if not ref:
        return None
    m = _REF_RE.match(ref.strip())
    if not m:
        return None
    book = m.group("book").strip()
    if not book:
        return None
    return {
        "book": book,
        "chapter": int(m.group("chapter")),
        "verse_start": int(m.group("vstart")) if m.group("vstart") else None,
        "verse_end": int(m.group("vend")) if m.group("vend") else None,
    }


async def fetch_passage_text(version: str, ref: str) -> Optional[dict]:
    """Best-effort real-text fetch for a free-text reference from other generation
    endpoints (Bible Study Builder, Word Study). Returns {reference, text, version}
    or None if the ref doesn't parse or the lookup fails — callers should degrade
    gracefully (e.g. still generate a topical study) rather than error out, since
    this input is much less structured than the dedicated /v1/bible/* routes."""
    parsed = parse_reference(ref)
    if not parsed:
        return None
    v = resolve_version(version)
    try:
        if parsed["verse_start"] and not parsed["verse_end"]:
            data = await get_verse(v, parsed["book"], parsed["chapter"], parsed["verse_start"])
            return {"reference": data["reference"], "text": data["text"], "version": v}
        chapter_data = await get_chapter(v, parsed["book"], parsed["chapter"])
        verses = chapter_data["verses"]
        if parsed["verse_start"]:
            vs, ve = parsed["verse_start"], parsed["verse_end"] or parsed["verse_start"]
            verses = [x for x in verses if x["verse"] and vs <= int(x["verse"]) <= ve]
            if not verses:
                return None
            text = "\n".join(f"{x['verse']}. {x['text']}" for x in verses)
            reference = f"{parsed['book']} {parsed['chapter']}:{vs}" + (f"-{ve}" if ve != vs else "")
        else:
            text = chapter_data["full_text"]
            reference = chapter_data["reference"]
        return {"reference": reference, "text": text, "version": v}
    except BibleSourceError:
        return None
    except Exception:
        return None
