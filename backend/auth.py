"""Authentication setup with fastapi-users."""

from typing import Optional, Any
from fastapi import Depends
from fastapi_users import FastAPIUsers, BaseUserManager, schemas
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from backend.models import User
    from backend.database import AsyncSessionLocal
    from backend.config import SECRET_KEY, JWT_LIFETIME_SECONDS
except ImportError:
    from models import User
    from database import AsyncSessionLocal
    from config import SECRET_KEY, JWT_LIFETIME_SECONDS


# User schemas for registration/response
class UserRead(schemas.BaseUser[str]):
    """User schema for reading."""
    full_name: str
    company_name: Optional[str] = None
    role: str
    temp_password: Optional[str] = None
    mail_sent: Optional[bool] = False
    created_by_id: Optional[str] = None


class UserCreate(schemas.BaseUserCreate):
    """User schema for creation."""
    full_name: str
    company_name: Optional[str] = None
    role: Optional[str] = "recruiter"
    temp_password: Optional[str] = None
    mail_sent: Optional[bool] = False
    created_by_id: Optional[str] = None


class UserUpdate(schemas.BaseUserUpdate):
    """User schema for update."""
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    role: Optional[str] = None
    temp_password: Optional[str] = None
    mail_sent: Optional[bool] = None


async def get_user_db(session: AsyncSession = Depends(lambda: AsyncSessionLocal())):
    """Get user database."""
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(BaseUserManager):
    """Custom user manager for fastapi-users."""
    reset_password_token_secret = SECRET_KEY
    verification_token_secret = SECRET_KEY

    async def on_after_register(self, user: User, request=None):
        print(f"[Auth] User registered: {user.email}")

    async def on_after_login(self, user: User, request=None, response=None):
        print(f"[Auth] User logged in: {user.email}")

    def parse_id(self, value: Any) -> str:
        return str(value)


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    """Get user manager."""
    yield UserManager(user_db)


# JWT Strategy
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")

jwt_strategy = JWTStrategy(secret=SECRET_KEY, lifetime_seconds=JWT_LIFETIME_SECONDS)

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=lambda: jwt_strategy,
)

# FastAPIUsers
fastapi_users = FastAPIUsers(
    get_user_manager,
    [auth_backend],
)

# Dependency for protected routes
current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
current_active_user_optional = fastapi_users.current_user(active=True, optional=True)


from fastapi import HTTPException

async def get_current_recruiter(user: User = Depends(current_active_user)) -> User:
    """Dependency to check if the user is a recruiter or superuser."""
    user_role = getattr(user, "role", "recruiter")
    print(f"[Auth] get_current_recruiter called: email={user.email}, role={user_role}, is_superuser={user.is_superuser}")
    if user_role != "recruiter" and not user.is_superuser:
        print(f"[Auth] 403 - User {user.email} has role={user_role}, denying access")
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Only recruiters can access this resource."
        )
    return user
