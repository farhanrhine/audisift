import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# --- Models (all via Groq) ---
CONVERSATION_MODEL = os.getenv("CONVERSATION_MODEL", "openai/gpt-oss-120b")
ASSESSMENT_MODEL   = os.getenv("ASSESSMENT_MODEL",   "llama-3.3-70b-versatile")
WHISPER_MODEL      = os.getenv("WHISPER_MODEL",       "whisper-large-v3-turbo")

# --- Database (SQLAlchemy) ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./audisift.db")

# Fix Render's legacy postgres:// URL format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# --- Authentication (JWT) ---
import secrets
DEFAULT_DEV_KEY = "dev-secret-key-change-in-production-use-openssl-rand-hex-32"
SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_DEV_KEY)

# Auto-generate a secure key on startup if using the default dev key or if it is empty
if SECRET_KEY == DEFAULT_DEV_KEY or SECRET_KEY == "your-secret-key-change-this-in-production" or not SECRET_KEY:
    print("[Config] WARNING: Using auto-generated SECRET_KEY on startup. Active recruiter sessions will log out on server restart.")
    SECRET_KEY = secrets.token_hex(32)

JWT_LIFETIME_SECONDS = int(os.getenv("JWT_LIFETIME_SECONDS", "86400"))  # 24 hours

# --- Email Notifications (optional) ---
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", "")

# --- Monitoring (optional) ---
SENTRY_DSN = os.getenv("SENTRY_DSN", "")

# --- Validation ---
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is not set. Add it to your .env file.")

