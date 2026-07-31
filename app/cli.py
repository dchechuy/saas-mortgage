"""Flask CLI commands. Registered from create_app() via register_cli(app)."""
import logging

import click
from pathlib import Path


def register_cli(app):
    @app.cli.command("correct-tenant-deployment")
    @click.option("--dry-run", is_flag=True, help="Print the correction plan without writing.")
    @click.option("--apply", "apply_changes", is_flag=True, help="Apply the validated correction.")
    @click.option("--cofficiency-uuid", required=True, help="Authoritative skunkBOX UUID.")
    @click.option("--advantagefirst-uuid", required=True, help="Authoritative skunkBOX UUID.")
    def correct_tenant_deployment_command(
        dry_run, apply_changes, cofficiency_uuid, advantagefirst_uuid
    ):
        """Correct user home tenants and the two seeded tenant UUID mirrors."""
        from .services.tenant_correction import (
            TenantCorrectionError, apply_tenant_correction,
            build_tenant_correction_plan,
        )

        if dry_run == apply_changes:
            raise click.UsageError("Choose exactly one of --dry-run or --apply.")
        try:
            plan = build_tenant_correction_plan(
                cofficiency_uuid, advantagefirst_uuid
            )
        except TenantCorrectionError as exc:
            raise click.ClickException(str(exc)) from exc

        click.echo(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
        click.echo(f"Before user counts: {plan['before_user_counts']}")
        click.echo(f"Projected user counts: {plan['projected_user_counts']}")
        click.echo(
            "Tenant UUIDs: "
            f"Cofficiency {plan['cofficiency'].external_id} -> {plan['cofficiency_uuid']}; "
            f"AdvantageFirst {plan['advantagefirst'].external_id} -> "
            f"{plan['advantagefirst_uuid']}"
        )
        click.echo(f"User changes ({len(plan['user_changes'])}):")
        for change in plan["user_changes"]:
            click.echo(
                f"  #{change.user_id} {change.username} <{change.email}>: "
                f"{change.from_tenant} -> {change.to_tenant}; "
                f"last active -> {change.last_active_tenant or 'none'}"
            )
        click.echo(
            "Historical log rows (ownership preserved): "
            + ", ".join(
                f"{name}={len(rows)}" for name, rows in plan["log_snapshot"].items()
            )
        )
        if dry_run:
            click.echo("No changes written.")
            return

        result = apply_tenant_correction(plan)
        click.echo(f"After user counts: {result['after_user_counts']}")
        click.echo(
            "Historical log rows after: "
            + ", ".join(
                f"{name}={count}"
                for name, count in result["historical_log_rows"].items()
            )
        )
        click.echo(
            "Applied successfully. Both corrected tenant mirrors are now "
            "unsynced; configure the service credential and run sync-tenants."
        )

    @app.cli.command("tenant-rollout-preflight")
    @click.option("--environment", required=True, help="Target environment label.")
    @click.option("--output", required=True, type=click.Path(dir_okay=False, path_type=Path))
    @click.option("--platform-inventory", type=click.Path(dir_okay=False, path_type=Path))
    def tenant_rollout_preflight_command(environment, output, platform_inventory):
        """Generate read-only Phase 6 rollout evidence; never enables or shares."""
        from .services.rollout_preflight import build_preflight_report

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            build_preflight_report(
                environment,
                str(platform_inventory) if platform_inventory else None,
            ),
            encoding="utf-8",
        )
        click.echo(f"Wrote preflight evidence to {output}")

    @app.cli.command("sync-tenants")
    def sync_tenants_command():
        """Reconcile the local tenant mirror against skunkBOX's authoritative
        registry. Safe to run repeatedly (upsert, never deletes) — suitable
        for a scheduled cron/systemd timer alongside the in-app "Sync with
        skunkBOX" button (app/routes/tenants.py:sync_tenants), which calls
        the exact same app.services.tenant_sync.run_reconciliation().
        """
        from .services.tenant_sync import run_reconciliation

        logger = logging.getLogger("sync_tenants")
        summary = run_reconciliation(logger=logger)

        if summary["fetch_error"]:
            click.echo(f"FAILED: could not reach skunkBOX — {summary['fetch_error']}")
            raise SystemExit(1)

        click.echo(f"Created: {summary['created']}")
        click.echo(f"Updated: {summary['updated']}")
        if summary["conflicts"]:
            click.echo(f"Conflicts ({len(summary['conflicts'])}) — needs manual review:")
            for c in summary["conflicts"]:
                click.echo(f"  - {c['name']} ({c['external_id']}): {c['message']}")
        if summary["missing_from_skunkbox"]:
            click.echo(f"Local tenants not returned by skunkBOX this round "
                      f"({len(summary['missing_from_skunkbox'])}), flagged sync_status=error:")
            for external_id in summary["missing_from_skunkbox"]:
                click.echo(f"  - {external_id}")
        if summary["conflicts"] or summary["missing_from_skunkbox"]:
            raise SystemExit(2)
