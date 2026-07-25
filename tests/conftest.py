import os
import sqlite3

import pytest
from flask import Flask
from flask_migrate import Migrate
from flask_migrate import upgrade as fm_upgrade

from app.extensions import db

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MIGRATIONS_DIR = os.path.join(BASE_DIR, "migrations")

# Head immediately before the tenant-schema migration — i.e. the schema shape
# of a real pre-Phase-1 install.
PRE_TENANT_REVISION = "11b469c6d972"


def _bare_app(db_path: str) -> Flask:
    """A Flask app with just db/migrate wired up — no blueprints, login
    manager, or startup seeding. migrations/env.py reads the engine from
    current_app.extensions['migrate'], so running flask_migrate.upgrade()
    needs an app context bound to the target database, not a bare Alembic
    Config."""
    flask_app = Flask(__name__)
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)
    Migrate(flask_app, db)
    return flask_app


@pytest.fixture()
def legacy_db(tmp_path):
    """A SQLite DB migrated to the revision just before the tenant migration,
    pre-populated with sample legacy data resembling a real pre-Phase-1 install:
    two users (one named 'admin', one not), and one row each of the tenant-owned
    operational tables and log tables."""
    db_path = str(tmp_path / "legacy.db")
    flask_app = _bare_app(db_path)
    with flask_app.app_context():
        fm_upgrade(directory=MIGRATIONS_DIR, revision=PRE_TENANT_REVISION)

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO user (username, email, password_hash, role, is_active, "
        "must_change_password, created_at, updated_at) VALUES "
        "('admin', 'admin@example.com', 'x', 'admin', 1, 0, '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO user (username, email, password_hash, role, is_active, "
        "must_change_password, created_at, updated_at) VALUES "
        "('jane', 'jane@example.com', 'x', 'member', 1, 0, '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO llm_model (name, provider, deployment_name, endpoint_url, "
        "api_key_encrypted, model_type, is_active, is_default, created_at, updated_at) "
        "VALUES ('gpt-4', 'Azure OpenAI', 'gpt-4-deploy', 'https://example.com', "
        "'enc', 'chat', 1, 1, '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO attribute (category, name, description, is_active, created_at) "
        "VALUES ('Customer', 'SMB', 'desc', 1, '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO integration (name, category, provider, use_case, is_active, "
        "created_at, updated_at) VALUES "
        "('OpenAI Prod', 'LLM', 'OpenAI', 'AI Agents', 1, '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO ai_agent (name, integration_id, skunkbox_agent_id, is_active, "
        "created_at, updated_at) VALUES ('Helper', 1, 1, 1, '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO agent_conversation (title, ai_agent_id, user_id, is_archived, "
        "is_favorite, created_at, updated_at) VALUES "
        "('Test convo', 1, 1, 0, 0, '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO llm_request_log (model_id, model_name, use_case, status, created_at) "
        "VALUES (1, 'gpt-4', 'chat', 'success', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO user_activity_log (user_id, action, page, created_at) "
        "VALUES (1, 'user.login', 'Login', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO api_request_log (integration_id, integration_name, endpoint, "
        "method, status_code, created_at) VALUES "
        "(1, 'OpenAI Prod', '/v1/models', 'GET', 200, '2026-01-01')"
    )
    conn.commit()
    conn.close()

    return db_path


@pytest.fixture()
def app(legacy_db):
    """A Flask app bound to the legacy database, migrated the rest of the way
    to head (applying the tenant migration on top of realistic pre-existing
    data) inside the same app context the migration itself will run under."""
    flask_app = _bare_app(legacy_db)
    with flask_app.app_context():
        fm_upgrade(directory=MIGRATIONS_DIR, revision="head")
        yield flask_app
