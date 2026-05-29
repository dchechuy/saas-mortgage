import os
import uuid

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..access import permission_required, user_has_access
from ..activity_logger import log_activity
from ..crypto import encrypt_value
from ..extensions import db
from ..models import AgentConversation, AiAgent, Attribute, DocPrompt, FeatureFlag, Integration, LlmModel, NavItem, NavSection
from ..page_registry import NAV_ITEMS

_ALLOWED_IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _save_agent_avatar(file_storage) -> str | None:
    if not file_storage or not file_storage.filename:
        return None
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in _ALLOWED_IMG_EXTS:
        return None
    filename = f"{uuid.uuid4().hex}{ext}"
    folder = current_app.config["AGENT_AVATAR_UPLOAD_FOLDER"]
    file_storage.save(os.path.join(folder, filename))
    return filename

models_bp = Blueprint("models", __name__, url_prefix="/models")


def _redirect_to_system_config(anchor: str = "integrations"):
    return redirect(f"{url_for('models.list_models')}#{anchor}")


@models_bp.route("/")
@login_required
def list_models():
    can_view_models = user_has_access("models", "view")
    can_view_attributes = user_has_access("attributes", "view")
    can_view_integrations = user_has_access("integrations", "view")
    can_view_agents = user_has_access("agents", "view")
    can_view_flags = user_has_access("models", "view")  # same permission gate as LLM Models

    if not any([can_view_models, can_view_attributes, can_view_integrations, can_view_agents]):
        flash("You do not have permission to access this page.", "error")
        return redirect(url_for("agents.list_conversations"))

    all_integrations = Integration.query.order_by(
        Integration.category, Integration.provider, Integration.name
    ).all() if (can_view_integrations or can_view_agents) else []

    # Build sections data for the Sections tab
    db_sections = NavSection.query.order_by(NavSection.sequence).all()
    sections_for_template = []
    all_slugs_in_sections = set()
    for sec in db_sections:
        items = []
        for ni in sec.all_items:
            reg = NAV_ITEMS.get(ni.page_slug)
            if reg:
                items.append({
                    "id":         ni.id,
                    "slug":       ni.page_slug,
                    "label":      reg["label"],
                    "is_visible": ni.is_visible,
                })
                all_slugs_in_sections.add(ni.page_slug)
        sections_for_template.append({
            "id":         sec.id,
            "name":       sec.name,
            "short_name": sec.short_name or "",
            "items":      items,
        })
    unassigned_pages = [
        {"slug": slug, "label": meta["label"]}
        for slug, meta in NAV_ITEMS.items()
        if slug not in all_slugs_in_sections
    ]

    from ..doc_generator import DEFAULT_PROMPTS

    return render_template(
        "models/list.html",
        llm_models=LlmModel.query.order_by(LlmModel.name).all() if can_view_models else [],
        attributes=Attribute.query.order_by(Attribute.category, Attribute.name).all() if can_view_attributes else [],
        integrations=all_integrations if can_view_integrations else [],
        ai_agents=AiAgent.query.order_by(AiAgent.name).all() if can_view_agents else [],
        all_integrations=all_integrations,
        feature_flags=FeatureFlag.query.order_by(FeatureFlag.id).all() if can_view_flags else [],
        can_view_models=can_view_models,
        can_view_attributes=can_view_attributes,
        can_view_integrations=can_view_integrations,
        can_view_agents=can_view_agents,
        can_view_flags=can_view_flags,
        sections=sections_for_template,
        unassigned_pages=unassigned_pages,
        doc_prompts=DocPrompt.query.order_by(DocPrompt.id).all(),
        default_prompts=DEFAULT_PROMPTS,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "System Config", "url": url_for("models.list_models")},
            {"label": "LLM Models", "url": None},
        ],
    )


@models_bp.route("/flags/<int:flag_id>/toggle", methods=["POST"])
@login_required
@permission_required("models", "edit")
def toggle_flag(flag_id):
    flag = db.get_or_404(FeatureFlag, flag_id)
    # Checkbox is present in form data when checked, absent when unchecked
    flag.is_enabled = bool(request.form.get("is_enabled"))
    db.session.commit()
    log_activity(current_user, "flag.toggled", page="System Config")
    return redirect(_redirect_to_system_config("flags").location)


@models_bp.route("/llm/add", methods=["POST"])
@login_required
@permission_required("models", "edit")
def add_llm_model():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Model name is required.", "error")
        return _redirect_to_system_config()

    if LlmModel.query.filter_by(name=name).first():
        flash(f"Model '{name}' already exists.", "error")
        return _redirect_to_system_config()

    make_default = request.form.get("is_default") == "1"
    if make_default:
        LlmModel.query.update({"is_default": False})

    model = LlmModel(
        name=name,
        provider=request.form.get("provider", "Azure OpenAI").strip() or "Azure OpenAI",
        deployment_name=request.form.get("deployment_name", "").strip(),
        endpoint_url=request.form.get("endpoint_url", "").strip(),
        api_key_encrypted=encrypt_value(request.form.get("api_key", "").strip()),
        model_type=request.form.get("model_type", "chat").strip() or "chat",
        is_active=request.form.get("is_active", "1") == "1",
        is_default=make_default,
    )
    db.session.add(model)
    db.session.commit()
    log_activity(current_user, "llm.created", page="System Config")
    flash(f"Model '{name}' added.", "success")
    return _redirect_to_system_config()


@models_bp.route("/llm/<int:model_id>/update", methods=["POST"])
@login_required
@permission_required("models", "edit")
def update_llm_model(model_id):
    model = db.get_or_404(LlmModel, model_id)
    name = request.form.get("name", "").strip()
    if not name:
        flash("Model name is required.", "error")
        return _redirect_to_system_config()

    duplicate = LlmModel.query.filter(LlmModel.name == name, LlmModel.id != model.id).first()
    if duplicate:
        flash(f"Model '{name}' already exists.", "error")
        return _redirect_to_system_config()

    make_default = request.form.get("is_default") == "1"
    if make_default:
        LlmModel.query.update({"is_default": False})

    model.name = name
    model.provider = request.form.get("provider", "Azure OpenAI").strip() or "Azure OpenAI"
    model.deployment_name = request.form.get("deployment_name", "").strip()
    model.endpoint_url = request.form.get("endpoint_url", "").strip()
    model.model_type = request.form.get("model_type", "chat").strip() or "chat"
    model.is_active = request.form.get("is_active") == "1"
    model.is_default = make_default

    api_key = request.form.get("api_key", "").strip()
    if api_key:
        model.api_key_encrypted = encrypt_value(api_key)

    db.session.commit()
    log_activity(current_user, "llm.updated", page="System Config")
    flash(f"Model '{model.name}' updated.", "success")
    return _redirect_to_system_config()


@models_bp.route("/llm/<int:model_id>/toggle", methods=["POST"])
@login_required
@permission_required("models", "edit")
def toggle_llm_model(model_id):
    model = db.get_or_404(LlmModel, model_id)
    model.is_active = not model.is_active
    db.session.commit()
    state = "activated" if model.is_active else "deactivated"
    log_activity(current_user, f"llm.{state}", page="System Config")
    flash(f"Model '{model.name}' {state}.", "success")
    return _redirect_to_system_config("integrations")


@models_bp.route("/attributes/batch-save", methods=["POST"])
@login_required
@permission_required("attributes", "edit")
def batch_save_attributes():
    data = request.get_json(force=True) or {}
    category = (data.get("category") or "").strip()
    values = data.get("values") or []
    deleted_ids = data.get("deleted_ids") or []

    if not category:
        return jsonify({"success": False, "error": "Category name is required."})

    for attr_id in deleted_ids:
        attr = db.session.get(Attribute, int(attr_id))
        if attr and attr.category == category:
            db.session.delete(attr)

    for v in values:
        name = (v.get("name") or "").strip()
        if not name:
            continue
        is_active = bool(v.get("is_active", True))
        attr_id = v.get("id")
        if attr_id:
            attr = db.session.get(Attribute, int(attr_id))
            if attr and attr.category == category:
                attr.name = name
                attr.is_active = is_active
        else:
            if not Attribute.query.filter_by(category=category, name=name).first():
                db.session.add(Attribute(category=category, name=name))

    try:
        db.session.commit()
        log_activity(current_user, "attribute.saved", page="System Config")
        return jsonify({"success": True})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)})


@models_bp.route("/integrations/add", methods=["POST"])
@login_required
@permission_required("integrations", "edit")
def add_integration():
    name = request.form.get("name", "").strip()
    provider = request.form.get("provider", "").strip()
    category = request.form.get("category", "").strip()
    if not name or not provider or not category:
        flash("Integration name, provider, and category are required.", "error")
        return _redirect_to_system_config("apis")

    if Integration.query.filter_by(name=name).first():
        flash(f"Integration '{name}' already exists.", "error")
        return _redirect_to_system_config("apis")

    integration = Integration(
        name=name,
        provider=provider,
        category=category,
        use_case=request.form.get("use_case", "AI Agents").strip() or "AI Agents",
        description=request.form.get("description", "").strip() or None,
        base_url=request.form.get("base_url", "").strip() or None,
        is_active=request.form.get("is_active", "1") == "1",
    )
    api_key = request.form.get("api_key", "").strip()
    if api_key:
        integration.api_key_encrypted = encrypt_value(api_key)

    db.session.add(integration)
    db.session.commit()
    log_activity(current_user, "integration.created", page="System Config")
    flash(f"Integration '{integration.provider}' added.", "success")
    return _redirect_to_system_config("apis")


@models_bp.route("/integrations/<int:integration_id>/save", methods=["POST"])
@login_required
@permission_required("integrations", "edit")
def save_integration(integration_id):
    integration = db.get_or_404(Integration, integration_id)

    name = request.form.get("name", "").strip()
    provider = request.form.get("provider", "").strip()
    category = request.form.get("category", "").strip()
    if not name or not provider or not category:
        flash("Integration name, provider, and category are required.", "error")
        return _redirect_to_system_config("apis")

    duplicate = Integration.query.filter(Integration.name == name, Integration.id != integration.id).first()
    if duplicate:
        flash(f"Integration '{name}' already exists.", "error")
        return _redirect_to_system_config("apis")

    integration.name = name
    integration.provider = provider
    integration.category = category
    integration.use_case = request.form.get("use_case", "AI Agents").strip() or "AI Agents"
    integration.description = request.form.get("description", "").strip() or None
    integration.base_url = request.form.get("base_url", "").strip() or None
    integration.is_active = request.form.get("is_active") == "1"

    api_key = request.form.get("api_key", "").strip()
    if api_key:
        integration.api_key_encrypted = encrypt_value(api_key)

    db.session.commit()
    log_activity(current_user, "integration.updated", page="System Config")
    flash(f"Integration '{integration.provider}' saved.", "success")
    return _redirect_to_system_config("apis")


@models_bp.route("/agents/add", methods=["POST"])
@login_required
@permission_required("agents", "edit")
def add_agent():
    name = request.form.get("name", "").strip()
    integration_id = request.form.get("integration_id", "").strip()
    skunkbox_agent_id_raw = request.form.get("skunkbox_agent_id", "").strip()
    if not name or not integration_id or not skunkbox_agent_id_raw:
        flash("Name, integration, and skunkBOX agent ID are required.", "error")
        return _redirect_to_system_config("agents")
    try:
        skunkbox_agent_id = int(skunkbox_agent_id_raw)
    except ValueError:
        flash("skunkBOX agent ID must be an integer.", "error")
        return _redirect_to_system_config("agents")

    avatar_filename = _save_agent_avatar(request.files.get("avatar"))
    agent = AiAgent(
        name=name,
        description=request.form.get("description", "").strip() or None,
        integration_id=int(integration_id),
        skunkbox_agent_id=skunkbox_agent_id,
        avatar_filename=avatar_filename,
        is_active=request.form.get("is_active", "1") == "1",
    )
    db.session.add(agent)
    db.session.commit()
    log_activity(current_user, "agent.created", page="System Config")
    flash(f"Agent '{name}' added.", "success")
    return _redirect_to_system_config("agents")


@models_bp.route("/agents/<int:agent_id>/save", methods=["POST"])
@login_required
@permission_required("agents", "edit")
def save_agent(agent_id):
    agent = db.get_or_404(AiAgent, agent_id)
    name = request.form.get("name", "").strip()
    integration_id = request.form.get("integration_id", "").strip()
    skunkbox_agent_id_raw = request.form.get("skunkbox_agent_id", "").strip()
    if not name or not integration_id or not skunkbox_agent_id_raw:
        flash("Name, integration, and skunkBOX agent ID are required.", "error")
        return _redirect_to_system_config("agents")
    try:
        skunkbox_agent_id = int(skunkbox_agent_id_raw)
    except ValueError:
        flash("skunkBOX agent ID must be an integer.", "error")
        return _redirect_to_system_config("agents")

    new_avatar = _save_agent_avatar(request.files.get("avatar"))
    agent.name = name
    agent.description = request.form.get("description", "").strip() or None
    agent.integration_id = int(integration_id)
    agent.skunkbox_agent_id = skunkbox_agent_id
    agent.is_active = request.form.get("is_active") == "1"
    if new_avatar:
        agent.avatar_filename = new_avatar

    db.session.commit()
    log_activity(current_user, "agent.updated", page="System Config")
    flash(f"Agent '{agent.name}' saved.", "success")
    return _redirect_to_system_config("agents")


@models_bp.route("/agents/<int:agent_id>/toggle", methods=["POST"])
@login_required
@permission_required("agents", "edit")
def toggle_agent(agent_id):
    agent = db.get_or_404(AiAgent, agent_id)
    agent.is_active = not agent.is_active

    if not agent.is_active:
        # Archive all active conversations for this agent
        archived = (
            AgentConversation.query
            .filter_by(ai_agent_id=agent.id, is_archived=False)
            .update({"is_archived": True}, synchronize_session="fetch")
        )
    else:
        archived = 0

    db.session.commit()
    state = "activated" if agent.is_active else "deactivated"
    log_activity(current_user, f"agent.{state}", page="System Config")
    msg = f"Agent '{agent.name}' {state}."
    if archived:
        msg += f" {archived} conversation{'s' if archived != 1 else ''} archived."
    flash(msg, "success")
    return _redirect_to_system_config("agents")


# ─────────────────────────────────────────────────────────────────────────────
# Nav Sections — save full layout (POST JSON)
# ─────────────────────────────────────────────────────────────────────────────

@models_bp.route("/sections/save", methods=["POST"])
@login_required
@permission_required("attributes", "edit")
def save_sections():
    """Receive the full sections+items layout as JSON and rebuild the DB."""
    import json as _json
    data = request.get_json(force=True) or []

    try:
        # Delete items first, then sections (bulk delete bypasses ORM cascade)
        NavItem.query.delete()
        NavSection.query.delete()
        db.session.flush()

        for seq, sec in enumerate(data, start=1):
            section = NavSection(
                name=sec.get("name", "").strip() or "Section",
                short_name=(sec.get("short_name") or "")[:5].strip() or None,
                sequence=seq,
            )
            db.session.add(section)
            db.session.flush()
            for item_seq, item in enumerate(sec.get("items", []), start=1):
                slug = item.get("slug", "").strip()
                if slug and slug in NAV_ITEMS:
                    db.session.add(NavItem(
                        section_id=section.id,
                        page_slug=slug,
                        sequence=item_seq,
                        is_visible=bool(item.get("is_visible", True)),
                    ))

        db.session.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Help Prompts — Option 1 (System Config direct edit)
# ─────────────────────────────────────────────────────────────────────────────

@models_bp.route("/doc-prompts/<key>/save", methods=["POST"])
@login_required
@permission_required("models", "edit")
def save_doc_prompt(key):
    from ..doc_generator import DEFAULT_PROMPTS
    if key not in DEFAULT_PROMPTS:
        flash(f"Unknown prompt key: {key}", "error")
        return _redirect_to_system_config("help-prompts")

    prompt_text = request.form.get("prompt_text", "").strip()
    if not prompt_text:
        flash("Prompt text cannot be empty.", "error")
        return _redirect_to_system_config("help-prompts")

    row = DocPrompt.query.filter_by(key=key).first()
    if row:
        row.prompt_text = prompt_text
    else:
        db.session.add(DocPrompt(
            key=key, label=DEFAULT_PROMPTS[key]["label"], prompt_text=prompt_text
        ))
    db.session.commit()
    log_activity(current_user, "doc_prompt.saved", page="System Config")
    flash(f"'{DEFAULT_PROMPTS[key]['label']}' prompt saved.", "success")
    return _redirect_to_system_config("help-prompts")


@models_bp.route("/doc-prompts/<key>/reset", methods=["POST"])
@login_required
@permission_required("models", "edit")
def reset_doc_prompt(key):
    from ..doc_generator import DEFAULT_PROMPTS
    if key not in DEFAULT_PROMPTS:
        flash(f"Unknown prompt key: {key}", "error")
        return _redirect_to_system_config("help-prompts")

    row = DocPrompt.query.filter_by(key=key).first()
    if row:
        row.prompt_text = DEFAULT_PROMPTS[key]["text"]
    else:
        db.session.add(DocPrompt(
            key=key, label=DEFAULT_PROMPTS[key]["label"],
            prompt_text=DEFAULT_PROMPTS[key]["text"]
        ))
    db.session.commit()
    log_activity(current_user, "doc_prompt.reset", page="System Config")
    flash(f"'{DEFAULT_PROMPTS[key]['label']}' reset to default.", "success")
    return _redirect_to_system_config("help-prompts")
