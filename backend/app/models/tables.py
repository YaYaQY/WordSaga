from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Vocabulary(Base):
    __tablename__ = "vocabulary"

    word: Mapped[str] = mapped_column(String(64), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, index=True)
    frequency: Mapped[int] = mapped_column(Integer, index=True)
    level: Mapped[str] = mapped_column(String(16))
    meaning: Mapped[str] = mapped_column(Text)


class UserSetting(Base):
    __tablename__ = "user_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class WordProgress(Base):
    __tablename__ = "word_progress"

    word: Mapped[str] = mapped_column(String(64), ForeignKey("vocabulary.word"), primary_key=True)
    seen_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    mastery: Mapped[float] = mapped_column(Float, default=0.0)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LearningSession(Base):
    __tablename__ = "learning_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16))
    level: Mapped[str] = mapped_column(String(16))
    style: Mapped[str] = mapped_column(String(128))
    word_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime)

    words: Mapped[list["SessionWord"]] = relationship(back_populates="session")
    story: Mapped["StoryPackage | None"] = relationship(back_populates="session")


class SessionWord(Base):
    __tablename__ = "session_words"
    __table_args__ = (UniqueConstraint("session_id", "word", name="uq_session_word"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_sessions.id"))
    word: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16))
    meaning: Mapped[str] = mapped_column(Text)

    session: Mapped["LearningSession"] = relationship(back_populates="words")


class StoryPackage(Base):
    __tablename__ = "story_packages"

    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_sessions.id"), primary_key=True)
    title: Mapped[str] = mapped_column(String(256))
    summary: Mapped[str] = mapped_column(Text)
    world_context: Mapped[str] = mapped_column(Text)

    session: Mapped["LearningSession"] = relationship(back_populates="story")
    chapters: Mapped[list["StoryChapter"]] = relationship(back_populates="story")


class StoryChapter(Base):
    __tablename__ = "story_chapters"
    __table_args__ = (UniqueConstraint("session_id", "chapter_index", name="uq_session_chapter"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("story_packages.session_id"))
    chapter_index: Mapped[int] = mapped_column(Integer)
    full_story_en: Mapped[str] = mapped_column(Text)
    annotated_story_zh: Mapped[str] = mapped_column(Text)
    occurrences_json: Mapped[str] = mapped_column(Text)

    story: Mapped["StoryPackage"] = relationship(back_populates="chapters")


class WrongRecord(Base):
    __tablename__ = "wrong_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[str] = mapped_column(String(36))
    stage: Mapped[int] = mapped_column(Integer)
    user_answer: Mapped[str] = mapped_column(Text)
    correct_answer: Mapped[str] = mapped_column(Text)
    error_type: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime)
