"""SQLAlchemy ORM models for AI Tutor Screener."""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid

Base = declarative_base()


class User(Base):
    """User account (recruiter or admin)."""
    __tablename__ = "user"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    organization_id = Column(String(36), ForeignKey("organization.id"), nullable=True)
    company_name = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default="recruiter")
    temp_password = Column(String(255), nullable=True)
    mail_sent = Column(Boolean, default=False)
    created_by_id = Column(String(36), ForeignKey("user.id"), nullable=True)

    # Relationships
    organization = relationship("Organization", back_populates="users")
    sessions = relationship("Session", back_populates="owner", foreign_keys="[Session.owner_id]")
    notes = relationship("SessionNote", back_populates="author")


class Organization(Base):
    """Organization (for future multi-tenant support)."""
    __tablename__ = "organization"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    users = relationship("User", back_populates="organization")
    sessions = relationship("Session", back_populates="organization")


class Session(Base):
    """Interview session."""
    __tablename__ = "session"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_name = Column(String(255), nullable=False)
    candidate_email = Column(String(255), nullable=True)
    status = Column(String(50), default="in_progress", index=True)  # in_progress, completed, generating, abandoned
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    exchange_count = Column(Integer, default=0)
    uncovered_dimensions = Column(Text, nullable=True)  # JSON stringified list
    interview_state = Column(Text, nullable=True)  # JSON stringified InterviewState (Phase 3)
    organization_id = Column(String(36), ForeignKey("organization.id"), nullable=True)
    owner_id = Column(String(36), ForeignKey("user.id"), nullable=True)
    candidate_user_id = Column(String(36), ForeignKey("user.id"), nullable=True)
    # Denormalized for fast dashboard queries (written when assessment is saved)
    overall_score = Column(Float, nullable=True, index=True)
    recommendation = Column(String(100), nullable=True, index=True)

    # Relationships
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    assessment = relationship("Assessment", back_populates="session", uselist=False, cascade="all, delete-orphan")
    organization = relationship("Organization", back_populates="sessions")
    owner = relationship("User", back_populates="sessions", foreign_keys=[owner_id])
    candidate_user = relationship("User", foreign_keys=[candidate_user_id])
    notes = relationship("SessionNote", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    """Interview message (candidate or interviewer)."""
    __tablename__ = "message"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("session.id"), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # "candidate", "interviewer"
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    session = relationship("Session", back_populates="messages")


class Assessment(Base):
    """Assessment report for a completed session."""
    __tablename__ = "assessment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("session.id"), unique=True, nullable=False, index=True)
    report_json = Column(Text, nullable=False)  # Full JSON report
    created_at = Column(DateTime, default=datetime.utcnow)
    overall_score = Column(Integer, nullable=True)  # Cached overall score for filtering
    recommendation = Column(String(100), nullable=True)  # "Move to next round", "Reservations", "Do not move forward"

    # Relationships
    session = relationship("Session", back_populates="assessment")


class SessionNote(Base):
    """Private notes added by recruiters to a session."""
    __tablename__ = "session_note"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("session.id"), nullable=False, index=True)
    author_id = Column(String(36), ForeignKey("user.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = relationship("Session", back_populates="notes")
    author = relationship("User", back_populates="notes")


class BulkLink(Base):
    """Bulk interview links for recruiter distribution (Phase 8)."""
    __tablename__ = "bulk_link"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(128), unique=True, nullable=False, index=True)  # Unique one-time token
    batch_label = Column(String(255), nullable=False)  # e.g., "May 2026 Batch"
    created_by_id = Column(String(36), ForeignKey("user.id"), nullable=False)
    session_id = Column(String(36), ForeignKey("session.id"), nullable=True)  # Assigned when link is used
    created_at = Column(DateTime, default=datetime.utcnow)
    used_at = Column(DateTime, nullable=True)  # Null if not yet used

    # Relationships
    created_by = relationship("User")
    session = relationship("Session")
