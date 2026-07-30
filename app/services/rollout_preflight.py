"""Read-only rollout evidence generation for Tenant Completion Phase 6."""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app

from ..extensions import db
from ..models import (
    AiAgent, ApiRequestLog, FeatureFlag, Integration, Tenant,
    TenantFeatureFlag, User,
)


def _command(*args: str) -> tuple[int, str]:
    result = subprocess.run(
        args, cwd=Path(current_app.root_path).parent,
        capture_output=True, text=True, check=False,
    )
    return result.returncode, (result.stdout or result.stderr).strip()


def build_preflight_report(environment: str, platform_inventory: str | None = None) -> str:
    """Return a Markdown evidence report without mutating rollout state."""
    generated = datetime.now(timezone.utc).isoformat()
    git_rc, git_status = _command("git", "status", "--short")
    rev_rc, revision = _command("git", "rev-parse", "HEAD")
    head_rc, heads = _command(str(Path(".venv/bin/flask")), "db", "heads")

    tenants = Tenant.query.order_by(Tenant.name).all()
    cofficiency = next((t for t in tenants if t.slug == "cofficiency"), None)
    advantagefirst = next((t for t in tenants if t.slug == "advantagefirst"), None)
    ambiguous = [t for t in tenants if not t.external_id or t.sync_status != "synced"]
    archived = [t for t in tenants if not t.is_active]
    active_credentials_configured = bool(
        current_app.config.get("SKUNKBOX_SERVICE_SECRET")
        and current_app.config.get("SKUNKBOX_BASE_URL")
    )
    ai_quality = FeatureFlag.query.filter_by(key="ai_quality").first()
    overrides = (
        TenantFeatureFlag.query.filter_by(feature_flag_id=ai_quality.id).all()
        if ai_quality else []
    )

    lines = [
        f"# Tenant Completion Phase 6 — Preflight Evidence ({environment})",
        "",
        f"- Generated (UTC): `{generated}`",
        f"- Cophy revision: `{revision if rev_rc == 0 else 'unavailable'}`",
        f"- Worktree: `{'clean' if git_rc == 0 and not git_status else 'DIRTY — no-go for deployment'}`",
        f"- Migration head command: `{'ok' if head_rc == 0 else 'failed'}` — `{heads}`",
        f"- skunkBOX URL + service secret configured: `{'yes' if active_credentials_configured else 'no'}`",
        "",
        "## Tenant registry",
        "",
        "| Tenant | UUID | Active | Sync status | Users | Agent pointers | AI Quality override |",
        "|---|---|---:|---|---:|---:|---|",
    ]
    override_by_tenant = {row.tenant_id: row.is_enabled for row in overrides}
    for tenant in tenants:
        override = override_by_tenant.get(tenant.id)
        lines.append(
            f"| {tenant.name} | `{tenant.external_id or 'MISSING'}` | "
            f"{'yes' if tenant.is_active else 'no'} | {tenant.sync_status} | "
            f"{User.query.filter_by(tenant_id=tenant.id).count()} | "
            f"{AiAgent.query.filter_by(tenant_id=tenant.id).count()} | "
            f"{'inherited' if override is None else ('enabled' if override else 'disabled')} |"
        )
    lines += [
        "",
        f"- Cofficiency UUID: `{cofficiency.external_id if cofficiency else 'MISSING'}`",
        f"- AdvantageFirst UUID: `{advantagefirst.external_id if advantagefirst else 'MISSING'}`",
        f"- Unsynced/ambiguous local tenants: `{len(ambiguous)}`",
        f"- Archived tenants: `{len(archived)}` (must fail closed in target smoke tests)",
        f"- Active AI Agent Integrations: `{Integration.query.filter_by(use_case='AI Agents', is_active=True).count()}`",
        f"- Active Documents Integrations: `{Integration.query.filter_by(use_case='Documents', is_active=True).count()}`",
        "",
        "## Management API monitoring baseline",
        "",
        f"- Local management-call audit rows: `{ApiRequestLog.query.filter_by(integration_name='skunkBOX Management API').count()}`",
        "- Secrets and request bodies are intentionally excluded from this report.",
        "",
        "## Deployment gates",
        "",
        f"- [{'x' if git_rc == 0 and not git_status else ' '}] Cophy worktree clean",
        f"- [{'x' if head_rc == 0 else ' '}] Cophy migration head resolved",
        f"- [{'x' if active_credentials_configured else ' '}] Service URL and secret configured",
        f"- [{'x' if cofficiency and advantagefirst else ' '}] Cofficiency and AdvantageFirst present",
        f"- [{'x' if not ambiguous else ' '}] No local-only or unsynced tenants",
        "- [ ] Target database backups recorded and restore-tested",
        "- [ ] Migrations rehearsed against target-data copies",
        "- [ ] skunkBOX UUIDs independently compared with this table",
        "- [ ] Archived-tenant fail-closed smoke test passed",
        "- [ ] Full suites passed on deployed revisions",
        "",
        "## Human-controlled gates (never automated)",
        "",
        "- [ ] Every proposed Shared collection has explicit Cofficiency approval",
        "- [ ] Every proposed Shared Agent has explicit Cofficiency approval",
        "- [ ] Pilot tenant and observation window are named",
        "- [ ] Pilot customer's own user completed the workflow",
        "- [ ] Go/no-go decision signed and dated",
    ]
    if platform_inventory:
        lines += [
            "",
            "## skunkBOX curation inventory",
            "",
            f"Authoritative inventory: `{platform_inventory}`",
        ]
    return "\n".join(lines) + "\n"
