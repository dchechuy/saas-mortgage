import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "app.db"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")
    PORT = int(os.environ.get("PORT", "5011"))
    AVATAR_UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads", "avatars")
    AGENT_AVATAR_UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads", "agent_avatars")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    # skunkBOX service client (Cross-System Tenant AI Assets, Phase 5) — the
    # Cophy-side service credential, distinct from any per-tenant Integration
    # API key. Never logged; see app/skunkbox_client.py.
    SKUNKBOX_BASE_URL = os.environ.get("SKUNKBOX_BASE_URL", "http://localhost:5000")
    SKUNKBOX_SERVICE_SECRET = os.environ.get("SKUNKBOX_SERVICE_SECRET", "")
    SKUNKBOX_CLIENT_TIMEOUT = float(os.environ.get("SKUNKBOX_CLIENT_TIMEOUT", "10"))
