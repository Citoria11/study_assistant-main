import logging
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.models import User
from app.database.session import get_db
from app.rag.vectorstore import (
    _get_or_load,
    _cache,
    _cache_lock,
    _resolve_asset_and_index,
)
from app.routes.auth import decode_token

router = APIRouter()
logger = logging.getLogger(__name__)

_TRANSLATIONS_DIR = Path(__file__).parent.parent / "assets" / "translations"
_ASV_FALLBACK = Path(__file__).parent.parent / "assets" / "asv.txt"

# Well-known display names for translation IDs
_DISPLAY_NAMES = {
    "ASV": "American Standard Version (1901)",
    "AAB": "Accessible Ancients Bible",
    "BSB": "Berean Standard Bible",
    "ENGWEBP": "World English Bible",
    "eng_asv": "American Standard Version (1901)",
    "eng_bbe": "Bible in Basic English",
    "eng_cpb": "KJV Cambridge Paragraph",
    "eng_dby": "Darby Translation",
    "eng_dra": "Douay-Rheims 1899",
    "eng_fbv": "Free Bible Version",
    "eng_gnv": "Geneva Bible 1599",
    "eng_kjv": "King James Version",
    "eng_kja": "King James Version + Apocrypha",
    "eng_lsv": "English LSV",
    "eng_msb": "Majority Standard Bible",
    "eng_net": "NET Bible",
    "eng_ojb": "Orthodox Jewish Bible",
    "eng_rv5": "Revised Version",
    "eng_t4t": "Translation for Translators",
    "eng_ulb": "Unlocked Literal Bible",
    "eng_wbs": "Webster Bible",
    "eng_web": "World English Bible Classic",
    "eng_webpb": "World English Bible British Edition",
    "eng_webu": "World English Bible Updated",
    "eng_weu": "World English Bible British Edition with Deuterocanon",
    "eng_wmb": "World Messianic Bible",
    "eng_wmu": "World Messianic Bible British Edition",
    "eng_wyc2017": "Wycliffe's Bible Modern Spelling",
    "eng_wyc2018": "Wycliffe's Bible Modern Spelling (Enhanced)",
    "eng_ylt": "Young's Literal Translation",
    "eng_abt": "ASV Byzantine Text",
    "eng_webc": "World English Bible (Catholic)",
}


class TranslationItem(BaseModel):
    id: str
    name: str


class SetTranslationRequest(BaseModel):
    translation: str


class SetTranslationResponse(BaseModel):
    translation: str


def _available_translations() -> list[TranslationItem]:
    """Return translations that have a downloaded .txt file, plus ASV fallback."""
    results: list[TranslationItem] = []

    # Built-in fallback
    if _ASV_FALLBACK.exists():
        results.append(
            TranslationItem(
                id="ASV", name="American Standard Version (1901) [built-in]"
            )
        )

    if _TRANSLATIONS_DIR.exists():
        for txt in sorted(_TRANSLATIONS_DIR.glob("*.txt")):
            tid = txt.stem
            name = _DISPLAY_NAMES.get(tid, tid)
            results.append(TranslationItem(id=tid, name=name))

    return results


@router.get("/translations", response_model=list[TranslationItem])
def list_translations():
    """Return all downloaded Bible translations available for use."""
    return _available_translations()


@router.put("/translation", response_model=SetTranslationResponse)
def set_translation(
    body: SetTranslationRequest, token: str, db: Session = Depends(get_db)
):
    """Update the authenticated user's preferred Bible translation."""
    payload = decode_token(token)
    user = db.get(User, payload.get("sub"))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    available_ids = {t.id for t in _available_translations()}
    if body.translation not in available_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Translation '{body.translation}' is not available. Download it first.",
        )

    user.preferred_translation = body.translation
    db.commit()
    logger.info("User %s set translation to %s", user.id, body.translation)

    # Pre-warm the vectorstore for the new translation in the background
    def _warm():
        try:
            _get_or_load(body.translation)
        except Exception as exc:
            logger.warning(
                "Background vectorstore warm-up failed for %s: %s",
                body.translation,
                exc,
            )

    threading.Thread(target=_warm, daemon=True).start()

    return SetTranslationResponse(translation=body.translation)


@router.get("/translation", response_model=SetTranslationResponse)
def get_translation(token: str, db: Session = Depends(get_db)):
    """Get the authenticated user's preferred Bible translation."""
    payload = decode_token(token)
    user = db.get(User, payload.get("sub"))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return SetTranslationResponse(translation=user.preferred_translation or "ASV")


class TranslationStatusResponse(BaseModel):
    translation: str
    ready: bool  # True = index is loaded in cache or exists on disk


@router.get("/translation/status", response_model=TranslationStatusResponse)
def get_translation_status(translation: str):
    """Check whether a translation's FAISS index is ready (cached or on disk)."""
    with _cache_lock:
        if translation in _cache:
            return TranslationStatusResponse(translation=translation, ready=True)
    # Not in cache — check if the index file exists on disk
    try:
        _, index_dir = _resolve_asset_and_index(translation)
        ready = (index_dir / "index.faiss").exists()
    except FileNotFoundError:
        ready = False
    return TranslationStatusResponse(translation=translation, ready=ready)
