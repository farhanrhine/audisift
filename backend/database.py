"""Database operations using SQLAlchemy ORM."""

import json
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine, select, update
from sqlalchemy.pool import NullPool, StaticPool

try:
    from backend.models import Base, Session, Message, Assessment, Organization, User, SessionNote, BulkLink, IssueReport
    from backend.config import DATABASE_URL
except ImportError:
    from models import Base, Session, Message, Assessment, Organization, User, SessionNote, BulkLink, IssueReport
    from config import DATABASE_URL


# Create async engine
if "sqlite" in DATABASE_URL:
    # SQLite with aiosqlite - use NullPool
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        poolclass=NullPool,
        connect_args={"timeout": 30, "check_same_thread": False},
    )
else:
    # PostgreSQL
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables on startup."""
    # For SQLite, use sync engine to avoid greenlet issues
    if "sqlite" in DATABASE_URL:
        sync_db_url = DATABASE_URL.replace("sqlite+aiosqlite", "sqlite")
        sync_engine = create_engine(sync_db_url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(sync_engine)
        # Dynamically add columns if they don't exist
        with sync_engine.connect() as conn:
            try:
                conn.execute("ALTER TABLE user ADD COLUMN company_name VARCHAR(255)")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE user ADD COLUMN role VARCHAR(50) DEFAULT 'recruiter'")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE user ADD COLUMN temp_password VARCHAR(255)")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE user ADD COLUMN mail_sent BOOLEAN DEFAULT 0")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE user ADD COLUMN created_by_id VARCHAR(36)")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE session ADD COLUMN candidate_user_id VARCHAR(36)")
            except Exception:
                pass
        sync_engine.dispose()
    else:
        # For PostgreSQL, use async
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            try:
                await conn.execute("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS company_name VARCHAR(255)")
            except Exception:
                pass
            try:
                await conn.execute("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'recruiter'")
            except Exception:
                pass
            try:
                await conn.execute("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS temp_password VARCHAR(255)")
            except Exception:
                pass
            try:
                await conn.execute("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS mail_sent BOOLEAN DEFAULT FALSE")
            except Exception:
                pass
            try:
                await conn.execute("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS created_by_id VARCHAR(36)")
            except Exception:
                pass
            try:
                await conn.execute("ALTER TABLE \"session\" ADD COLUMN IF NOT EXISTS candidate_user_id VARCHAR(36)")
            except Exception:
                pass


async def get_session_obj() -> AsyncSession:
    """Get a database session."""
    async with AsyncSessionLocal() as session:
        yield session


# --------- Session Management ---------


async def create_session(candidate_name: str, candidate_email: str = None, organization_id: str = None, owner_id: str = None, candidate_user_id: str = None) -> str:
    """Create a new interview session."""
    async with AsyncSessionLocal() as db:
        session = Session(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            organization_id=organization_id,
            owner_id=owner_id,
            candidate_user_id=candidate_user_id,
            status="in_progress",
        )
        db.add(session)
        await db.commit()
        return session.id


async def get_session(session_id: str) -> Session | None:
    """Fetch a session by ID."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()


async def get_all_sessions(organization_id: str = None, owner_id: str = None, status: str = None, limit: int = 100, offset: int = 0) -> list[Session]:
    """Get sessions with optional filters."""
    async with AsyncSessionLocal() as db:
        query = select(Session)
        if organization_id:
            query = query.where(Session.organization_id == organization_id)
        if owner_id:
            query = query.where(Session.owner_id == owner_id)
        if status:
            query = query.where(Session.status == status)
        query = query.order_by(Session.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return result.scalars().all()


async def update_session_status(session_id: str, status: str):
    """Update session status."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Session).where(Session.id == session_id).values(
                status=status,
                completed_at=datetime.utcnow() if status == "completed" else None
            )
        )
        await db.commit()


async def update_session_state(session_id: str, exchange_count_or_state, uncovered_dimensions: list = None, interview_state: dict = None):
    """
    Update session state. Supports two calling patterns:
    1. update_session_state(session_id, exchange_count, uncovered_dimensions, interview_state)
    2. update_session_state(session_id, interview_state_dict) - new LangGraph style
    """
    async with AsyncSessionLocal() as db:
        values = {}
        
        # Detect calling pattern
        if isinstance(exchange_count_or_state, dict):
            # New LangGraph style: second arg is the InterviewState dict
            state_dict = exchange_count_or_state
            values[Session.exchange_count] = state_dict.get("exchange_count", 0)
            values[Session.uncovered_dimensions] = json.dumps(state_dict.get("dimensions_uncovered", []))
            values[Session.interview_state] = json.dumps(state_dict, default=str)
        else:
            # Old style: second arg is exchange_count
            exchange_count = exchange_count_or_state
            values[Session.exchange_count] = exchange_count
            if uncovered_dimensions:
                values[Session.uncovered_dimensions] = json.dumps(uncovered_dimensions)
            if interview_state:
                values[Session.interview_state] = json.dumps(interview_state, default=str)
        
        await db.execute(update(Session).where(Session.id == session_id).values(values))
        await db.commit()


async def complete_session(session_id: str):
    """Mark session as completed."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Session).where(Session.id == session_id).values(
                status="completed",
                completed_at=datetime.utcnow()
            )
        )
        await db.commit()


async def abandon_old_sessions(minutes: int = 30):
    """Mark sessions with no activity for X minutes as abandoned."""
    cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Session)
            .where(
                (Session.status == "in_progress") &
                (Session.created_at < cutoff_time)
            )
            .values(status="abandoned")
        )
        await db.commit()


# --------- Message Management ---------


async def save_message(session_id: str, role: str, content: str):
    """Save a message to the session."""
    async with AsyncSessionLocal() as db:
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
        )
        db.add(message)
        await db.commit()


async def get_messages(session_id: str) -> list[dict]:
    """Fetch all messages for a session."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message).where(Message.session_id == session_id).order_by(Message.timestamp)
        )
        messages = result.scalars().all()
        return [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()}
            for m in messages
        ]


# --------- Assessment Management ---------


async def save_assessment(session_id: str, report_json: str, recommendation: str = None, overall_score: float = None):
    """Save assessment report and denormalize score onto Session for fast dashboard queries."""
    async with AsyncSessionLocal() as db:
        assessment = Assessment(
            session_id=session_id,
            report_json=report_json,
            recommendation=recommendation,
            overall_score=overall_score,
        )
        db.add(assessment)
        # Denormalize onto Session row so dashboard queries don't need a join
        await db.execute(
            update(Session).where(Session.id == session_id).values(
                overall_score=overall_score,
                recommendation=recommendation,
                status="completed",
                completed_at=datetime.utcnow(),
            )
        )
        await db.commit()


async def get_assessment(session_id: str) -> Assessment | None:
    """Fetch assessment for a session."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Assessment).where(Assessment.session_id == session_id)
        )
        return result.scalar_one_or_none()


# --------- Organization Management ---------


async def create_organization(name: str) -> str:
    """Create a new organization."""
    async with AsyncSessionLocal() as db:
        org = Organization(name=name)
        db.add(org)
        await db.commit()
        return org.id


async def get_organization(org_id: str) -> Organization | None:
    """Fetch organization by ID."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one_or_none()


# --------- Session Notes ---------


async def add_session_note(session_id: str, author_id: str, content: str):
    """Add a note to a session."""
    async with AsyncSessionLocal() as db:
        note = SessionNote(
            session_id=session_id,
            author_id=author_id,
            content=content,
        )
        db.add(note)
        await db.commit()


async def get_session_notes(session_id: str) -> list[SessionNote]:
    """Get all notes for a session."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SessionNote)
            .where(SessionNote.session_id == session_id)
            .order_by(SessionNote.created_at)
        )
        return result.scalars().all()


# --------- Bulk Interview Links (Phase 8) ---------


async def create_bulk_link(token: str, batch_label: str, created_by_id: str) -> BulkLink:
    """Create a new bulk interview link."""
    async with AsyncSessionLocal() as db:
        link = BulkLink(
            token=token,
            batch_label=batch_label,
            created_by_id=created_by_id,
        )
        db.add(link)
        await db.commit()
        return link


async def get_bulk_link(token: str) -> BulkLink | None:
    """Fetch a bulk link by token."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(BulkLink).where(BulkLink.token == token)
        )
        return result.scalar_one_or_none()


async def use_bulk_link(token: str, session_id: str):
    """Mark a bulk link as used and associate with a session."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(BulkLink)
            .where(BulkLink.token == token)
            .values(session_id=session_id, used_at=datetime.utcnow())
        )
        await db.commit()


async def get_bulk_links_for_user(user_id: str, limit: int = 100) -> list[BulkLink]:
    """Get all bulk links created by a user."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(BulkLink)
            .where(BulkLink.created_by_id == user_id)
            .order_by(BulkLink.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()


async def get_candidates_for_recruiter(owner_id: str) -> list[User]:
    """Get all candidates created by a recruiter."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User)
            .where(User.created_by_id == owner_id, User.role == "candidate")
            .order_by(User.created_at.desc())
        )
        return result.scalars().all()


async def update_candidate_mail_sent(user_id: str, mail_sent: bool):
    """Update candidate mail sent status."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(mail_sent=mail_sent)
        )
        await db.commit()


# --------- Issue Reports & Feedback ---------

async def create_issue_report(reporter_name: str = None, reporter_email: str = None, role: str = "candidate", description: str = "") -> IssueReport:
    """Create a new issue/feedback report."""
    async with AsyncSessionLocal() as db:
        report = IssueReport(
            reporter_name=reporter_name,
            reporter_email=reporter_email,
            role=role,
            description=description,
            status="open"
        )
        db.add(report)
        await db.commit()
        return report


async def get_all_issue_reports() -> list[IssueReport]:
    """Get all issue reports, newest first."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(IssueReport).order_by(IssueReport.created_at.desc())
        )
        return result.scalars().all()


async def update_issue_status(issue_id: int, status: str):
    """Update status of a reported issue."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(IssueReport)
            .where(IssueReport.id == issue_id)
            .values(status=status)
        )
        await db.commit()


async def get_recruiters_usage_stats() -> list[dict]:
    """Get statistics for all recruiters (company, candidate count, interview count)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.role == "recruiter").order_by(User.created_at.desc())
        )
        recruiters = result.scalars().all()
        
        stats = []
        for r in recruiters:
            # Count candidates created by this recruiter
            cand_res = await db.execute(
                select(User).where(User.created_by_id == r.id, User.role == "candidate")
            )
            candidates_count = len(cand_res.scalars().all())
            
            # Count interview sessions owned by this recruiter
            sess_res = await db.execute(
                select(Session).where(Session.owner_id == r.id)
            )
            sessions_count = len(sess_res.scalars().all())
            
            stats.append({
                "id": r.id,
                "email": r.email,
                "full_name": r.full_name,
                "company_name": r.company_name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "candidate_count": candidates_count,
                "session_count": sessions_count
            })
        return stats
