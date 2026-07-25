"""Migration/model tests for Phase 1 — Tenant schema and safe migration.

These run the real Alembic migration against a database pre-populated with
data resembling a genuine pre-Phase-1 install (see tests/conftest.py), then
assert the historical-ownership and schema invariants required by
docs/prompts/Tenant Separation - Prompt - Phase 1 - saas-mortgage.md.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (AgentConversation, AiAgent, ApiRequestLog, Attribute,
                         Integration, LlmModel, LlmRequestLog, Tenant,
                         User, UserActivityLog)


def test_exactly_one_cofficiency_and_one_advantagefirst_tenant(app):
    tenants = Tenant.query.order_by(Tenant.slug).all()
    slugs = [t.slug for t in tenants]
    assert slugs == ["advantagefirst", "cofficiency"]


def test_cofficiency_is_protected_and_advantagefirst_is_not(app):
    cofficiency = Tenant.query.filter_by(slug="cofficiency").one()
    advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
    assert cofficiency.is_protected is True
    assert advantagefirst.is_protected is False
    assert cofficiency.is_active is True
    assert advantagefirst.is_active is True


def test_existing_admin_home_tenant_is_cofficiency(app):
    cofficiency = Tenant.query.filter_by(slug="cofficiency").one()
    admin = User.query.filter_by(username="admin").one()
    assert admin.tenant_id == cofficiency.id


def test_existing_non_admin_users_are_advantagefirst(app):
    advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
    jane = User.query.filter_by(username="jane").one()
    assert jane.tenant_id == advantagefirst.id


def test_existing_admin_remembered_tenant_is_advantagefirst(app):
    advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
    admin = User.query.filter_by(username="admin").one()
    assert admin.last_active_tenant_id == advantagefirst.id


def test_existing_tenant_owned_records_are_advantagefirst(app):
    advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()

    llm_model = LlmModel.query.filter_by(name="gpt-4").one()
    attribute = Attribute.query.filter_by(category="Customer", name="SMB").one()
    integration = Integration.query.filter_by(name="OpenAI Prod").one()
    ai_agent = AiAgent.query.filter_by(name="Helper").one()
    conversation = AgentConversation.query.filter_by(title="Test convo").one()

    assert llm_model.tenant_id == advantagefirst.id
    assert attribute.tenant_id == advantagefirst.id
    assert integration.tenant_id == advantagefirst.id
    assert ai_agent.tenant_id == advantagefirst.id
    assert conversation.tenant_id == advantagefirst.id


def test_historical_logs_are_advantagefirst_even_when_actor_is_admin(app):
    advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
    admin = User.query.filter_by(username="admin").one()

    llm_log = LlmRequestLog.query.one()
    activity_log = UserActivityLog.query.one()
    api_log = ApiRequestLog.query.one()

    # The activity log's actor is the admin user (Cofficiency's home user)...
    assert activity_log.user_id == admin.id
    # ...but the event itself still belongs to AdvantageFirst, not Cofficiency.
    assert activity_log.tenant_id == advantagefirst.id
    assert llm_log.tenant_id == advantagefirst.id
    assert api_log.tenant_id == advantagefirst.id


def test_required_tenant_columns_are_non_null(app):
    for model in (User, LlmModel, Attribute, Integration, AiAgent,
                  AgentConversation, LlmRequestLog, UserActivityLog, ApiRequestLog):
        rows = model.query.all()
        assert rows, f"expected at least one {model.__name__} row from fixture data"
        assert all(row.tenant_id is not None for row in rows), (
            f"{model.__name__} has a row with a null tenant_id"
        )

    # And the constraint is actually enforced at the DB level, not just
    # incidentally true of the fixture data.
    advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
    bad_model = LlmModel(
        tenant_id=None,
        name="no-tenant-model",
        deployment_name="x",
        endpoint_url="https://example.com",
        api_key_encrypted="enc",
    )
    db.session.add(bad_model)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_tenant_relative_uniqueness(app):
    advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
    acme = Tenant(name="Acme", slug="acme", is_active=True, is_protected=False)
    db.session.add(acme)
    db.session.commit()

    # Same natural name ("gpt-4") already exists for AdvantageFirst — a
    # different tenant reusing that name must be allowed.
    assert LlmModel.query.filter_by(tenant_id=advantagefirst.id, name="gpt-4").count() == 1
    acme_model = LlmModel(
        tenant_id=acme.id,
        name="gpt-4",
        deployment_name="acme-deploy",
        endpoint_url="https://acme.example.com",
        api_key_encrypted="enc",
    )
    db.session.add(acme_model)
    db.session.commit()  # must not raise

    # But a duplicate name within the *same* tenant must be rejected.
    duplicate = LlmModel(
        tenant_id=acme.id,
        name="gpt-4",
        deployment_name="acme-deploy-2",
        endpoint_url="https://acme.example.com",
        api_key_encrypted="enc",
    )
    db.session.add(duplicate)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_model_relationships_load_without_ambiguous_foreign_key_errors(app):
    cofficiency = Tenant.query.filter_by(slug="cofficiency").one()
    advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()

    admin = User.query.filter_by(username="admin").one()
    assert admin.tenant.id == cofficiency.id
    assert admin.last_active_tenant.id == advantagefirst.id

    ai_agent = AiAgent.query.filter_by(name="Helper").one()
    assert ai_agent.tenant.id == advantagefirst.id
    assert ai_agent.integration.name == "OpenAI Prod"

    conversation = AgentConversation.query.filter_by(title="Test convo").one()
    assert conversation.tenant.id == advantagefirst.id
    assert conversation.user.username == "admin"
    assert conversation.agent.name == "Helper"
