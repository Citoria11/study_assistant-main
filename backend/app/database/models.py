import datetime

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    Integer,
    JSON,
)

from app.database.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, index=True)  # UUID string
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    preferred_translation = Column(String(32), nullable=False, default="ASV")
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<User email={self.email!r}>"


class StudyNotebookEntry(Base):
    """
    One entry per study session for a user.

    Tracks daily achievements, cumulative progress, free-form notes,
    unresolved questions, and the user's own feedback on the session.
    """

    __tablename__ = "study_notebook"

    id = Column(String(36), primary_key=True, index=True)  # UUID string
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Date of the study session (date only, not datetime — one entry per day)
    session_date = Column(DateTime, nullable=False, index=True)

    # Daily achievements: list of short strings, e.g. ["Memorized John 3:16", "Completed Trivia"]
    achievements = Column(JSON, nullable=False, default=list)

    # Progress score 0–100 representing the user's self-assessed or computed progress
    progress_score = Column(Integer, nullable=True)

    # Free-form study notes for the session
    notes = Column(Text, nullable=True)

    # Unresolved questions: list of strings the user wants to follow up on
    unresolved_questions = Column(JSON, nullable=False, default=list)

    # User's own reflective feedback on the session
    feedback = Column(Text, nullable=True)

    # Daily goal tracking
    daily_goal = Column(Text, nullable=True)  # e.g. "John 3"
    goal_milestones = Column(JSON, nullable=True)  # list of str
    goal_completed = Column(
        JSON, nullable=False, default=list
    )  # list of int (completed indices)

    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<StudyNotebookEntry user_id={self.user_id!r} date={self.session_date!r}>"
        )


class Checkpointer(Base):
    """
    Stores LangGraph checkpointer state keyed by thread_id.

    LangGraph's built-in SqliteSaver/PostgresSaver can manage this
    automatically; this model is provided as an explicit SQLAlchemy
    representation for reference and custom queries.
    """

    __tablename__ = "checkpointers"

    thread_id = Column(String(255), primary_key=True, index=True)
    checkpoint_data = Column(Text, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<Checkpointer thread_id={self.thread_id!r}>"
