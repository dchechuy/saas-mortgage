import os
import sqlite3
import uuid
from datetime import datetime

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


def create_tenant(app, name, slug, is_active=True, external_id=None):
    """Fixture tenant. `external_id` defaults to a random UUID (a test
    double for "some skunkBOX tenant exists") since real Phase 5 code always
    requires one — pass an explicit value to simulate a specific mapping."""
    import uuid as _uuid

    from app.models import Tenant

    with app.app_context():
        tenant = Tenant(
            name=name, slug=slug, is_active=is_active, is_protected=False,
            external_id=external_id or str(_uuid.uuid4()), sync_status="synced",
        )
        db.session.add(tenant)
        db.session.commit()
        return tenant.id


def create_integration(app, tenant_id, use_case="AI Agents", name=None, base_url="https://skunk.example.com",
                       api_key="fake-key", is_active=True):
    from app.crypto import encrypt_value
    from app.models import Integration

    with app.app_context():
        integration = Integration(
            tenant_id=tenant_id, name=name or f"{use_case} Integration {tenant_id}",
            category="LLM", provider="skunkBOX", use_case=use_case,
            api_key_encrypted=encrypt_value(api_key), base_url=base_url, is_active=is_active,
        )
        db.session.add(integration)
        db.session.commit()
        return integration.id


def create_ai_agent(app, tenant_id, integration_id, skunkbox_agent_id, name=None,
                    is_shared=False, is_active=True):
    from app.models import AiAgent

    with app.app_context():
        agent = AiAgent(
            tenant_id=tenant_id, name=name or f"Agent {skunkbox_agent_id}",
            integration_id=integration_id, skunkbox_agent_id=skunkbox_agent_id,
            is_active=is_active, is_shared=is_shared,
        )
        db.session.add(agent)
        db.session.commit()
        return agent.id


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


# ── skunkBOX service client test double (Phase 5) ───────────────────────

class FakeSkunkBox:
    """In-memory stand-in for app.skunkbox_client — routes/CLI code under
    test call the same function names/signatures as the real client, so
    swapping is transparent. Records every call in `.calls`; set
    `.fail_next = (method_name, exception_instance)` to make the next
    matching call raise, for testing partial-failure/recovery paths."""

    def __init__(self):
        self.tenants: dict[str, dict] = {}
        self.collections: dict[int, dict] = {}
        self.agents: dict[int, dict] = {}
        self._next_collection_id = 1
        self._next_agent_id = 1
        self.fail_next: tuple[str, Exception] | None = None
        self.calls: list[tuple] = []

        # ── Phase 7: Components / Datasets / Experiments ────────────────
        self.components: dict[int, dict] = {}
        self._versions_by_id: dict[int, dict] = {}   # version_id -> version dict (also linked into component["versions"])
        self.datasets: dict[int, dict] = {}
        self._dataset_versions_by_id: dict[int, dict] = {}
        self.experiments: dict[int, dict] = {}
        self.valid_model_ids: set[int] = {1}
        self._next_component_id = 1
        self._next_version_id = 1
        self._next_dataset_id = 1
        self._next_dataset_version_id = 1
        self._next_experiment_id = 1

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if self.fail_next and self.fail_next[0] == name:
            _, err = self.fail_next
            self.fail_next = None
            raise err

    @staticmethod
    def _now():
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    def seed(self, name, slug, external_id=None, is_active=True, is_protected=False):
        """Pre-populate a tenant as if skunkBOX already knows about it."""
        external_id = external_id or str(uuid.uuid4())
        now = self._now()
        self.tenants[external_id] = {
            "public_id": external_id, "name": name, "slug": slug,
            "is_active": is_active, "is_protected": is_protected,
            "created_at": now, "updated_at": now,
        }
        return external_id

    def list_tenants(self, updated_since=None, limit=200, offset=0):
        self._record("list_tenants", updated_since=updated_since)
        values = list(self.tenants.values())
        return {"tenants": values, "total": len(values), "limit": limit, "offset": offset}

    def get_tenant(self, external_id):
        self._record("get_tenant", external_id)
        from app.skunkbox_client import SkunkBoxClientError
        if external_id not in self.tenants:
            raise SkunkBoxClientError("No tenant exists with that UUID.",
                                      status_code=404, error_code="tenant_not_found")
        return self.tenants[external_id]

    def create_tenant(self, name, idempotency_key=None):
        self._record("create_tenant", name, idempotency_key=idempotency_key)
        from app.skunkbox_client import SkunkBoxClientError
        for t in self.tenants.values():
            if t["name"] == name:
                raise SkunkBoxClientError(f"A tenant named '{name}' already exists.",
                                          status_code=409, error_code="name_conflict")
        external_id = str(uuid.uuid4())
        now = self._now()
        record = {
            "public_id": external_id, "name": name, "slug": name.lower().replace(" ", "-"),
            "is_active": True, "is_protected": False, "created_at": now, "updated_at": now,
        }
        self.tenants[external_id] = record
        return record

    def update_tenant(self, external_id, name):
        self._record("update_tenant", external_id, name)
        record = self.get_tenant(external_id)
        record["name"] = name
        record["updated_at"] = self._now()
        return record

    def archive_tenant(self, external_id):
        self._record("archive_tenant", external_id)
        record = self.get_tenant(external_id)
        record["is_active"] = False
        return record

    def reactivate_tenant(self, external_id):
        self._record("reactivate_tenant", external_id)
        record = self.get_tenant(external_id)
        record["is_active"] = True
        return record

    # ── Knowledge / Agents management (Phase 6) ─────────────────────────
    #
    # Visibility mirrors skunkBOX's real rule: owner_tenant_external_id ==
    # caller's tenant_id, OR is_shared. `seed_collection`/`seed_agent` take
    # an explicit owner so tests can model both "my own" and "Cofficiency
    # shared" resources without this double needing to know about Cophy's
    # local Tenant table at all.

    def seed_collection(self, name, owner_tenant_external_id, description=None,
                        is_shared=False, document_count=0, collection_id=None):
        cid = collection_id if collection_id is not None else self._next_collection_id
        self._next_collection_id = max(self._next_collection_id, cid + 1)
        self.collections[cid] = {
            "id": cid, "name": name, "description": description,
            "is_shared": is_shared, "document_count": document_count,
            "_owner": owner_tenant_external_id,
        }
        return cid

    def seed_agent(self, name, owner_tenant_external_id, role_title=None, description=None,
                   is_shared=False, is_active=True, agent_id=None):
        aid = agent_id if agent_id is not None else self._next_agent_id
        self._next_agent_id = max(self._next_agent_id, aid + 1)
        self.agents[aid] = {
            "id": aid, "name": name, "role_title": role_title, "description": description,
            "is_shared": is_shared, "is_active": is_active,
            "_owner": owner_tenant_external_id,
        }
        return aid

    @staticmethod
    def _visible(record, tenant_id):
        return record["_owner"] == tenant_id or record["is_shared"]

    @staticmethod
    def _envelope(record, tenant_id):
        owned = record["_owner"] == tenant_id
        out = {k: v for k, v in record.items() if not k.startswith("_")}
        out["owner"] = "self" if owned else "cofficiency"
        out["can_edit"] = owned and not record["is_shared"]
        return out

    def list_knowledge_collections(self, tenant_id):
        self._record("list_knowledge_collections", tenant_id)
        return {"collections": [
            self._envelope(c, tenant_id) for c in self.collections.values() if self._visible(c, tenant_id)
        ]}

    def get_knowledge_collection(self, tenant_id, collection_id):
        self._record("get_knowledge_collection", tenant_id, collection_id)
        from app.skunkbox_client import SkunkBoxClientError
        record = self.collections.get(collection_id)
        if not record or not self._visible(record, tenant_id):
            raise SkunkBoxClientError("No collection exists with that id.",
                                      status_code=404, error_code="collection_not_found")
        return self._envelope(record, tenant_id)

    def list_agents(self, tenant_id):
        self._record("list_agents", tenant_id)
        return {"agents": [
            self._envelope(a, tenant_id) for a in self.agents.values() if self._visible(a, tenant_id)
        ]}

    def get_agent(self, tenant_id, agent_id):
        self._record("get_agent", tenant_id, agent_id)
        from app.skunkbox_client import SkunkBoxClientError
        record = self.agents.get(agent_id)
        if not record or not self._visible(record, tenant_id):
            raise SkunkBoxClientError("No agent exists with that id.",
                                      status_code=404, error_code="agent_not_found")
        return self._envelope(record, tenant_id)

    # ── Components / Datasets / Experiments (Phase 7) ───────────────────
    #
    # Components/Datasets are never shared (PRD §9/§12: single-tenant only)
    # — visibility here is a plain tenant_id match, no is_shared branch.

    @staticmethod
    def _own_or_404(record, tenant_id, message, error_code):
        from app.skunkbox_client import SkunkBoxClientError
        if not record or record["_owner"] != tenant_id:
            raise SkunkBoxClientError(message, status_code=404, error_code=error_code)
        return record

    # Mirrors a real, documented gap in skunkBOX's component_to_dict(): these
    # four PATCH-writable fields are never read back via any management-API
    # response (services/components.py:144-157 on the saas-platform side) —
    # the fake omits them from every envelope too, so a Cophy test can't
    # accidentally pass against behavior the real API doesn't have.
    _COMPONENT_WRITE_ONLY_FIELDS = {"system_prompt", "json_schema", "json_formatting_requirements", "release_notes"}

    @classmethod
    def _component_envelope(cls, c):
        out = {k: v for k, v in c.items()
              if not k.startswith("_") and k not in cls._COMPONENT_WRITE_ONLY_FIELDS}
        out["versions"] = [
            {k: v for k, v in ver.items() if not k.startswith("_")} for ver in c["_version_order"]
        ]
        return out

    def list_components(self, tenant_id, is_active=None, limit=20, offset=0):
        self._record("list_components", tenant_id, is_active=is_active, limit=limit, offset=offset)
        items = [c for c in self.components.values() if c["_owner"] == tenant_id]
        if is_active is not None:
            items = [c for c in items if c["is_active"] == bool(is_active)]
        return {"components": [self._component_envelope(c) for c in items[offset:offset + limit]],
               "total": len(items), "limit": limit, "offset": offset}

    def get_component(self, tenant_id, component_id):
        self._record("get_component", tenant_id, component_id)
        c = self._own_or_404(self.components.get(component_id), tenant_id,
                             "No component exists with that id.", "component_not_found")
        return self._component_envelope(c)

    def create_component(self, tenant_id, title, category_id=None, description=None, idempotency_key=None):
        self._record("create_component", tenant_id, title, category_id=category_id,
                     description=description, idempotency_key=idempotency_key)
        from app.skunkbox_client import SkunkBoxClientError
        if not title:
            raise SkunkBoxClientError("Title is required.", status_code=400, error_code="invalid_request")
        cid = self._next_component_id
        self._next_component_id += 1
        vid = self._next_version_id
        self._next_version_id += 1
        # Stored by reference (not a copy) in both places — promote/update
        # must mutate the one object both `_version_order` and
        # `_versions_by_id` see, or a promotion would go stale in one of them.
        draft = {"id": vid, "_component_id": cid, "version_number": 1, "status": "draft", "prompt": "",
                 "output_fields": None, "justification_prompt": None, "is_locked": False,
                 "created_at": self._now(), "promoted_at": None}
        component = {
            "id": cid, "title": title, "slug": title.lower().replace(" ", "-"), "is_active": True,
            "description": description, "category_id": category_id,
            "system_prompt": None, "json_schema": None, "json_formatting_requirements": None,
            "release_notes": None, "created_at": self._now(), "updated_at": self._now(),
            "_owner": tenant_id, "_version_order": [draft],
        }
        self.components[cid] = component
        self._versions_by_id[vid] = draft
        return self._component_envelope(component)

    def update_component(self, tenant_id, component_id, **fields):
        self._record("update_component", tenant_id, component_id, **fields)
        c = self._own_or_404(self.components.get(component_id), tenant_id,
                             "No component exists with that id.", "component_not_found")
        from app.skunkbox_client import SkunkBoxClientError
        version_fields = {k: v for k, v in fields.items()
                          if k in ("prompt", "output_fields", "justification_prompt")}
        component_fields = {k: v for k, v in fields.items() if k not in version_fields}
        for k, v in component_fields.items():
            c[k] = v
        if version_fields:
            draft = next((v for v in c["_version_order"] if v["status"] == "draft"), None)
            if not draft:
                raise SkunkBoxClientError("This component has no draft version to edit.",
                                          status_code=409, error_code="no_draft")
            if draft["is_locked"]:
                raise SkunkBoxClientError("This draft has already been used in an Experiment and is locked.",
                                          status_code=409, error_code="version_locked")
            draft.update(version_fields)
            self._versions_by_id[draft["id"]].update(version_fields)
        c["updated_at"] = self._now()
        return self._component_envelope(c)

    def list_component_versions(self, tenant_id, component_id):
        self._record("list_component_versions", tenant_id, component_id)
        c = self._own_or_404(self.components.get(component_id), tenant_id,
                             "No component exists with that id.", "component_not_found")
        return {"versions": [{k: v for k, v in ver.items() if not k.startswith("_")} for ver in c["_version_order"]]}

    def promote_component_version(self, tenant_id, component_id, target_status, idempotency_key=None):
        self._record("promote_component_version", tenant_id, component_id, target_status,
                     idempotency_key=idempotency_key)
        c = self._own_or_404(self.components.get(component_id), tenant_id,
                             "No component exists with that id.", "component_not_found")
        from app.skunkbox_client import SkunkBoxClientError
        versions = c["_version_order"]
        if target_status == "release":
            draft = next((v for v in versions if v["status"] == "draft"), None)
            if not draft:
                raise SkunkBoxClientError("No draft version to promote.", status_code=400, error_code="no_draft")
            if any(v["status"] == "release" for v in versions):
                raise SkunkBoxClientError("A release version already exists.",
                                          status_code=400, error_code="release_exists")
            draft["status"] = "release"
            draft["promoted_at"] = self._now()
        elif target_status == "production":
            release = next((v for v in versions if v["status"] == "release"), None)
            if not release:
                raise SkunkBoxClientError("No release version to promote.", status_code=400, error_code="no_release")
            for v in versions:
                if v["status"] == "production":
                    v["status"] = "legacy"
            release["status"] = "production"
            release["promoted_at"] = self._now()
        else:
            raise SkunkBoxClientError("target_status must be 'release' or 'production'.",
                                      status_code=400, error_code="invalid_request")
        c["updated_at"] = self._now()
        return self._component_envelope(c)

    def archive_component(self, tenant_id, component_id):
        self._record("archive_component", tenant_id, component_id)
        c = self._own_or_404(self.components.get(component_id), tenant_id,
                             "No component exists with that id.", "component_not_found")
        c["is_active"] = False
        return self._component_envelope(c)

    def reactivate_component(self, tenant_id, component_id):
        self._record("reactivate_component", tenant_id, component_id)
        c = self._own_or_404(self.components.get(component_id), tenant_id,
                             "No component exists with that id.", "component_not_found")
        c["is_active"] = True
        return self._component_envelope(c)

    @staticmethod
    def _dataset_envelope(d):
        return {k: v for k, v in d.items() if not k.startswith("_")}

    def list_datasets(self, tenant_id, limit=20, offset=0):
        self._record("list_datasets", tenant_id, limit=limit, offset=offset)
        items = [d for d in self.datasets.values() if d["_owner"] == tenant_id]
        return {"datasets": [self._dataset_envelope(d) for d in items[offset:offset + limit]],
               "total": len(items), "limit": limit, "offset": offset}

    def get_dataset(self, tenant_id, dataset_id):
        self._record("get_dataset", tenant_id, dataset_id)
        d = self._own_or_404(self.datasets.get(dataset_id), tenant_id,
                             "No dataset exists with that id.", "dataset_not_found")
        return self._dataset_envelope(d)

    def create_dataset(self, tenant_id, name, description=None, dataset_type="unlabeled", idempotency_key=None):
        self._record("create_dataset", tenant_id, name, description=description,
                     dataset_type=dataset_type, idempotency_key=idempotency_key)
        from app.skunkbox_client import SkunkBoxClientError
        if not name:
            raise SkunkBoxClientError("Name is required.", status_code=400, error_code="invalid_request")
        if dataset_type not in ("labeled", "unlabeled"):
            raise SkunkBoxClientError("Invalid dataset_type.", status_code=400, error_code="invalid_request")
        did = self._next_dataset_id
        self._next_dataset_id += 1
        dataset = {
            "id": did, "name": name, "description": description, "dataset_type": dataset_type,
            "is_labeled": dataset_type == "labeled", "is_active": True, "current_version": None,
            "created_at": self._now(), "updated_at": self._now(), "_owner": tenant_id,
        }
        self.datasets[did] = dataset
        return self._dataset_envelope(dataset)

    def update_dataset(self, tenant_id, dataset_id, name=None, description=None):
        self._record("update_dataset", tenant_id, dataset_id, name=name, description=description)
        d = self._own_or_404(self.datasets.get(dataset_id), tenant_id,
                             "No dataset exists with that id.", "dataset_not_found")
        if name is not None:
            d["name"] = name
        if description is not None:
            d["description"] = description
        d["updated_at"] = self._now()
        return self._dataset_envelope(d)

    def import_dataset_rows(self, tenant_id, dataset_id, rows):
        self._record("import_dataset_rows", tenant_id, dataset_id, rows)
        d = self._own_or_404(self.datasets.get(dataset_id), tenant_id,
                             "No dataset exists with that id.", "dataset_not_found")
        from app.skunkbox_client import SkunkBoxClientError
        if not rows or not isinstance(rows, list):
            raise SkunkBoxClientError("rows must be a non-empty list.", status_code=400, error_code="invalid_request")
        dvid = self._next_dataset_version_id
        self._next_dataset_version_id += 1
        columns = sorted({k for row in rows for k in row.keys()})
        version = {"id": dvid, "version_number": (d["current_version"]["version_number"] + 1
                                                  if d["current_version"] else 1),
                  "row_count": len(rows), "column_count": len(columns)}
        d["current_version"] = version
        d["updated_at"] = self._now()
        self._dataset_versions_by_id[dvid] = {"_dataset_id": dataset_id, "_owner": tenant_id, **version}
        return self._dataset_envelope(d)

    def archive_dataset(self, tenant_id, dataset_id):
        self._record("archive_dataset", tenant_id, dataset_id)
        d = self._own_or_404(self.datasets.get(dataset_id), tenant_id,
                             "No dataset exists with that id.", "dataset_not_found")
        d["is_active"] = False
        return self._dataset_envelope(d)

    @staticmethod
    def _experiment_envelope(e):
        return {k: v for k, v in e.items() if not k.startswith("_")}

    def create_experiment(self, tenant_id, component_version_id, dataset_version_id, model_id,
                          description=None, idempotency_key=None):
        self._record("create_experiment", tenant_id, component_version_id, dataset_version_id, model_id,
                     description=description, idempotency_key=idempotency_key)
        from app.skunkbox_client import SkunkBoxClientError
        version = self._versions_by_id.get(component_version_id)
        owning_component = self.components.get(version["_component_id"]) if version else None
        if not version or not owning_component or owning_component["_owner"] != tenant_id:
            raise SkunkBoxClientError("No component version exists with that id.",
                                      status_code=404, error_code="component_version_not_found")
        if version["status"] not in ("release", "production"):
            raise SkunkBoxClientError("The component version must be Release or Production.",
                                      status_code=400, error_code="invalid_component_version")
        dv = self._dataset_versions_by_id.get(dataset_version_id)
        if not dv or dv["_owner"] != tenant_id:
            raise SkunkBoxClientError("No dataset version exists with that id.",
                                      status_code=404, error_code="dataset_version_not_found")
        if model_id not in self.valid_model_ids:
            raise SkunkBoxClientError("No model exists with that id.",
                                      status_code=404, error_code="model_not_found")
        eid = self._next_experiment_id
        self._next_experiment_id += 1
        experiment = {
            "id": eid, "description": description, "component_id": owning_component["id"],
            "component_version_id": component_version_id, "dataset_version_id": dataset_version_id,
            "model_id": model_id, "status": "pending",
            "total_records": None, "processed_records": 0, "failed_records": 0, "progress_pct": 0,
            "eval_status": None, "eval_overall_score": None, "precision": None, "recall": None,
            "created_at": self._now(), "started_at": None, "completed_at": None,
            "_owner": tenant_id, "_results": [],
        }
        self.experiments[eid] = experiment
        return self._experiment_envelope(experiment)

    def seed_experiment(self, experiment_id, owner_tenant_external_id, status="pending", **overrides):
        """Pre-populate an experiment as if skunkBOX already ran/is running
        it — for tests that need a local Experiment row's
        skunkbox_experiment_id to resolve without going through the full
        create_experiment() validation chain."""
        experiment = {
            "id": experiment_id, "description": None, "component_id": 1,
            "component_version_id": 1, "dataset_version_id": 1, "model_id": 1, "status": status,
            "total_records": None, "processed_records": 0, "failed_records": 0, "progress_pct": 0,
            "eval_status": None, "eval_overall_score": None, "precision": None, "recall": None,
            "created_at": self._now(), "started_at": None, "completed_at": None,
            "_owner": owner_tenant_external_id, "_results": [],
        }
        experiment.update(overrides)
        self.experiments[experiment_id] = experiment
        return experiment_id

    def get_experiment(self, tenant_id, experiment_id):
        self._record("get_experiment", tenant_id, experiment_id)
        e = self._own_or_404(self.experiments.get(experiment_id), tenant_id,
                             "No experiment exists with that id.", "experiment_not_found")
        return self._experiment_envelope(e)

    def get_experiment_results(self, tenant_id, experiment_id, limit=50, offset=0):
        self._record("get_experiment_results", tenant_id, experiment_id, limit=limit, offset=offset)
        e = self._own_or_404(self.experiments.get(experiment_id), tenant_id,
                             "No experiment exists with that id.", "experiment_not_found")
        results = e["_results"]
        return {"experiment": self._experiment_envelope(e), "results": results[offset:offset + limit],
               "total": len(results), "limit": limit, "offset": offset}


@pytest.fixture()
def fake_skunkbox(monkeypatch):
    """Patches every app.skunkbox_client function to route through a fresh
    in-memory FakeSkunkBox for the duration of one test."""
    import app.skunkbox_client as client_module

    fake = FakeSkunkBox()
    for name in ("list_tenants", "get_tenant", "create_tenant",
                "update_tenant", "archive_tenant", "reactivate_tenant",
                "list_knowledge_collections", "get_knowledge_collection",
                "list_agents", "get_agent",
                "list_components", "get_component", "create_component", "update_component",
                "list_component_versions", "promote_component_version",
                "archive_component", "reactivate_component",
                "list_datasets", "get_dataset", "create_dataset", "update_dataset",
                "import_dataset_rows", "archive_dataset",
                "create_experiment", "get_experiment", "get_experiment_results"):
        monkeypatch.setattr(client_module, name, getattr(fake, name))
    return fake
