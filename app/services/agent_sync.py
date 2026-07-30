"""Reconcile tenant-local Agent pointers with authoritative skunkBOX Personas.

The local row remains necessary for conversations, avatars, and the
tenant's chat Integration, but skunkBOX owns Agent configuration and
lifecycle. Both tenant-owned and Cofficiency Shared Agents are synchronized;
rows are never deleted or silently converted between ownership types.
"""
import logging

from ..extensions import db
from ..models import AiAgent, Integration

log = logging.getLogger(__name__)


def sync_agents_for_tenant(tenant) -> dict:
    """Upsert pointers for every owned or Shared Agent visible to `tenant`."""
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
    visible_remote = [
        a for a in remote_agents
        if a.get("owner") == "self" or (a.get("is_shared") and a.get("owner") != "self")
    ]
    seen_ids = {a["id"] for a in visible_remote}

    for remote in visible_remote:
        remote_is_shared = bool(remote.get("is_shared") and remote.get("owner") != "self")
        existing = AiAgent.query.filter_by(tenant_id=tenant.id, skunkbox_agent_id=remote["id"]).first()
        try:
            if existing and existing.is_shared != remote_is_shared:
                summary["conflicts"].append({
                    "skunkbox_agent_id": remote["id"],
                    "message": f"Local Agent #{existing.id} has a different ownership type "
                               "than the authoritative skunkBOX Agent; it was not repurposed.",
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
                    is_shared=remote_is_shared,
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
    # a valid AiAgent to point at. Unlike tenant_sync.run_reconciliation's
    # analogous "skip on empty response" guard, an empty *visible-agents*
    # response is NOT treated as evidence of a transient/misconfigured
    # fetch: by this point list_agents() already succeeded without raising
    # (a real fetch failure returned early above), and a tenant legitimately
    # having zero visible Shared Agents is the normal starting state for
    # every tenant, not a red flag — a tenant list going to zero would be
    # (skunkBOX always has at least Cofficiency itself), so the two guards
    # are deliberately NOT symmetric.
    stale = AiAgent.query.filter(
        AiAgent.tenant_id == tenant.id,
        # Legacy tenant-owned hand-configured pointers are retained by the
        # mixed strategy until positively matched; absence from a remote
        # page is not enough to destroy their local chat availability.
        AiAgent.is_shared.is_(True),
        AiAgent.is_active.is_(True),
        ~AiAgent.skunkbox_agent_id.in_(seen_ids),
    ).all()
    for agent in stale:
        agent.is_active = False
        summary["deactivated"] += 1
    if stale:
        db.session.commit()

    return summary


# Backwards-compatible name used by conversation routes and existing tests.
sync_shared_agents_for_tenant = sync_agents_for_tenant
