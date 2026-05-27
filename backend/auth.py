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


class UserCreate(schemas.BaseUserCreate):
    """User schema for creation."""
    full_name: str


class UserUpdate(schemas.BaseUserUpdate):
    """User schema for update."""
    full_name: Optional[str] = None


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
