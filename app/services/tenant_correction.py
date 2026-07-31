"""Controlled one-off correction for the deployed tenant classification.

This is intentionally explicit and operator-driven. It does not infer
skunkBOX UUIDs or contact the network, and it never modifies historical
activity/request log ownership.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from uuid import UUID, uuid4

from ..extensions import db
from ..models import ApiRequestLog, LlmRequestLog, Tenant, User, UserActivityLog


class TenantCorrectionError(Exception):
    pass


@dataclass(frozen=True)
class UserChange:
    user_id: int
    username: str
    email: str
    from_tenant: str
    to_tenant: str
    last_active_tenant: str | None


def _canonical_uuid(value: str, label: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise TenantCorrectionError(f"{label} must be a valid UUID.") from exc


def _exact_tenant(slug: str) -> Tenant:
    rows = Tenant.query.filter_by(slug=slug).all()
    if len(rows) != 1:
        raise TenantCorrectionError(
            f"Expected exactly one tenant with slug {slug!r}; found {len(rows)}."
        )
    return rows[0]


def _user_counts() -> dict[str, int]:
    return dict(sorted(Counter(
        user.tenant.slug if user.tenant else "missing"
        for user in User.query.order_by(User.id).all()
    ).items()))


def _log_snapshot() -> dict[str, tuple[tuple[int, int], ...]]:
    """Capture exact immutable event ownership, not merely aggregate counts."""
    return {
        "user_activity_log": tuple(
            db.session.query(UserActivityLog.id, UserActivityLog.tenant_id)
            .order_by(UserActivityLog.id).all()
        ),
        "llm_request_log": tuple(
            db.session.query(LlmRequestLog.id, LlmRequestLog.tenant_id)
            .order_by(LlmRequestLog.id).all()
        ),
        "api_request_log": tuple(
            db.session.query(ApiRequestLog.id, ApiRequestLog.tenant_id)
            .order_by(ApiRequestLog.id).all()
        ),
    }


def build_tenant_correction_plan(
    cofficiency_uuid: str, advantagefirst_uuid: str
) -> dict:
    cofficiency = _exact_tenant("cofficiency")
    advantagefirst = _exact_tenant("advantagefirst")
    if cofficiency.id == advantagefirst.id:
        raise TenantCorrectionError("Cofficiency and AdvantageFirst resolve to the same row.")

    coff_uuid = _canonical_uuid(cofficiency_uuid, "Cofficiency UUID")
    advantage_uuid = _canonical_uuid(advantagefirst_uuid, "AdvantageFirst UUID")
    if coff_uuid == advantage_uuid:
        raise TenantCorrectionError("The two authoritative tenant UUIDs must be different.")

    collisions = Tenant.query.filter(
        Tenant.external_id.in_([coff_uuid, advantage_uuid]),
        ~Tenant.id.in_([cofficiency.id, advantagefirst.id]),
    ).all()
    if collisions:
        names = ", ".join(f"{row.name} (#{row.id})" for row in collisions)
        raise TenantCorrectionError(
            f"An authoritative UUID is already assigned to another local tenant: {names}."
        )

    changes = []
    projected = Counter()
    for user in User.query.order_by(User.id).all():
        email = (user.email or "").strip().lower()
        target = advantagefirst if email.endswith("@advantage1st.com") else cofficiency
        projected[target.slug] += 1
        target_last_active = (
            advantagefirst if target.id == cofficiency.id and user.tenant_id != cofficiency.id
            else None
        )
        if user.tenant_id != target.id:
            changes.append(UserChange(
                user_id=user.id,
                username=user.username,
                email=user.email or "",
                from_tenant=user.tenant.slug if user.tenant else "missing",
                to_tenant=target.slug,
                last_active_tenant=target_last_active.slug if target_last_active else None,
            ))

    return {
        "cofficiency": cofficiency,
        "advantagefirst": advantagefirst,
        "cofficiency_uuid": coff_uuid,
        "advantagefirst_uuid": advantage_uuid,
        "user_changes": changes,
        "before_user_counts": _user_counts(),
        "projected_user_counts": dict(sorted(projected.items())),
        "log_snapshot": _log_snapshot(),
    }


def apply_tenant_correction(plan: dict) -> dict:
    cofficiency = plan["cofficiency"]
    advantagefirst = plan["advantagefirst"]
    change_by_id = {change.user_id: change for change in plan["user_changes"]}

    try:
        # Temporary valid UUIDs make a swap safe while preserving the
        # NOT-NULL/UNIQUE constraints throughout the transaction.
        cofficiency.external_id = str(uuid4())
        advantagefirst.external_id = str(uuid4())
        db.session.flush()
        cofficiency.external_id = plan["cofficiency_uuid"]
        advantagefirst.external_id = plan["advantagefirst_uuid"]
        for tenant in (cofficiency, advantagefirst):
            tenant.sync_status = "unsynced"
            tenant.last_synced_at = None

        for user_id, change in change_by_id.items():
            user = db.session.get(User, user_id)
            if change.to_tenant == "cofficiency":
                user.tenant_id = cofficiency.id
                user.last_active_tenant_id = advantagefirst.id
            else:
                user.tenant_id = advantagefirst.id
                user.last_active_tenant_id = None

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    after_logs = _log_snapshot()
    if after_logs != plan["log_snapshot"]:
        # This should be structurally impossible because the command never
        # writes log rows. Fail loudly if a future refactor changes that.
        raise TenantCorrectionError(
            "Historical log ownership changed unexpectedly; restore the backup."
        )

    return {
        "after_user_counts": _user_counts(),
        "historical_log_rows": {
            name: len(rows) for name, rows in after_logs.items()
        },
    }
