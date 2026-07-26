"""Local-mirror upsert logic for skunkBOX Shared Agents (Cross-System Tenant
AI Assets PRD, Phase 6). Called from app/routes/agents.py's conversation
list on every view — same "always live, no scheduled job" philosophy
Learning Center already uses for documents/collections (app/routes/agents.py
learning_center()), rather than a separate reconciliation command.

Never touches a tenant-owned (`is_shared=False`) `AiAgent` row. Never
deletes a Shared mirror row — an Agent that's no longer visible (unshared,
archived, or the tenant lost access) is deactivated instead, so existing
conversation history keeps a valid `AiAgent` to point at.
"""
import logging

from ..extensions import db
from ..models import AiAgent, Integration

log = logging.getLogger(__name__)


def sync_shared_agents_for_tenant(tenant) -> dict:
    """Upsert local `AiAgent` mirror rows for every Cofficiency Shared Agent
    visible to `tenant`. Returns a summary dict; never raises — a skunkBOX
    outage must not break the conversations page, it should just mean
    Shared Agents don't show up (or show stale) until the next successful
    call.
    """
    summary = {"created": 0, "updated": 0, "deactivated": 0, "conflicts": [], "fetch_error": None}

    if not tenant or not tenant.external_id or tenant.sync_status != "synced":
        return summary

    integration = Integration.query.filter_by(
        tenant_id=tenant.id, use_case="AI Agents", is_active=True
    ).first()
    if not integration:
        # Nothing to attach a mirror row to — a Shared Agent still needs the
        # tenant's own credentials to actually chat (visibility is enforced
        # skunkBOX-side by tenant UUID, but the transport is still the
        # tenant's own per-tenant Integration/API key).
        return summary

    from .. import skunkbox_client
    from ..skunkbox_client import SkunkBoxClientError

    try:
        remote_page = skunkbox_client.list_agents(tenant.external_id)
    except SkunkBoxClientError as exc:
        summary["fetch_error"] = str(exc)
        log.warning("Shared agent sync: failed to fetch agent list for tenant %s: %s", tenant.id, exc)
        return summary
    except Exception as exc:
        summary["fetch_error"] = str(exc)
        log.warning("Shared agent sync: unexpected error for tenant %s: %s", tenant.id, exc)
        return summary

    remote_agents = remote_page.get("agents", [])
    shared_remote = [a for a in remote_agents if a.get("is_shared") and a.get("owner") != "self"]
    seen_ids = {a["id"] for a in shared_remote}

    for remote in shared_remote:
        existing = AiAgent.query.filter_by(tenant_id=tenant.id, skunkbox_agent_id=remote["id"]).first()
        try:
            if existing and not existing.is_shared:
                # A customer already has their own local row pointing at
                # this same skunkbox_agent_id — never silently repurpose it
                # into a Shared mirror (ambiguous ownership).
                summary["conflicts"].append({
                    "skunkbox_agent_id": remote["id"],
                    "message": f"Local agent #{existing.id} ({existing.name!r}) already uses "
                              f"skunkbox_agent_id={remote['id']}; cannot mirror the Shared Agent "
                              f"of the same id.",
                })
                continue
            if existing:
                existing.name = remote["name"]
                existing.description = remote.get("description")
                existing.is_active = bool(remote.get("is_active", True))
                db.session.commit()
                summary["updated"] += 1
            else:
                db.session.add(AiAgent(
                    tenant_id=tenant.id,
                    name=remote["name"],
                    description=remote.get("description"),
                    integration_id=integration.id,
                    skunkbox_agent_id=remote["id"],
                    is_active=bool(remote.get("is_active", True)),
                    is_shared=True,
                ))
                db.session.commit()
                summary["created"] += 1
        except Exception as exc:
            db.session.rollback()
            summary["conflicts"].append({"skunkbox_agent_id": remote["id"], "message": str(exc)})
            log.warning("Shared agent sync: failed to upsert agent %s for tenant %s: %s",
                       remote["id"], tenant.id, exc)

    # A previously-mirrored Shared Agent that's no longer visible (unshared,
    # archived) is deactivated, never deleted — existing conversations keep
    # a valid AiAgent to point at. Skipped entirely when skunkBOX returned
    # zero *total* agents (not just zero shared ones) — almost certainly a
    # transient/misconfigured response, not evidence every Shared Agent was
    # unshared at once (same reasoning as tenant_sync.run_reconciliation's
    # local_only guard).
    stale = (
        AiAgent.query.filter(
            AiAgent.tenant_id == tenant.id,
            AiAgent.is_shared.is_(True),
            AiAgent.is_active.is_(True),
            ~AiAgent.skunkbox_agent_id.in_(seen_ids),
        ).all()
        if remote_agents else []
    )
    for agent in stale:
        agent.is_active = False
        summary["deactivated"] += 1
    if stale:
        db.session.commit()

    return summary
