"""
Books route – serves the ASV Bible text paginated by book and chapter.

Endpoints
---------
GET /api/books/
    Returns the ordered list of book names.

GET /api/books/{book}/{chapter}
    Returns all verses for the given book / chapter number.
    Also includes total_chapters so the frontend can build prev/next navigation.

POST /api/books/search
    Natural-language / typo-tolerant search. Uses an LLM to interpret the query
    as either a Bible reference or a phrase search, then validates / executes it
    against the loaded ASV text. Returns one reference hit or up to 10 phrase hits.
"""

import logging
import os
import re
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.llm import get_llm

router = APIRouter()

ASV_PATH = Path(__file__).parent.parent / "assets" / "asv.txt"

# ---------------------------------------------------------------------------
# Data loading (parsed once at first request)
# ---------------------------------------------------------------------------

_VERSE_RE = re.compile(
    r"^(?P<book>.+?)\s+(?P<chapter>\d+):(?P<verse>\d+)\s+(?P<text>.+)$"
)


@lru_cache(maxsize=1)
def _load_bible() -> "OrderedDict[str, dict[int, list[tuple[int, str]]]]":
    data: OrderedDict = OrderedDict()
    with open(ASV_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            m = _VERSE_RE.match(line)
            if not m:
                continue
            book = m.group("book")
            chapter = int(m.group("chapter"))
            verse = int(m.group("verse"))
            text = m.group("text")
            if book not in data:
                data[book] = {}
            if chapter not in data[book]:
                data[book][chapter] = []
            data[book][chapter].append((verse, text))
    return data


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class VerseItem(BaseModel):
    verse: int
    text: str


class ChapterResponse(BaseModel):
    book: str
    chapter: int
    total_chapters: int
    verses: List[VerseItem]


class BooksResponse(BaseModel):
    books: List[str]


class SearchQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=300)


class SearchHit(BaseModel):
    book: str
    chapter: int
    verse: int
    text: str


class SearchResponse(BaseModel):
    match_type: str  # "reference" | "phrase" | "not_found"
    interpretation: str  # human-readable explanation of what was understood
    hits: List[SearchHit]  # 1 item for reference, up to 10 for phrase


# ---------------------------------------------------------------------------
# LLM interpretation schema (structured output)
# ---------------------------------------------------------------------------


class _LLMInterpretation(BaseModel):
    match_type: str = Field(
        description=(
            "'reference' if the query is a Bible reference (book + chapter + optional verse), "
            "'phrase' if it is a text phrase, keyword, or partial quote to search for."
        )
    )
    book: Optional[str] = Field(
        None,
        description=(
            "Resolved book name, chosen EXACTLY from the provided book list. "
            "Correct typos and abbreviations (e.g. 'jon' → 'John', 'psalm' → 'Psalms', "
            "'rev' → 'Revelation', '1 sam' → '1 Samuel'). Null for phrase searches."
        ),
    )
    chapter: Optional[int] = Field(
        None,
        description="Chapter number. Null if not specified or phrase search.",
    )
    verse: Optional[int] = Field(
        None,
        description="Verse number. Null if not specified or not a verse-level reference.",
    )
    phrase: Optional[str] = Field(
        None,
        description=(
            "Cleaned, lowercase search phrase for substring matching. "
            "Remove filler words if unhelpful. Null for reference searches."
        ),
    )
    interpretation: str = Field(
        description=(
            "A brief human-readable description of what was understood, "
            "e.g. 'Genesis 1:2' or 'Searching for \"waste and void\"'."
        )
    )


_SEARCH_SYSTEM = (
    "You are a Bible reference resolver. "
    "Given a user query, interpret it as either a specific Bible reference "
    "(possibly with typos or abbreviations) or a phrase/keyword search.\n\n"
    "Available book names (use EXACTLY one of these for the 'book' field):\n"
    "{book_list}\n\n"
    "Rules:\n"
    "- Treat abbreviations liberally: 'jon'→'John', 'ps'→'Psalms', 'gen'→'Genesis', "
    "'rev'→'Revelation', '1 sam'→'1 Samuel', 'phil'→'Philippians', etc.\n"
    "- 'john316' or 'john 316' means John 3:16.\n"
    "- If only a book and chapter are given (no verse), set verse=null.\n"
    "- If the query looks like a partial quote or keywords, use match_type='phrase'.\n"
    "- For phrase searches provide a clean lowercase phrase (2–6 words work best)."
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", response_model=BooksResponse)
def list_books():
    """Return ordered list of all book names."""
    bible = _load_bible()
    return BooksResponse(books=list(bible.keys()))


@router.post("/search", response_model=SearchResponse)
def search_bible(body: SearchQuery):
    """
    Natural-language search. Uses an LLM to parse the query into either a
    Bible reference or a phrase, then validates / executes it against the ASV.
    """
    logger.info("[search] query=%r", body.query)
    bible = _load_bible()
    book_list = ", ".join(bible.keys())

    # --- 1. LLM interpretation ---
    llm = get_llm(temperature=0)
    structured = llm.with_structured_output(_LLMInterpretation)
    system_prompt = _SEARCH_SYSTEM.format(book_list=book_list)
    try:
        interp: _LLMInterpretation = structured.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": body.query},
            ]
        )
        logger.info(
            "[search] LLM interpreted: match_type=%r book=%r chapter=%r verse=%r phrase=%r interpretation=%r",
            interp.match_type,
            interp.book,
            interp.chapter,
            interp.verse,
            interp.phrase,
            interp.interpretation,
        )
    except Exception as exc:
        logger.exception("[search] LLM call failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc

    # --- 2a. Reference resolution ---
    if interp.match_type == "reference" and interp.book and interp.chapter:
        # Case-insensitive match against actual book list
        matched_book = next(
            (b for b in bible if b.lower() == interp.book.lower()), None
        )
        # Fallback: partial match (e.g. LLM returned "Psalm" vs "Psalms")
        if matched_book is None:
            matched_book = next(
                (b for b in bible if b.lower().startswith(interp.book.lower()[:4])),
                None,
            )
        if matched_book is None:
            logger.warning("[search] book not found: %r", interp.book)
            return SearchResponse(
                match_type="not_found",
                interpretation=f"Could not find book '{interp.book}' in the Bible.",
                hits=[],
            )

        logger.info("[search] matched book=%r", matched_book)
        book_data = bible[matched_book]
        if interp.chapter not in book_data:
            logger.warning(
                "[search] chapter not found: %r ch=%r (total=%d)",
                matched_book,
                interp.chapter,
                len(book_data),
            )
            return SearchResponse(
                match_type="not_found",
                interpretation=(
                    f"{matched_book} has only {len(book_data)} chapter(s); "
                    f"chapter {interp.chapter} does not exist."
                ),
                hits=[],
            )

        if interp.verse is not None:
            verse_map = {v: t for v, t in book_data[interp.chapter]}
            if interp.verse not in verse_map:
                logger.warning(
                    "[search] verse not found: %r %r:%r",
                    matched_book,
                    interp.chapter,
                    interp.verse,
                )
                return SearchResponse(
                    match_type="not_found",
                    interpretation=(
                        f"{matched_book} {interp.chapter} has no verse {interp.verse}."
                    ),
                    hits=[],
                )
            logger.info(
                "[search] reference hit: %r %r:%r",
                matched_book,
                interp.chapter,
                interp.verse,
            )
            return SearchResponse(
                match_type="reference",
                interpretation=interp.interpretation,
                hits=[
                    SearchHit(
                        book=matched_book,
                        chapter=interp.chapter,
                        verse=interp.verse,
                        text=verse_map[interp.verse],
                    )
                ],
            )
        else:
            # Chapter-only reference — return first verse as the navigation target
            first_verse, first_text = book_data[interp.chapter][0]
            logger.info(
                "[search] chapter-only reference hit: %r ch=%r",
                matched_book,
                interp.chapter,
            )
            return SearchResponse(
                match_type="reference",
                interpretation=interp.interpretation,
                hits=[
                    SearchHit(
                        book=matched_book,
                        chapter=interp.chapter,
                        verse=first_verse,
                        text=first_text,
                    )
                ],
            )

    # --- 2b. Phrase search ---
    _STOP_WORDS = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "of",
        "to",
        "for",
        "is",
        "was",
        "are",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "can",
        "could",
        "that",
        "this",
        "it",
        "its",
        "he",
        "she",
        "they",
        "them",
        "his",
        "her",
        "their",
        "my",
        "your",
        "not",
        "no",
        "nor",
        "so",
        "yet",
        "at",
        "by",
        "from",
        "with",
        "on",
        "as",
        "up",
        "out",
        "into",
        "than",
        "then",
        "when",
        "who",
        "which",
        "what",
        "there",
        "i",
        "we",
        "ye",
        "thou",
        "thee",
        "thy",
        "said",
        "unto",
        "upon",
        "also",
        "over",
        "all",
        "one",
        "me",
    }

    phrase = (interp.phrase or body.query).lower().strip()
    logger.info("[search] phrase search: %r", phrase)

    def _scan(match_fn) -> list[SearchHit]:
        results: list[SearchHit] = []
        for book_name, chapters in bible.items():
            for chap_num, verse_list in chapters.items():
                for v_num, v_text in verse_list:
                    if match_fn(v_text.lower()):
                        results.append(
                            SearchHit(
                                book=book_name,
                                chapter=chap_num,
                                verse=v_num,
                                text=v_text,
                            )
                        )
                    if len(results) >= 10:
                        return results
        return results

    # Level 1: exact substring
    hits = _scan(lambda t: phrase in t)
    logger.info("[search] exact-phrase hits: %d", len(hits))

    # Level 2: all significant keywords must appear
    keywords: list[str] = []
    if not hits:
        keywords = [w for w in re.split(r"\W+", phrase) if w and w not in _STOP_WORDS]
        logger.info("[search] falling back to keyword search: %r", keywords)
        if keywords:
            hits = _scan(lambda t, kw=keywords: all(k in t for k in kw))
            logger.info("[search] keyword hits: %d", len(hits))

    # Level 3: majority of keywords (≥ 60%) must appear
    if not hits and keywords:
        threshold = max(1, round(len(keywords) * 0.6))
        logger.info(
            "[search] falling back to partial keyword search (threshold=%d/%d)",
            threshold,
            len(keywords),
        )
        hits = _scan(
            lambda t, kw=keywords, th=threshold: sum(1 for k in kw if k in t) >= th
        )
        logger.info("[search] partial-keyword hits: %d", len(hits))

    logger.info("[search] final hits: %d", len(hits))
    if not hits:
        return SearchResponse(
            match_type="not_found",
            interpretation=f"No verses found containing '{phrase}'.",
            hits=[],
        )

    return SearchResponse(
        match_type="phrase",
        interpretation=interp.interpretation,
        hits=hits,
    )


@router.get("/{book}/{chapter}", response_model=ChapterResponse)
def get_chapter(book: str, chapter: int):
    """Return all verses for a specific book and chapter."""
    bible = _load_bible()

    matched_book = next((b for b in bible if b.lower() == book.lower()), None)
    if matched_book is None:
        raise HTTPException(status_code=404, detail=f"Book '{book}' not found.")

    book_data = bible[matched_book]
    if chapter not in book_data:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter {chapter} not found in '{matched_book}'.",
        )

    verses = [VerseItem(verse=v, text=t) for v, t in book_data[chapter]]
    return ChapterResponse(
        book=matched_book,
        chapter=chapter,
        total_chapters=len(book_data),
        verses=verses,
    )
