import os

import markdown as md_lib
from flask import Flask
from flask_login import current_user

from .access import user_has_access
from .extensions import db, login_manager, migrate
from .page_registry import NAV_ITEMS, PAGES


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object("config.Config")

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["AVATAR_UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["AGENT_AVATAR_UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from .models import (AiAgent, AgentConversation, AgentMessage,  # noqa: F401
                          Attribute, FeatureFlag, Integration, LlmModel,
                          LlmRequestLog, UserActivityLog, ApiRequestLog,
                          NavItem, NavSection,
                          Permission, ReleaseNote, Role, User)

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    from .routes.agents import agents_bp
    from .routes.auth import auth_bp
    from .routes.help import help_bp
    from .routes.main import main_bp
    from .routes.models import models_bp
    from .routes.permissions import permissions_bp
    from .routes.reporting import reporting_bp
    from .routes.users import users_bp

    app.register_blueprint(agents_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(help_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(models_bp)
    app.register_blueprint(permissions_bp)
    app.register_blueprint(reporting_bp)
    app.register_blueprint(users_bp)

    @app.template_filter("md")
    def render_markdown(text: str) -> str:
        return md_lib.markdown(text or "", extensions=["tables", "fenced_code"])

    @app.context_processor
    def inject_permissions():
        return {"has_access": user_has_access}

    @app.context_processor
    def inject_feature_flags():
        """Make feature flag states available in every template as `flag_<key>`.
        Defaults all known flags to True when the table doesn't exist yet,
        so a pending migration never hides UI from users."""
        _KNOWN_FLAGS = ["conversations", "learning_center", "ai_agents_section", "system_overview"]
        flags = {f"flag_{k}": True for k in _KNOWN_FLAGS}
        try:
            for f in FeatureFlag.query.all():
                flags[f"flag_{f.key}"] = f.is_enabled
        except Exception:
            pass
        return flags

    @app.context_processor
    def inject_nav():
        """Build the sidebar nav structure from NavSection / NavItem DB records.
        Falls back gracefully if the tables don't exist yet."""
        nav = []
        try:
            flag_cache: dict = {}
            try:
                for f in FeatureFlag.query.all():
                    flag_cache[f.key] = f.is_enabled
            except Exception:
                pass

            for section in NavSection.query.order_by(NavSection.sequence).all():
                visible = []
                for ni in section.visible_items:
                    reg = NAV_ITEMS.get(ni.page_slug)
                    if not reg:
                        continue
                    ff = reg.get("feature_flag")
                    if ff and not flag_cache.get(ff, True):
                        continue
                    if not user_has_access(reg["permission_slug"], "view"):
                        continue
                    visible.append({
                        "slug":             ni.page_slug,
                        "label":            reg["label"],
                        "icon":             reg["icon"],
                        "endpoint":         reg["endpoint"],
                        "active_endpoints": reg["active_endpoints"],
                    })
                if visible:
                    nav.append({
                        "name":       section.name,
                        "short_name": section.short_name or "",
                        "pages":      visible,
                    })
        except Exception:
            pass
        return {"nav_sections": nav, "nav_registry": NAV_ITEMS}

    with app.app_context():
        _seed_defaults()

    return app


def _seed_defaults() -> None:
    from sqlalchemy import inspect as sa_inspect

    from .models import Attribute, FeatureFlag, Integration, NavItem, NavSection, Permission, Role, User

    inspector = sa_inspect(db.engine)
    if not inspector.has_table("user"):
        return
    existing_cols = {c["name"] for c in inspector.get_columns("user")}
    if "updated_at" not in existing_cols:
        return
    if inspector.has_table("integration"):
        integration_cols = {c["name"] for c in inspector.get_columns("integration")}
        if "use_case" not in integration_cols:
            return
    if not inspector.has_table("feature_flag"):
        return
    if not inspector.has_table("nav_section"):
        return

    admin_role = Role.query.filter_by(name="admin").first()
    if not admin_role:
        admin_role = Role(name="admin", is_system=True)
        db.session.add(admin_role)
        db.session.flush()
        for page in PAGES:
            db.session.add(Permission(role_id=admin_role.id, page_slug=page["slug"], access_level="edit"))
    elif not admin_role.is_system:
        admin_role.is_system = True

    member_role = Role.query.filter_by(name="member").first()
    if not member_role:
        member_role = Role(name="member", is_system=False)
        db.session.add(member_role)
        db.session.flush()
        for page in PAGES:
            level = "view" if page["slug"] in {"dashboard", "help"} else "no_access"
            db.session.add(Permission(role_id=member_role.id, page_slug=page["slug"], access_level=level))
    elif member_role.is_system:
        member_role.is_system = False

    for role in Role.query.all():
        role.is_system = role.name.lower() == "admin"

    for role in Role.query.all():
        for page in PAGES:
            exists = Permission.query.filter_by(role_id=role.id, page_slug=page["slug"]).first()
            if not exists:
                default_level = "edit" if role.name == "admin" else "no_access"
                db.session.add(Permission(role_id=role.id, page_slug=page["slug"], access_level=default_level))

    admin_user = User.query.filter_by(username="admin").first()
    if not admin_user:
        admin_user = User(
            username="admin",
            email="admin@example.com",
            role="admin",
            first_name="System",
            last_name="Administrator",
            must_change_password=True,
        )
        admin_user.set_password("Changeme-123")
        db.session.add(admin_user)

    default_attributes = [
        ("Customer", "SMB", "Small and mid-sized business"),
        ("Customer", "Enterprise", "Larger strategic account"),
        ("Workflow", "Pilot", "Early prototype or validation workflow"),
    ]
    for category, name, description in default_attributes:
        exists = Attribute.query.filter_by(category=category, name=name).first()
        if not exists:
            db.session.add(Attribute(category=category, name=name, description=description))

    default_flags = [
        ("conversations",    "Conversations",       "Show the Conversations page under AI Agents"),
        ("learning_center",  "Learning Center",     "Show the Learning Center page under AI Agents"),
        ("ai_agents_section","AI Agents Section",   "Show the AI Agents section in the left navigation menu"),
        ("system_overview",  "System Overview",     "Show the System Overview section in the left navigation menu"),
    ]
    for key, label, desc in default_flags:
        if not FeatureFlag.query.filter_by(key=key).first():
            db.session.add(FeatureFlag(key=key, label=label, description=desc, is_enabled=True))

    # ── Default nav sections ─────────────────────────────────────────────────
    if NavSection.query.count() == 0:
        default_sections = [
            ("AI Agents",      "AI",    1, ["conversations", "learning_center"]),
            ("Administration", "Admin", 2, ["user_management", "system_config", "reporting"]),
            ("Documentation",  "Docs",  3, ["user_guides", "system_overview"]),
        ]
        for name, short_name, seq, slugs in default_sections:
            section = NavSection(name=name, short_name=short_name, sequence=seq)
            db.session.add(section)
            db.session.flush()
            for i, slug in enumerate(slugs, start=1):
                db.session.add(NavItem(section_id=section.id, page_slug=slug, sequence=i, is_visible=True))

    db.session.commit()
