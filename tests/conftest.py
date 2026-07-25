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
def migrated_db(legacy_db):
    """legacy_db migrated the rest of the way to head — applies every
    migration up to and including the tenant ones on top of realistic
    pre-existing data."""
    flask_app = _bare_app(legacy_db)
    with flask_app.app_context():
        fm_upgrade(directory=MIGRATIONS_DIR, revision="head")
    return legacy_db


@pytest.fixture()
def app(migrated_db):
    """A bare Flask app (no blueprints, login manager, or seeding) bound to
    the migrated database — used by Phase 1 model/migration tests that only
    need the ORM."""
    flask_app = _bare_app(migrated_db)
    with flask_app.app_context():
        yield flask_app


@pytest.fixture()
def full_app(migrated_db, monkeypatch):
    """The real application — blueprints, login manager, startup seeding —
    bound to the migrated database. Used by Phase 2+ route/web-flow tests.

    Patches config.Config.SQLALCHEMY_DATABASE_URI directly rather than the
    DATABASE_URL env var: config.py reads the env var once at first import,
    so a later env var change wouldn't reach create_app() if config had
    already been imported by an earlier test in the same pytest session.

    Deliberately does NOT wrap the yield in `with flask_app.app_context():`.
    Flask reuses an already-active app context for the same app rather than
    pushing a fresh one (see Flask's RequestContext.push()), so a persistent
    outer context here would make every `client.post()`/`client.get()` in the
    test share one `flask.g` — silently resurrecting stale per-request caches
    (e.g. tenant_context's g-based active-tenant cache) across what should be
    independent requests. Real requests never have this problem since nothing
    holds a context open between them. Direct ORM access in test bodies
    should open its own `with full_app.app_context():` block instead.
    """
    import config as config_module

    monkeypatch.setattr(config_module.Config, "SQLALCHEMY_DATABASE_URI", f"sqlite:///{migrated_db}")

    from app import create_app
    flask_app = create_app()
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield flask_app


@pytest.fixture()
def client(full_app):
    return full_app.test_client()


# ── Shared helpers for Phase 2+ route/web-flow tests ────────────────────────

def set_password(app, username, password):
    """Set a known password on a fixture user, bypassing must_change_password."""
    from app.models import User

    with app.app_context():
        user = User.query.filter_by(username=username).one()
        user.set_password(password)
        user.must_change_password = False
        db.session.commit()
        return user.id


def login(client, username, password):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=True)


def ensure_baseline_permissions(app, role_name="member"):
    """The `jane` fixture user's role ('member') has no matching Role row by
    default, which resolves to no_access on every page — including
    'dashboard', the post-login landing page. That's an unrelated pre-existing
    gap in the permission system (not something Tenant Separation should fix),
    so tests that log in as a non-admin fixture user grant it baseline view
    access here, mirroring what a real non-admin role would have."""
    from app.models import Permission, Role
    from app.page_registry import PAGES

    with app.app_context():
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name, is_system=False)
            db.session.add(role)
            db.session.flush()
        for page in PAGES:
            if not Permission.query.filter_by(role_id=role.id, page_slug=page["slug"]).first():
                db.session.add(Permission(role_id=role.id, page_slug=page["slug"], access_level="view"))
        db.session.commit()


def create_tenant(app, name, slug, is_active=True):
    from app.models import Tenant

    with app.app_context():
        tenant = Tenant(name=name, slug=slug, is_active=is_active, is_protected=False)
        db.session.add(tenant)
        db.session.commit()
        return tenant.id


def create_user(app, username, tenant_id, role="member", password="Test-1234"):
    from app.models import User

    with app.app_context():
        user = User(
            username=username, email=f"{username}@example.com", role=role,
            tenant_id=tenant_id, must_change_password=False,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id
