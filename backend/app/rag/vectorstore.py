import logging
import os
import re
import threading
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS

from app.services.llm import get_embeddings

logger = logging.getLogger(__name__)

_ASSETS_DIR = Path(__file__).parent.parent / "assets"
_FAISS_BASE = Path(__file__).parent / "faiss_index"

# ---------------------------------------------------------------------------
# Per-translation cache
# Each entry: {"retriever": ..., "verse_index": {...}, "ref_re": ...}
# ---------------------------------------------------------------------------
_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()

# The "default" translation loaded at startup (used when no translation specified)
_default_translation: Optional[str] = None


_VERSE_RE = re.compile(r"^(.+?\s\d+:\d+)\s+(.+)$")


def _normalise_ref(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip().lower())


def _load_documents(asset_path: Path) -> list[Document]:
    docs: list[Document] = []
    with open(asset_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = _VERSE_RE.match(line)
            if not m:
                continue
            reference, text = m.group(1), m.group(2)
            docs.append(Document(page_content=text, metadata={"reference": reference}))
    logger.info("Loaded %d verses from %s", len(docs), asset_path.name)
    return docs


def _build_ref_regex(docs: list[Document]) -> re.Pattern:
    """Build a regex using only real Bible book names from the index."""
    book_names: set[str] = set()
    for doc in docs:
        m = re.match(r"^(.+?)\s+\d+:\d+$", doc.metadata["reference"])
        if m:
            book_names.add(m.group(1))
    sorted_books = sorted(book_names, key=len, reverse=True)
    book_alts = "|".join(re.escape(b) for b in sorted_books)
    pattern = rf"(?i)\b({book_alts})\s+(\d+):(\d+(?:-\d+)?)\b"
    logger.info("Built verse reference regex for %d book names", len(sorted_books))
    return re.compile(pattern, re.IGNORECASE)


def _resolve_asset_and_index(translation: str) -> tuple[Path, Path]:
    """Return (asset_txt_path, faiss_index_dir) for a translation ID."""
    if translation == "ASV":
        asset = _ASSETS_DIR / "asv.txt"
        index_dir = _FAISS_BASE / "ASV"
    else:
        asset = _ASSETS_DIR / "translations" / f"{translation}.txt"
        index_dir = _FAISS_BASE / translation
    if not asset.exists():
        raise FileNotFoundError(
            f"Bible text file not found: {asset}\n"
            f"Run: python backend/scripts/download_translations.py --only {translation}"
        )
    return asset, index_dir


def _load_translation(translation: str) -> dict:
    """Build or load a FAISS index for *translation* and return a cache entry."""
    embeddings = get_embeddings()
    asset_path, index_dir = _resolve_asset_and_index(translation)

    index_file = index_dir / "index.faiss"
    if index_file.exists():
        logger.info("[%s] Loading existing FAISS index from %s", translation, index_dir)
        vectorstore = FAISS.load_local(
            str(index_dir), embeddings, allow_dangerous_deserialization=True
        )
        docs = _load_documents(asset_path)
    else:
        logger.info(
            "[%s] FAISS index not found — building from scratch (~1 min)…", translation
        )
        docs = _load_documents(asset_path)
        vectorstore = FAISS.from_documents(docs, embeddings)
        index_dir.mkdir(parents=True, exist_ok=True)
        vectorstore.save_local(str(index_dir))
        logger.info("[%s] FAISS index saved to %s", translation, index_dir)

    verse_index = {_normalise_ref(doc.metadata["reference"]): doc for doc in docs}
    logger.info("[%s] Verse lookup index built (%d entries)", translation, len(verse_index))

    ref_re = _build_ref_regex(docs)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
    logger.info("[%s] RAG retriever ready", translation)

    return {"retriever": retriever, "verse_index": verse_index, "ref_re": ref_re}


def _get_or_load(translation: str) -> dict:
    """Return cached entry for *translation*, loading it on first access (thread-safe)."""
    with _cache_lock:
        if translation not in _cache:
            logger.info("[%s] Not in cache — loading…", translation)
            _cache[translation] = _load_translation(translation)
        return _cache[translation]


_DEFAULT_TRANSLATION = "BSB"


def init_rag() -> None:
    """Pre-warm the default translation cache at startup."""
    global _default_translation
    _default_translation = _DEFAULT_TRANSLATION
    logger.info("Default translation: %s", _default_translation)
    _get_or_load(_default_translation)


def _exact_lookup(query: str, entry: dict) -> list[Document]:
    """Match explicit verse references in the query using book-name-aware regex."""
    ref_re: re.Pattern = entry["ref_re"]
    verse_index: dict = entry["verse_index"]

    found: list[Document] = []
    seen: set[str] = set()

    for m in ref_re.finditer(query):
        book = m.group(1).strip()
        chapter = m.group(2)
        verse_part = m.group(3)

        if "-" in verse_part:
            start, end = verse_part.split("-", 1)
            verse_nums = range(int(start), int(end) + 1)
        else:
            verse_nums = [int(verse_part)]

        for v in verse_nums:
            key = _normalise_ref(f"{book} {chapter}:{v}")
            if key in verse_index and key not in seen:
                found.append(verse_index[key])
                seen.add(key)

    return found


def retrieve(
    query: str, translation: Optional[str] = None, semantic_k: int = 5
) -> tuple[list[Document], list[Document]]:
    """
    Returns (exact_docs, semantic_docs) for the given translation.
    Falls back to the default translation if none is specified.
    """
    t = translation or _default_translation or "ASV"
    entry = _get_or_load(t)

    exact = _exact_lookup(query, entry)
    exact_refs = {_normalise_ref(d.metadata["reference"]) for d in exact}

    remaining_slots = max(0, semantic_k - len(exact))
    semantic: list[Document] = []

    if remaining_slots > 0:
        for doc in entry["retriever"].invoke(query):
            if _normalise_ref(doc.metadata["reference"]) not in exact_refs:
                semantic.append(doc)
                if len(semantic) >= remaining_slots:
                    break

    return exact, semantic


def get_retriever(translation: Optional[str] = None):
    t = translation or _default_translation or "ASV"
    return _get_or_load(t)["retriever"]

