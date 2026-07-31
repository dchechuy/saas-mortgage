from app.extensions import db
from app.models import ApiRequestLog, LlmRequestLog, Tenant, User, UserActivityLog

from .conftest import create_user


COFF_UUID = "4525fa19-e0d2-4b02-a6e4-2f8fdcceaf57"
ADV_UUID = "0f259057-3333-4d7e-9fde-54107799869b"


def _args(mode):
    return [
        "correct-tenant-deployment", mode,
        "--cofficiency-uuid", COFF_UUID,
        "--advantagefirst-uuid", ADV_UUID,
    ]


def _log_ownership():
    return {
        "activity": UserActivityLog.query.with_entities(
            UserActivityLog.id, UserActivityLog.tenant_id
        ).order_by(UserActivityLog.id).all(),
        "llm": LlmRequestLog.query.with_entities(
            LlmRequestLog.id, LlmRequestLog.tenant_id
        ).order_by(LlmRequestLog.id).all(),
        "api": ApiRequestLog.query.with_entities(
            ApiRequestLog.id, ApiRequestLog.tenant_id
        ).order_by(ApiRequestLog.id).all(),
    }


def test_correction_dry_run_and_apply_preserve_historical_logs(full_app):
    with full_app.app_context():
        cofficiency = Tenant.query.filter_by(slug="cofficiency").one()
        advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
        create_user(full_app, "internal_person", advantagefirst.id, role="admin")
        create_user(full_app, "customer_person", advantagefirst.id, role="admin")
        internal = User.query.filter_by(username="internal_person").one()
        customer = User.query.filter_by(username="customer_person").one()
        internal.email = "person@gmail.com"
        customer.email = "person@Advantage1st.com"
        db.session.commit()
        before_logs = _log_ownership()
        before_internal_tenant = internal.tenant_id

    runner = full_app.test_cli_runner()
    dry = runner.invoke(args=_args("--dry-run"))
    assert dry.exit_code == 0, dry.output
    assert "No changes written." in dry.output
    assert "SKUNKBOX_SERVICE_SECRET" not in dry.output
    with full_app.app_context():
        assert User.query.filter_by(username="internal_person").one().tenant_id == before_internal_tenant
        assert _log_ownership() == before_logs

    applied = runner.invoke(args=_args("--apply"))
    assert applied.exit_code == 0, applied.output
    assert "Applied successfully" in applied.output
    with full_app.app_context():
        cofficiency = Tenant.query.filter_by(slug="cofficiency").one()
        advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
        internal = User.query.filter_by(username="internal_person").one()
        customer = User.query.filter_by(username="customer_person").one()
        assert internal.tenant_id == cofficiency.id
        assert internal.last_active_tenant_id == advantagefirst.id
        assert customer.tenant_id == advantagefirst.id
        assert customer.last_active_tenant_id is None
        assert cofficiency.external_id == COFF_UUID
        assert advantagefirst.external_id == ADV_UUID
        assert cofficiency.sync_status == advantagefirst.sync_status == "unsynced"
        assert _log_ownership() == before_logs


def test_correction_requires_exactly_one_mode_and_expected_tenants(full_app):
    runner = full_app.test_cli_runner()
    neither = runner.invoke(args=[
        "correct-tenant-deployment",
        "--cofficiency-uuid", COFF_UUID,
        "--advantagefirst-uuid", ADV_UUID,
    ])
    both = runner.invoke(args=[
        "correct-tenant-deployment", "--dry-run", "--apply",
        "--cofficiency-uuid", COFF_UUID,
        "--advantagefirst-uuid", ADV_UUID,
    ])
    assert neither.exit_code != 0
    assert both.exit_code != 0

    with full_app.app_context():
        tenant = Tenant.query.filter_by(slug="cofficiency").one()
        tenant.slug = "temporarily-missing"
        db.session.commit()
    try:
        missing = runner.invoke(args=_args("--dry-run"))
        assert missing.exit_code != 0
        assert "Expected exactly one tenant" in missing.output
    finally:
        with full_app.app_context():
            tenant = Tenant.query.filter_by(slug="temporarily-missing").one()
            tenant.slug = "cofficiency"
            db.session.commit()
