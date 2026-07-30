import os
from urllib.parse import urlparse

import markdown as md_lib
from flask import Flask, flash, jsonify, redirect, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError

from .access import user_has_access
from .extensions import csrf, db, login_manager, migrate
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
    csrf.init_app(app)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        """Return a safe response for stale, missing, or invalid CSRF tokens.

        Browser fetch calls receive JSON; ordinary form posts are redirected
        to a safe same-origin page so login and expired sessions never enter a
        POST redirect loop.
        """
        message = "Your form expired or could not be verified. Please try again."
        is_ajax = (
            request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.accept_mimetypes.best == "application/json"
        )
        if is_ajax:
            return jsonify({"ok": False, "error": "csrf_failed", "message": message}), 400

        flash(message, "error")
        referrer = request.referrer
        if referrer:
            parsed = urlparse(referrer)
            if not parsed.netloc or parsed.netloc == request.host:
                safe_path = parsed.path or "/"
                if parsed.query:
                    safe_path = f"{safe_path}?{parsed.query}"
                return redirect(safe_path)
        if current_user.is_authenticated:
            return redirect(url_for("agents.list_conversations"))
        return redirect(url_for("auth.login"))

    from .models import (AiAgent, AgentConversation, AgentMessage,  # noqa: F401
                          Attribute, DocPrompt, Experiment, FeatureFlag, Integration, LlmModel,
                          LlmRequestLog, UserActivityLog, ApiRequestLog,
                          NavItem, NavSection,
                          Permission, ReleaseNote, Role, Tenant, TenantFeatureFlag, User)

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    from .routes.agents import agents_bp
    from .routes.auth import auth_bp
    from .routes.help import help_bp
    from .routes.main import main_bp
    from .routes.models import models_bp
    from .routes.permissions import permissions_bp
    from .routes.quality import quality_bp
    from .routes.reporting import reporting_bp
    from .routes.tenants import tenants_bp
    from .routes.users import users_bp

    app.register_blueprint(agents_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(help_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(models_bp)
    app.register_blueprint(permissions_bp)
    app.register_blueprint(quality_bp)
    app.register_blueprint(reporting_bp)
    app.register_blueprint(tenants_bp)
    app.register_blueprint(users_bp)

    from .cli import register_cli
    register_cli(app)

    @app.template_filter("md")
    def render_markdown(text: str) -> str:
        return md_lib.markdown(text or "", extensions=["tables", "fenced_code"])

    @app.context_processor
    def inject_permissions():
        return {"has_access": user_has_access}

    @app.context_processor
    def inject_tenant_switcher():
        """Expose the active tenant and switcher options to every template.
        Only Cofficiency users get switcher data; external users always see
        their single home tenant with no switch control."""
        from .tenant_context import can_switch_tenants, get_active_tenant

        if not current_user.is_authenticated:
            return {"active_tenant": None, "can_switch_tenants": False, "switchable_tenants": []}

        switchable = can_switch_tenants()
        tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all() if switchable else []
        return {
            "active_tenant": get_active_tenant(),
            "can_switch_tenants": switchable,
            "switchable_tenants": tenants,
        }

    @app.context_processor
    def inject_feature_flags():
        """Make effective (tenant-override-aware) feature flag states available
        in every template as `flag_<key>`. Defaults all known flags to True
        when the table doesn't exist yet, so a pending migration never hides
        UI from users."""
        from .feature_flags import effective_feature_flags

        # ai_quality deliberately excluded: its real default is False (see
        # _seed_defaults' default_flags), unlike every other flag here,
        # which default True pre-migration as a defensive fallback.
        _KNOWN_FLAGS = ["conversations", "learning_center", "ai_agents_section", "system_overview"]
        flags = {f"flag_{k}": True for k in _KNOWN_FLAGS}
        try:
            for key, enabled in effective_feature_flags().items():
                flags[f"flag_{key}"] = enabled
        except Exception:
            pass
        return flags

    @app.context_processor
    def inject_nav():
        """Build the sidebar nav structure from NavSection / NavItem DB records.
        Falls back gracefully if the tables don't exist yet."""
        from .feature_flags import effective_feature_flags
        from .tenant_context import is_cofficiency_user

        nav = []
        try:
            flag_cache: dict = {}
            try:
                flag_cache = effective_feature_flags()
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
                    if reg.get("cofficiency_only") and not is_cofficiency_user():
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

    from .models import (Attribute, DocPrompt, FeatureFlag, Integration, NavItem, NavSection,
                          Permission, Role, Tenant, User)

    inspector = sa_inspect(db.engine)
    if not inspector.has_table("user"):
        return
    existing_cols = {c["name"] for c in inspector.get_columns("user")}
    if "updated_at" not in existing_cols:
        return
    if "tenant_id" not in existing_cols:
        return
    if inspector.has_table("integration"):
        integration_cols = {c["name"] for c in inspector.get_columns("integration")}
        if "use_case" not in integration_cols:
            return
        if "tenant_id" not in integration_cols:
            return
    if not inspector.has_table("feature_flag"):
        return
    if not inspector.has_table("nav_section"):
        return
    if not inspector.has_table("doc_prompt"):
        return
    if not inspector.has_table("tenant"):
        return
    tenant_cols = {c["name"] for c in inspector.get_columns("tenant")}
    if "external_id" not in tenant_cols:
        return

    cofficiency = Tenant.query.filter_by(slug="cofficiency").first()
    advantagefirst = Tenant.query.filter_by(slug="advantagefirst").first()
    if not cofficiency or not advantagefirst:
        # Tenant seed rows are inserted by the tenant migration itself; if they
        # aren't there yet, the schema isn't fully migrated — don't race it.
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
            tenant_id=cofficiency.id,
        )
        admin_user.set_password("Changeme-123")
        db.session.add(admin_user)

    default_attributes = [
        ("Customer", "SMB", "Small and mid-sized business"),
        ("Customer", "Enterprise", "Larger strategic account"),
        ("Workflow", "Pilot", "Early prototype or validation workflow"),
    ]
    for category, name, description in default_attributes:
        exists = Attribute.query.filter_by(
            tenant_id=advantagefirst.id, category=category, name=name
        ).first()
        if not exists:
            db.session.add(Attribute(
                tenant_id=advantagefirst.id, category=category, name=name, description=description
            ))

    default_flags = [
        ("conversations",    "Conversations",       "Show the Conversations page under AI Agents", True),
        ("learning_center",  "Learning Center",     "Show the Learning Center page under AI Agents", True),
        ("ai_agents_section","AI Agents Section",   "Show the AI Agents section in the left navigation menu", True),
        ("system_overview",  "System Overview",     "Show the System Overview section in the left navigation menu", True),
        # Off by default — enabled per customer via a TenantFeatureFlag
        # override once they're ready for the Components/Datasets/AI
        # Quality workflow (Cross-System Tenant AI Assets PRD Phase 7).
        ("ai_quality",       "AI Assets & Quality", "Show AI Assets, Datasets, and AI Quality in the left navigation menu", False),
    ]
    for key, label, desc, default_enabled in default_flags:
        if not FeatureFlag.query.filter_by(key=key).first():
            db.session.add(FeatureFlag(key=key, label=label, description=desc, is_enabled=default_enabled))

    # Nav sections are seeded via migration h8i9j0k1l2m3, not at startup.
    # Seeding here caused a race condition with multiple gunicorn workers.

    from .doc_generator import DEFAULT_PROMPTS
    for key, meta in DEFAULT_PROMPTS.items():
        if not DocPrompt.query.filter_by(key=key).first():
            db.session.add(DocPrompt(key=key, label=meta["label"], prompt_text=meta["text"]))

    db.session.commit()
