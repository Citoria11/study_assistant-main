import datetime
import json
import logging
import os
import re
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field as PydanticField
from sqlalchemy.orm import Session

from app.database.models import StudyNotebookEntry
from app.database.session import get_db
from app.routes.auth import decode_token
from app.services.llm import get_llm

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def get_current_user_id(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header.",
        )
    token = authorization.removeprefix("Bearer ")
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload."
        )
    return user_id


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class NotebookEntryCreate(BaseModel):
    session_date: datetime.date
    achievements: List[str] = []
    progress_score: Optional[int] = None
    notes: Optional[str] = None
    unresolved_questions: List[str] = []
    feedback: Optional[str] = None


class NotebookEntryUpdate(BaseModel):
    achievements: Optional[List[str]] = None
    progress_score: Optional[int] = None
    notes: Optional[str] = None
    unresolved_questions: Optional[List[str]] = None
    feedback: Optional[str] = None
    daily_goal: Optional[str] = None
    goal_milestones: Optional[List[str]] = None
    goal_completed: Optional[List[int]] = None


class NotebookEntryResponse(BaseModel):
    id: str
    user_id: str
    session_date: datetime.datetime
    achievements: List[str]
    progress_score: Optional[int]
    notes: Optional[str]
    unresolved_questions: List[str]
    feedback: Optional[str]
    daily_goal: Optional[str] = None
    goal_milestones: Optional[List[str]] = None
    goal_completed: List[int] = []
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class AchievementEvent(BaseModel):
    achievement_type: str  # "memorama" | "trivia" | "memorization"
    topic: Optional[str] = None  # verse(s) or game subject
    # Memorama fields
    pairs: Optional[int] = None
    moves: Optional[int] = None
    # Trivia fields
    score: Optional[int] = None
    total: Optional[int] = None
    pct: Optional[int] = None
    # Memorization fields
    technique: Optional[str] = None  # e.g. "flashcards"
    summary: Optional[str] = None  # extra context for LLM


class AchievementResponse(BaseModel):
    description: str
    entry: NotebookEntryResponse


class GoalSuggestRequest(BaseModel):
    book: str
    chapter: int


# ---------------------------------------------------------------------------
# Milestone matching helper
# ---------------------------------------------------------------------------


class _MilestoneMatchResult(BaseModel):
    completed_indices: List[int] = PydanticField(
        description="Indices (0-based) of milestones that this achievement satisfies. Empty list if none."
    )


def _match_reflection_milestones(
    notes: str,
    pending: List[tuple[int, str]],
) -> List[int]:
    """
    Check whether the saved notes content satisfies any pending reflection milestones.
    Only called for milestones that contain the word 'reflect'.
    """
    if not pending or not notes.strip():
        return []
    milestone_lines = "\n".join(f"  [{i}] {text}" for i, text in pending)
    prompt = (
        "A user saved the following notes in their Bible study notebook:\n\n"
        f'"""\n{notes[:800]}\n"""\n\n'
        "Pending reflection milestones:\n"
        f"{milestone_lines}\n\n"
        "Which of these reflection milestones do the notes address? "
        "Only match if the notes contain substantive reflection on the topic mentioned in the milestone. "
        "A few words are not enough — there must be genuine engagement with the topic. "
        "When in doubt, return an empty list."
    )
    llm = get_llm(temperature=0)
    structured = llm.with_structured_output(_MilestoneMatchResult)
    try:
        result: _MilestoneMatchResult = structured.invoke(
            [{"role": "user", "content": prompt}]
        )
        valid = [
            i
            for i in result.completed_indices
            if any(orig_i == i for orig_i, _ in pending)
        ]
        logger.info("[milestone_reflect] matched indices=%s", valid)
        return valid
    except Exception as exc:
        logger.warning("[milestone_reflect] LLM call failed: %s", exc)
        return []


def _match_milestones_to_achievement(
    achievement_desc: str,
    achievement_type: str,
    topic: Optional[str],
    technique: Optional[str],
    pending: List[tuple[int, str]],
) -> List[int]:
    """
    Use a cheap LLM structured-output call to decide which pending milestones
    the given achievement satisfies. Returns a list of 0-based indices.
    """
    if not pending:
        return []
    milestone_lines = "\n".join(f"  [{i}] {text}" for i, text in pending)
    prompt = (
        "A user just completed ONE specific activity in a Bible study app.\n\n"
        f"Achievement type: {achievement_type}\n"
        f"Technique/subtype: {technique or 'unknown'}\n"
        f"Achievement description: {achievement_desc}\n"
        f"Topic/Verse: {topic or 'unknown'}\n\n"
        "Pending goal milestones (index: text):\n"
        f"{milestone_lines}\n\n"
        "Return the indices of milestones that were DIRECTLY and SPECIFICALLY completed by this achievement.\n\n"
        "STRICT rules — only match when ALL conditions are true:\n"
        "1. The milestone ACTION matches the achievement type exactly:\n"
        "   - technique='flashcards' → only matches milestones about studying/reading with flashcards\n"
        "   - technique contains 'chunking'/'spaced repetition'/'anchor' etc (coach session) → "
        "only matches milestones about memorizing a verse WITH the coach\n"
        "   - achievement_type='memorama' → only matches milestones explicitly about playing Memorama\n"
        "   - achievement_type='trivia' → only matches milestones explicitly about Bible Trivia\n"
        "2. The milestone TOPIC matches the achievement topic (same verse reference or same chapter/book)\n"
        "3. A 'recite from memory' milestone is ONLY matched when the coach explicitly confirmed "
        "the recitation was correct — NOT by a flashcard study session\n"
        "4. 'Write notes reflecting on X' milestones are NEVER matched here — "
        "they are only completed by saving notes in the notebook\n"
        "5. Do NOT match milestones about activities the user has NOT yet done\n"
        "6. When in doubt, return an empty list — it is better to under-match than over-match\n\n"
        "Return ONLY the indices of milestones that were clearly and directly completed."
    )
    llm = get_llm(temperature=0)
    structured = llm.with_structured_output(_MilestoneMatchResult)
    try:
        result: _MilestoneMatchResult = structured.invoke(
            [{"role": "user", "content": prompt}]
        )
        valid = [
            i
            for i in result.completed_indices
            if any(orig_i == i for orig_i, _ in pending)
        ]
        logger.info("[milestone_match] matched indices=%s", valid)
        return valid
    except Exception as exc:
        logger.warning("[milestone_match] LLM call failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/goal/suggest")
def suggest_goal_milestones(
    body: GoalSuggestRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Use LLM to suggest 4–6 study milestones for a given book/chapter."""
    from app.routes.books import _load_bible

    bible = _load_bible()
    book_data = bible.get(body.book)
    if not book_data:
        raise HTTPException(status_code=404, detail="Book not found.")
    chapter_data = book_data.get(body.chapter)
    if not chapter_data:
        raise HTTPException(status_code=404, detail="Chapter not found.")

    preview = "\n".join(f"{v}. {t}" for v, t in chapter_data[:10])

    llm = get_llm(temperature=0.5)
    prompt = (
        f"A Bible student wants to study {body.book} chapter {body.chapter} today.\n\n"
        f"First verses for context:\n{preview}\n\n"
        "Suggest 4-6 study milestones achievable inside a Bible study app. "
        "The app has EXACTLY these activities — use ONLY these types:\n"
        "- Memorize a verse using flashcards (the Bible study agent guides)\n"
        "- Recite a verse from memory to the Bible study agent (agent confirms)\n"
        "- Play Bible Trivia (answer questions about a passage)\n"
        "- Play Memorama (match verse pairs)\n"
        "- Ask the Bible study agent a question about the passage\n"
        "- Write a reflection in the notebook notes (for any reflective/contemplative task)\n\n"
        "IMPORTANT: If you want a reflective milestone, it MUST be phrased as "
        '"Write notes reflecting on [specific topic from the chapter]". '
        "Do NOT suggest generic actions like 'read the chapter', 'identify themes', "
        "'discuss the meaning', 'explore the significance', or any task involving "
        "understanding, interpretation, or discussion of a passage — "
        "every milestone must map to one of the six activity types above.\n\n"
        "Return ONLY a JSON array of strings with no other text. "
        f"Each milestone must be concise (max 90 chars) and specific to {body.book} {body.chapter}. "
        "Example format:\n"
        f'["Memorize {body.book} {body.chapter}:1 using flashcards", '
        f'"Recite {body.book} {body.chapter}:1 from memory to the Bible study agent", '
        f'"Ask the Bible study agent about the main theme of {body.book} {body.chapter}", '
        f'"Complete a Bible Trivia game on {body.book} {body.chapter}", '
        f'"Write notes reflecting on the key message of {body.book} {body.chapter}"]\n\n'
        "Return 4-6 milestones as a JSON array."
    )
    result = llm.invoke([{"role": "user", "content": prompt}])
    content = result.content.strip()
    # Strip markdown code fences if present
    content = re.sub(r"^```[a-z]*\n?", "", content)
    content = re.sub(r"\n?```$", "", content)
    try:
        milestones = json.loads(content)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not parse LLM response.")
    if not isinstance(milestones, list):
        raise HTTPException(status_code=500, detail="Unexpected LLM response format.")
    return {"milestones": [str(m)[:100] for m in milestones[:6]]}


@router.post("/achievement", response_model=AchievementResponse)
def log_achievement(
    body: AchievementEvent,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Auto-log an achievement to today's notebook entry (creating it if needed).

    Games supply structured data → description built locally.
    Memorization activities use an LLM to write a friendly sentence.
    """
    # --- 1. Build description ---
    t = body.achievement_type
    if t == "memorama":
        topic_str = f" on {body.topic}" if body.topic else ""
        desc = (
            f"🃏 Memorama{topic_str}: matched {body.pairs} pairs in {body.moves} moves"
        )
    elif t == "trivia":
        topic_str = f" on {body.topic}" if body.topic else ""
        pct_str = f" ({body.pct}%)" if body.pct is not None else ""
        desc = f"❓ Bible Trivia{topic_str}: {body.score}/{body.total} correct{pct_str}"
    else:
        # Memorization — ask the LLM to write an encouraging notebook entry line
        llm = get_llm(temperature=0.4)
        prompt = (
            "The user just completed a Bible memorization activity.\n"
            f"Verse(s)/Topic: {body.topic or 'Scripture'}\n"
            f"Technique: {body.technique or 'flashcards'}\n"
            f"Additional context: {body.summary or 'none'}\n\n"
            "Write ONE concise sentence (max 120 characters) describing this achievement "
            "for a personal study notebook. Start with the 🧠 emoji. Be specific and encouraging."
        )
        try:
            result = llm.invoke([{"role": "user", "content": prompt}])
            desc = result.content.strip()[:200]
        except Exception as exc:
            logger.warning("[achievement] LLM description failed: %s", exc)
            desc = f"🧠 Studied {body.topic or 'Scripture'} using {body.technique or 'flashcard'} technique"

    logger.info("[achievement] user=%s type=%s desc=%r", user_id, t, desc)

    # --- 2. Find or create today's entry ---
    today_start = datetime.datetime.now(datetime.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    tomorrow_start = today_start + datetime.timedelta(days=1)

    entry = (
        db.query(StudyNotebookEntry)
        .filter(
            StudyNotebookEntry.user_id == user_id,
            StudyNotebookEntry.session_date >= today_start,
            StudyNotebookEntry.session_date < tomorrow_start,
        )
        .first()
    )
    if not entry:
        entry = StudyNotebookEntry(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_date=today_start,
            achievements=[],
            unresolved_questions=[],
        )
        db.add(entry)
        db.flush()

    # --- 3. Append achievement (copy list to signal SQLAlchemy mutation) ---
    entry.achievements = [*entry.achievements, desc]
    entry.updated_at = datetime.datetime.now(datetime.timezone.utc)

    # --- 4. Auto-complete matching goal milestones ---
    milestones = entry.goal_milestones or []
    if milestones:
        already_done = set(entry.goal_completed or [])
        pending = [(i, m) for i, m in enumerate(milestones) if i not in already_done]
        newly_done = _match_milestones_to_achievement(
            desc, t, body.topic, body.technique, pending
        )
        if newly_done:
            new_completed = sorted(already_done | set(newly_done))
            entry.goal_completed = new_completed
            entry.progress_score = round(len(new_completed) / len(milestones) * 100)
            logger.info(
                "[milestone_match] user=%s newly_done=%s progress=%s%%",
                user_id,
                newly_done,
                entry.progress_score,
            )

    db.commit()
    db.refresh(entry)

    return AchievementResponse(description=desc, entry=entry)


@router.delete("/all", status_code=204)
def clear_all_entries(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Delete all notebook entries for the authenticated user."""
    db.query(StudyNotebookEntry).filter(StudyNotebookEntry.user_id == user_id).delete()
    db.commit()


@router.get("/", response_model=List[NotebookEntryResponse])
def list_entries(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Return all notebook entries for the authenticated user, newest first."""
    entries = (
        db.query(StudyNotebookEntry)
        .filter(StudyNotebookEntry.user_id == user_id)
        .order_by(StudyNotebookEntry.session_date.desc())
        .all()
    )
    return entries


@router.get("/{entry_id}", response_model=NotebookEntryResponse)
def get_entry(
    entry_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    entry = (
        db.query(StudyNotebookEntry)
        .filter(
            StudyNotebookEntry.id == entry_id,
            StudyNotebookEntry.user_id == user_id,
        )
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return entry


@router.post("/", response_model=NotebookEntryResponse, status_code=201)
def create_entry(
    body: NotebookEntryCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if body.progress_score is not None and not (0 <= body.progress_score <= 100):
        raise HTTPException(
            status_code=400, detail="progress_score must be between 0 and 100."
        )

    session_dt = datetime.datetime.combine(
        body.session_date, datetime.time.min, tzinfo=datetime.timezone.utc
    )

    entry = StudyNotebookEntry(
        id=str(uuid.uuid4()),
        user_id=user_id,
        session_date=session_dt,
        achievements=body.achievements,
        progress_score=body.progress_score,
        notes=body.notes,
        unresolved_questions=body.unresolved_questions,
        feedback=body.feedback,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=NotebookEntryResponse)
def update_entry(
    entry_id: str,
    body: NotebookEntryUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    entry = (
        db.query(StudyNotebookEntry)
        .filter(
            StudyNotebookEntry.id == entry_id,
            StudyNotebookEntry.user_id == user_id,
        )
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found.")

    if body.progress_score is not None and not (0 <= body.progress_score <= 100):
        raise HTTPException(
            status_code=400, detail="progress_score must be between 0 and 100."
        )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)

    # Auto-calculate progress from completed milestones
    upd = body.model_dump(exclude_unset=True)
    if "goal_completed" in upd or "goal_milestones" in upd:
        milestones = entry.goal_milestones
        completed = entry.goal_completed or []
        if milestones and len(milestones) > 0:
            entry.progress_score = round(len(completed) / len(milestones) * 100)

    # When feedback (Reflection) is saved, check if any pending reflection milestone is satisfied
    if "feedback" in upd and upd["feedback"] and entry.goal_milestones:
        already_done = set(entry.goal_completed or [])
        reflection_pending = [
            (i, m)
            for i, m in enumerate(entry.goal_milestones)
            if i not in already_done and "reflect" in m.lower()
        ]
        if reflection_pending:
            newly_done = _match_reflection_milestones(
                upd["feedback"], reflection_pending
            )
            if newly_done:
                new_completed = sorted(already_done | set(newly_done))
                entry.goal_completed = new_completed
                entry.progress_score = round(
                    len(new_completed) / len(entry.goal_milestones) * 100
                )
                logger.info(
                    "[milestone_reflect] newly_done=%s progress=%s%%",
                    newly_done,
                    entry.progress_score,
                )

    entry.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_entry(
    entry_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    entry = (
        db.query(StudyNotebookEntry)
        .filter(
            StudyNotebookEntry.id == entry_id,
            StudyNotebookEntry.user_id == user_id,
        )
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found.")
    db.delete(entry)
    db.commit()
