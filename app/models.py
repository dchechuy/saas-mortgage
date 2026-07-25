from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class Tenant(db.Model):
    """A tenant-isolated workspace. Cofficiency is the protected internal tenant;
    all other tenants are customer POC/prototype workspaces."""
    __tablename__ = "tenant"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_protected = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    role = db.Column(db.String(80), nullable=False, default="member")
    avatar = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    # Immutable home tenant, assigned at creation. No route may update this column
    # (enforced since Phase 3); correcting a user's tenant requires a controlled
    # data migration, not ordinary UI.
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
    # Remembered active tenant for Cofficiency users; ignored for external users (Phase 2 resolves active tenant).
    last_active_tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id], backref=db.backref("users", lazy="dynamic"))
    last_active_tenant = db.relationship("Tenant", foreign_keys=[last_active_tenant_id])

    @property
    def display_name(self) -> str:
        full_name = " ".join(part for part in [self.first_name, self.last_name] if part)
        return full_name or self.username

    def is_admin(self) -> bool:
        return self.role == "admin"

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Role(db.Model):
    __tablename__ = "role"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    is_system = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    permissions = db.relationship("Permission", backref="role", cascade="all, delete-orphan")

    @property
    def is_protected(self) -> bool:
        return self.name.lower() == "admin"

    def get_permission(self, page_slug: str) -> str:
        for permission in self.permissions:
            if permission.page_slug == page_slug:
                return permission.access_level
        return "no_access"

    def get_scope(self, page_slug: str) -> str:
        if self.name.lower() == "admin":
            return "all"
        for permission in self.permissions:
            if permission.page_slug == page_slug:
                return permission.scope
        return "own"


class Permission(db.Model):
    __tablename__ = "permission"

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("role.id"), nullable=False)
    page_slug = db.Column(db.String(80), nullable=False)
    access_level = db.Column(db.String(20), nullable=False, default="no_access")
    scope = db.Column(db.String(10), nullable=False, default="own")  # "own" | "all"

    __table_args__ = (
        db.UniqueConstraint("role_id", "page_slug", name="uq_role_page"),
    )


class LlmModel(db.Model):
    __tablename__ = "llm_model"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    provider = db.Column(db.String(80), nullable=False, default="Azure OpenAI")
    deployment_name = db.Column(db.String(120), nullable=False)
    endpoint_url = db.Column(db.String(255), nullable=False)
    api_key_encrypted = db.Column(db.Text, nullable=False)
    model_type = db.Column(db.String(40), nullable=False, default="chat")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = db.relationship("Tenant", backref=db.backref("llm_models", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_llm_model_tenant_name"),
    )


class Attribute(db.Model):
    __tablename__ = "attribute"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    tenant = db.relationship("Tenant", backref=db.backref("attributes", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "category", "name", name="uq_attribute_tenant_category_name"),
    )


class Integration(db.Model):
    __tablename__ = "integration"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    provider = db.Column(db.String(80), nullable=False)
    use_case = db.Column(db.String(40), nullable=False, default="AI Agents")
    description = db.Column(db.String(255), nullable=True)
    api_key_encrypted = db.Column(db.Text, nullable=True)
    base_url = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)

    tenant = db.relationship("Tenant", backref=db.backref("integrations", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_integration_tenant_name"),
    )


class ReleaseNote(db.Model):
    __tablename__ = "release_note"

    id = db.Column(db.Integer, primary_key=True)
    version_major = db.Column(db.Integer, nullable=False, default=1)
    version_minor = db.Column(db.Integer, nullable=False, default=0)
    version_patch = db.Column(db.Integer, nullable=False, default=0)
    version_string = db.Column(db.String(20), nullable=False)
    release_type = db.Column(db.String(20), nullable=False, default="minor")
    # Legacy field kept for backward compatibility
    title = db.Column(db.String(255), nullable=True)
    summary_markdown = db.Column(db.Text, nullable=True)
    # New fields (AI-generated pipeline)
    codename = db.Column(db.String(80), nullable=True)           # e.g. "Emerald Wolverine" (major only)
    raw_summary = db.Column(db.Text, nullable=True)              # changelog text fed to AI
    content_html = db.Column(db.Text, nullable=True)             # AI-generated HTML content
    status = db.Column(db.String(20), nullable=False, default="published")  # published | draft
    published_at = db.Column(db.DateTime, nullable=True)
    changelog_commit_hash = db.Column(db.String(40), nullable=True)   # git HEAD at generation time (legacy)
    changelog_snapshot    = db.Column(db.Text,        nullable=True)   # full CHANGELOG.md text at generation time
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    created_by = db.relationship("User", foreign_keys=[created_by_user_id])


class LlmRequestLog(db.Model):
    """One row per call to an LLM model. Written by whatever code makes the call."""
    __tablename__ = "llm_request_log"

    id                = db.Column(db.Integer, primary_key=True)
    tenant_id         = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
    model_id          = db.Column(db.Integer, db.ForeignKey("llm_model.id"), nullable=True)
    model_name        = db.Column(db.String(120), nullable=True)   # snapshot at call time
    use_case          = db.Column(db.String(80),  nullable=True)   # e.g. 'chat', 'adhoc'
    prompt_tokens     = db.Column(db.Integer, nullable=True)
    completion_tokens = db.Column(db.Integer, nullable=True)
    total_tokens      = db.Column(db.Integer, nullable=True)
    latency_ms        = db.Column(db.Integer, nullable=True)
    status            = db.Column(db.String(20), nullable=False, default="success")  # success | error
    error_message     = db.Column(db.Text, nullable=True)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    tenant = db.relationship("Tenant", backref=db.backref("llm_request_logs", lazy="dynamic"))
    model = db.relationship("LlmModel", backref=db.backref("request_logs", lazy="dynamic"))


class UserActivityLog(db.Model):
    """One row per significant user action. Written by activity_logger.log_activity()."""
    __tablename__ = "user_activity_log"

    id         = db.Column(db.Integer, primary_key=True)
    tenant_id  = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    action     = db.Column(db.String(120), nullable=False)   # e.g. 'user.login'
    page       = db.Column(db.String(80),  nullable=True)    # friendly page name
    ip_address = db.Column(db.String(45),  nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    tenant = db.relationship("Tenant", backref=db.backref("user_activity_logs", lazy="dynamic"))
    user = db.relationship("User", backref=db.backref("activity_logs", lazy="dynamic"))


class ApiRequestLog(db.Model):
    """One row per outbound call to an external Integration. Written by whatever code calls the API."""
    __tablename__ = "api_request_log"

    id               = db.Column(db.Integer, primary_key=True)
    tenant_id        = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
    integration_id   = db.Column(db.Integer, db.ForeignKey("integration.id"), nullable=True)
    integration_name = db.Column(db.String(120), nullable=True)  # snapshot at call time
    endpoint         = db.Column(db.String(255), nullable=True)
    method           = db.Column(db.String(10),  nullable=True)
    status_code      = db.Column(db.Integer, nullable=True)
    latency_ms       = db.Column(db.Integer, nullable=True)
    error_message    = db.Column(db.Text, nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    tenant = db.relationship("Tenant", backref=db.backref("api_request_logs", lazy="dynamic"))
    integration = db.relationship("Integration", backref=db.backref("request_logs", lazy="dynamic"))


class AiAgent(db.Model):
    """A configured AI agent that proxies to a skunkBOX agent via an Integration."""
    __tablename__ = "ai_agent"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    integration_id = db.Column(db.Integer, db.ForeignKey("integration.id"), nullable=False)
    skunkbox_agent_id = db.Column(db.Integer, nullable=False)
    avatar_filename = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = db.relationship("Tenant", backref=db.backref("ai_agents", lazy="dynamic"))
    integration = db.relationship("Integration", backref=db.backref("ai_agents", lazy="dynamic"))
    conversations = db.relationship("AgentConversation", backref="agent", lazy="dynamic")


class AgentConversation(db.Model):
    """A conversation thread between a user and an AI agent."""
    __tablename__ = "agent_conversation"

    id = db.Column(db.Integer, primary_key=True)
    # Stored explicitly (not merely inferred from user/agent) to preserve historical
    # attribution and support direct authorization checks.
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
    title = db.Column(db.String(255), nullable=True)
    ai_agent_id = db.Column(db.Integer, db.ForeignKey("ai_agent.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    skunkbox_session_id = db.Column(db.String(120), nullable=True)
    is_archived  = db.Column(db.Boolean, nullable=False, default=False)
    is_favorite  = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = db.relationship("Tenant", backref=db.backref("agent_conversations", lazy="dynamic"))
    user = db.relationship("User", backref=db.backref("agent_conversations", lazy="dynamic"))
    messages = db.relationship("AgentMessage", backref="conversation", lazy="dynamic",
                               order_by="AgentMessage.created_at", cascade="all, delete-orphan")


class AgentMessage(db.Model):
    """A single message within an AgentConversation."""
    __tablename__ = "agent_message"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("agent_conversation.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False)   # 'user' | 'assistant'
    content = db.Column(db.Text, nullable=False)
    rag_sources = db.Column(db.Text, nullable=True)   # JSON list of source dicts (assistant only)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def rag_sources_list(self):
        """Parse rag_sources JSON into a list of dicts, or empty list."""
        import json
        if not self.rag_sources:
            return []
        try:
            return json.loads(self.rag_sources)
        except Exception:
            return []


class MessageAttachment(db.Model):
    """Local mirror of attachment metadata for chat history display.
    The actual file lives on skunkBOX — we store only what we need to render chips."""
    __tablename__ = "message_attachment"

    id                     = db.Column(db.Integer, primary_key=True)
    message_id             = db.Column(db.Integer, db.ForeignKey("agent_message.id"), nullable=False)
    skunkbox_attachment_id = db.Column(db.Integer, nullable=False)
    original_filename      = db.Column(db.String(255), nullable=False)
    mime_type              = db.Column(db.String(100), nullable=False)
    file_category          = db.Column(db.String(20), nullable=False)  # 'image' | 'document'
    file_size_bytes        = db.Column(db.Integer, nullable=True)
    created_at             = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    message = db.relationship("AgentMessage", backref=db.backref("attachments", lazy="dynamic"))


class NavSection(db.Model):
    """A labelled group in the left sidebar navigation."""
    __tablename__ = "nav_section"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(80), nullable=False)
    short_name = db.Column(db.String(5),  nullable=True)   # shown when sidebar is collapsed
    sequence   = db.Column(db.Integer,    nullable=False, default=0)

    items = db.relationship(
        "NavItem", backref="section", lazy="dynamic",
        order_by="NavItem.sequence", cascade="all, delete-orphan",
    )

    @property
    def visible_items(self):
        return self.items.filter_by(is_visible=True).order_by(NavItem.sequence).all()

    @property
    def all_items(self):
        return self.items.order_by(NavItem.sequence).all()


class NavItem(db.Model):
    """A single link inside a NavSection."""
    __tablename__ = "nav_item"

    id         = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey("nav_section.id"), nullable=False)
    page_slug  = db.Column(db.String(80), nullable=False)
    sequence   = db.Column(db.Integer,   nullable=False, default=0)
    is_visible = db.Column(db.Boolean,   nullable=False, default=True)


class FeatureFlag(db.Model):
    """Application feature flags — toggled via System Config."""
    __tablename__ = "feature_flag"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)   # e.g. "conversations"
    label = db.Column(db.String(120), nullable=False)              # e.g. "Conversations"
    description = db.Column(db.String(255), nullable=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)


class TenantFeatureFlag(db.Model):
    """Per-tenant override of a FeatureFlag's global default. Absence of a row
    means the tenant uses FeatureFlag.is_enabled."""
    __tablename__ = "tenant_feature_flag"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
    feature_flag_id = db.Column(db.Integer, db.ForeignKey("feature_flag.id"), nullable=False)
    is_enabled = db.Column(db.Boolean, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = db.relationship("Tenant", backref=db.backref("feature_flag_overrides", lazy="dynamic"))
    feature_flag = db.relationship("FeatureFlag", backref=db.backref("tenant_overrides", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "feature_flag_id", name="uq_tenant_feature_flag"),
    )


class DocPrompt(db.Model):
    """Editable prompts used by the help-document generator."""
    __tablename__ = "doc_prompt"

    id          = db.Column(db.Integer, primary_key=True)
    key         = db.Column(db.String(40), unique=True, nullable=False)
    label       = db.Column(db.String(120), nullable=False)
    prompt_text = db.Column(db.Text, nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow,
                            onupdate=datetime.utcnow, nullable=False)


def next_version(release_type: str, latest: ReleaseNote | None) -> tuple[int, int, int]:
    if latest is None:
        return (1, 0, 0)

    major = latest.version_major
    minor = latest.version_minor
    patch = latest.version_patch

    if release_type == "major":
        return (major + 1, 0, 0)
    if release_type == "patch":
        return (major, minor, patch + 1)
    return (major, minor + 1, 0)
