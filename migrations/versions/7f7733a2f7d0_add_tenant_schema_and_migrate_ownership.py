"""add tenant schema and migrate historical ownership to advantagefirst

Revision ID: 7f7733a2f7d0
Revises: 11b469c6d972
Create Date: 2026-07-24

"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7f7733a2f7d0'
down_revision = '11b469c6d972'
branch_labels = None
depends_on = None


# Tables that directly own operational/configuration records and migrate to AdvantageFirst.
_TENANT_OWNED_TABLES = ("llm_model", "attribute", "integration", "ai_agent", "agent_conversation")
# Historical log tables — every existing row migrates to AdvantageFirst regardless of actor.
_LOG_TABLES = ("llm_request_log", "user_activity_log", "api_request_log")


def upgrade():
    # ------------------------------------------------------------------
    # 1-3. Create tenant table, seed Cofficiency (protected) and AdvantageFirst.
    # ------------------------------------------------------------------
    op.create_table(
        "tenant",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_protected", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_tenant_name"),
        sa.UniqueConstraint("slug", name="uq_tenant_slug"),
    )

    tenant_table = sa.table(
        "tenant",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("slug", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("is_protected", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )

    now = datetime.utcnow()
    op.bulk_insert(
        tenant_table,
        [
            {
                "name": "Cofficiency", "slug": "cofficiency",
                "is_active": True, "is_protected": True,
                "created_at": now, "updated_at": now,
            },
            {
                "name": "AdvantageFirst", "slug": "advantagefirst",
                "is_active": True, "is_protected": False,
                "created_at": now, "updated_at": now,
            },
        ],
    )

    conn = op.get_bind()
    cofficiency_id = conn.execute(
        sa.text("SELECT id FROM tenant WHERE slug = 'cofficiency'")
    ).scalar_one()
    advantagefirst_id = conn.execute(
        sa.text("SELECT id FROM tenant WHERE slug = 'advantagefirst'")
    ).scalar_one()

    # ------------------------------------------------------------------
    # 4. Add tenant columns as nullable.
    # ------------------------------------------------------------------
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_active_tenant_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_user_tenant_id", "tenant", ["tenant_id"], ["id"])
        batch_op.create_foreign_key(
            "fk_user_last_active_tenant_id", "tenant", ["last_active_tenant_id"], ["id"]
        )

    with op.batch_alter_table("llm_model") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_llm_model_tenant_id", "tenant", ["tenant_id"], ["id"])

    with op.batch_alter_table("attribute") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_attribute_tenant_id", "tenant", ["tenant_id"], ["id"])

    with op.batch_alter_table("integration") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_integration_tenant_id", "tenant", ["tenant_id"], ["id"])

    with op.batch_alter_table("ai_agent") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_ai_agent_tenant_id", "tenant", ["tenant_id"], ["id"])

    with op.batch_alter_table("agent_conversation") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_agent_conversation_tenant_id", "tenant", ["tenant_id"], ["id"]
        )

    with op.batch_alter_table("llm_request_log") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_llm_request_log_tenant_id", "tenant", ["tenant_id"], ["id"]
        )

    with op.batch_alter_table("user_activity_log") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_user_activity_log_tenant_id", "tenant", ["tenant_id"], ["id"]
        )

    with op.batch_alter_table("api_request_log") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_api_request_log_tenant_id", "tenant", ["tenant_id"], ["id"]
        )

    # ------------------------------------------------------------------
    # 5. Create tenant_feature_flag (per-tenant override table).
    # ------------------------------------------------------------------
    op.create_table(
        "tenant_feature_flag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("feature_flag_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["feature_flag_id"], ["feature_flag.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "feature_flag_id", name="uq_tenant_feature_flag"),
    )

    # ------------------------------------------------------------------
    # 6-7. Existing system `admin` user -> Cofficiency. Every other user -> AdvantageFirst.
    # ------------------------------------------------------------------
    conn.execute(
        sa.text("UPDATE user SET tenant_id = :tid WHERE username = 'admin'"),
        {"tid": cofficiency_id},
    )
    conn.execute(
        sa.text("UPDATE user SET tenant_id = :tid WHERE username != 'admin'"),
        {"tid": advantagefirst_id},
    )

    # ------------------------------------------------------------------
    # 8. Existing admin's remembered active tenant is AdvantageFirst.
    # ------------------------------------------------------------------
    conn.execute(
        sa.text("UPDATE user SET last_active_tenant_id = :tid WHERE username = 'admin'"),
        {"tid": advantagefirst_id},
    )

    # ------------------------------------------------------------------
    # 9. Existing tenant-owned operational/configuration records -> AdvantageFirst.
    # ------------------------------------------------------------------
    for table in _TENANT_OWNED_TABLES:
        conn.execute(sa.text(f"UPDATE {table} SET tenant_id = :tid"), {"tid": advantagefirst_id})

    # ------------------------------------------------------------------
    # 10. Existing activity/LLM/API request logs -> AdvantageFirst, regardless of actor.
    # ------------------------------------------------------------------
    for table in _LOG_TABLES:
        conn.execute(sa.text(f"UPDATE {table} SET tenant_id = :tid"), {"tid": advantagefirst_id})

    # ------------------------------------------------------------------
    # 11. Replace global uniqueness with tenant-relative uniqueness.
    #
    # llm_model.name and integration.name were declared `unique=True` with no
    # explicit constraint name, so SQLite backs them with an unnamed
    # autoindex. batch_alter_table can't `drop_constraint` a constraint that
    # has no name, so we pass `copy_from` describing the table's current real
    # shape (tenant_id now included) without that unique constraint — batch
    # mode rebuilds the table from that description instead of reflecting the
    # old unique constraint back in.
    # ------------------------------------------------------------------
    llm_model_copy_from = sa.Table(
        "llm_model", sa.MetaData(),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("deployment_name", sa.String(length=120), nullable=False),
        sa.Column("endpoint_url", sa.String(length=255), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("model_type", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], name="fk_llm_model_tenant_id"),
    )
    with op.batch_alter_table("llm_model", copy_from=llm_model_copy_from) as batch_op:
        batch_op.create_unique_constraint("uq_llm_model_tenant_name", ["tenant_id", "name"])

    integration_copy_from = sa.Table(
        "integration", sa.MetaData(),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("use_case", sa.String(length=40), nullable=False, server_default="AI Agents"),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], name="fk_integration_tenant_id"),
    )
    with op.batch_alter_table("integration", copy_from=integration_copy_from) as batch_op:
        batch_op.create_unique_constraint("uq_integration_tenant_name", ["tenant_id", "name"])

    # attribute already has a named unique constraint, so it can be dropped directly.
    with op.batch_alter_table("attribute") as batch_op:
        batch_op.drop_constraint("uq_attribute_category_name", type_="unique")
        batch_op.create_unique_constraint(
            "uq_attribute_tenant_category_name", ["tenant_id", "category", "name"]
        )

    # ------------------------------------------------------------------
    # 12. Make required tenant columns non-null.
    # ------------------------------------------------------------------
    with op.batch_alter_table("user") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("llm_model") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("attribute") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("integration") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("ai_agent") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("agent_conversation") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("llm_request_log") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("user_activity_log") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("api_request_log") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)


def downgrade():
    # Downgrade limitation: llm_model.name and integration.name were originally
    # backed by unnamed SQLite unique constraints (created via `unique=True`).
    # This downgrade restores the same uniqueness behavior under an explicit
    # name (uq_llm_model_name / uq_integration_name) instead, since Alembic's
    # batch mode cannot recreate an anonymous constraint. Structurally and
    # behaviorally equivalent; only the constraint's name differs from the
    # original schema.

    # Reverse of the non-null pass — tenant columns become nullable again.
    with op.batch_alter_table("api_request_log") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("user_activity_log") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("llm_request_log") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("agent_conversation") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("ai_agent") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("integration") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("attribute") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("llm_model") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=True)

    # Restore original tenant-relative -> global unique constraints.
    with op.batch_alter_table("attribute") as batch_op:
        batch_op.drop_constraint("uq_attribute_tenant_category_name", type_="unique")
        batch_op.create_unique_constraint("uq_attribute_category_name", ["category", "name"])

    integration_copy_from = sa.Table(
        "integration", sa.MetaData(),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("use_case", sa.String(length=40), nullable=False, server_default="AI Agents"),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], name="fk_integration_tenant_id"),
    )
    with op.batch_alter_table("integration", copy_from=integration_copy_from) as batch_op:
        batch_op.create_unique_constraint("uq_integration_name", ["name"])

    llm_model_copy_from = sa.Table(
        "llm_model", sa.MetaData(),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("deployment_name", sa.String(length=120), nullable=False),
        sa.Column("endpoint_url", sa.String(length=255), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("model_type", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], name="fk_llm_model_tenant_id"),
    )
    with op.batch_alter_table("llm_model", copy_from=llm_model_copy_from) as batch_op:
        batch_op.create_unique_constraint("uq_llm_model_name", ["name"])

    op.drop_table("tenant_feature_flag")

    with op.batch_alter_table("api_request_log") as batch_op:
        batch_op.drop_constraint("fk_api_request_log_tenant_id", type_="foreignkey")
        batch_op.drop_column("tenant_id")

    with op.batch_alter_table("user_activity_log") as batch_op:
        batch_op.drop_constraint("fk_user_activity_log_tenant_id", type_="foreignkey")
        batch_op.drop_column("tenant_id")

    with op.batch_alter_table("llm_request_log") as batch_op:
        batch_op.drop_constraint("fk_llm_request_log_tenant_id", type_="foreignkey")
        batch_op.drop_column("tenant_id")

    with op.batch_alter_table("agent_conversation") as batch_op:
        batch_op.drop_constraint("fk_agent_conversation_tenant_id", type_="foreignkey")
        batch_op.drop_column("tenant_id")

    with op.batch_alter_table("ai_agent") as batch_op:
        batch_op.drop_constraint("fk_ai_agent_tenant_id", type_="foreignkey")
        batch_op.drop_column("tenant_id")

    with op.batch_alter_table("integration") as batch_op:
        batch_op.drop_constraint("fk_integration_tenant_id", type_="foreignkey")
        batch_op.drop_column("tenant_id")

    with op.batch_alter_table("attribute") as batch_op:
        batch_op.drop_constraint("fk_attribute_tenant_id", type_="foreignkey")
        batch_op.drop_column("tenant_id")

    with op.batch_alter_table("llm_model") as batch_op:
        batch_op.drop_constraint("fk_llm_model_tenant_id", type_="foreignkey")
        batch_op.drop_column("tenant_id")

    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_constraint("fk_user_last_active_tenant_id", type_="foreignkey")
        batch_op.drop_constraint("fk_user_tenant_id", type_="foreignkey")
        batch_op.drop_column("last_active_tenant_id")
        batch_op.drop_column("tenant_id")

    op.drop_table("tenant")
