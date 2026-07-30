"""Flask CLI commands. Registered from create_app() via register_cli(app)."""
import logging

import click
from pathlib import Path


def register_cli(app):
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
