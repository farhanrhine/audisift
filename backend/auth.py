"""Authentication setup with fastapi-users."""

from typing import Optional
from fastapi import Depends
from fastapi_users import FastAPIUsers, BaseUserManager
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
class UserRead(BaseModel):
    """User schema for reading."""
    id: int
    email: EmailStr
    is_active: bool
    is_superuser: bool
    full_name: str

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """User schema for creation."""
    email: EmailStr
    password: str
    full_name: str


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
