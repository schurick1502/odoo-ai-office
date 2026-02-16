"""Bridge sync: transfers approved DocumentFlow jobs to Odoo AI Office cases."""

import asyncio
import logging
import sys

from ..docflow.client import DocFlowClient
from ..odoo_bridge.client import OdooAiOfficeClient
from .config import BridgeConfig
from .transform import (
    transform_bookings_to_suggestion,
    transform_enrichment_suggestions,
    transform_job_to_case_vals,
)

logger = logging.getLogger(__name__)


class BridgeSync:
    """Polls DocumentFlow for approved jobs and creates Odoo cases."""

    def __init__(self, config: BridgeConfig):
        self.config = config
        self.docflow = DocFlowClient(
            base_url=config.docflow_url,
            username=config.docflow_username,
            password=config.docflow_password,
            token=config.docflow_token,
        )
        self.odoo = OdooAiOfficeClient(
            url=config.odoo_url,
            db=config.odoo_db,
            username=config.odoo_username,
            password=config.odoo_password,
        )

    async def sync_once(self) -> dict:
        """Run a single sync cycle.

        Returns stats dict: {created, skipped, errors}.
        """
        created = 0
        skipped = 0
        errors = []

        for status in self.config.sync_statuses:
            try:
                jobs_data = await self.docflow.list_jobs(status=status, page_size=100)
            except Exception as exc:
                errors.append({"status": status, "error": str(exc)})
                continue

            items = jobs_data.get("items", [])
            if isinstance(jobs_data, list):
                items = jobs_data

            for job_summary in items:
                job_id = job_summary.get("id")
                if not job_id:
                    continue

                # Deduplication check
                if self.odoo.case_exists("docflow.job", job_id):
                    skipped += 1
                    logger.debug("Skipping job %d (already synced)", job_id)
                    continue

                try:
                    await self._sync_job(job_id)
                    created += 1
                    logger.info("Synced job %d to Odoo", job_id)
                except Exception as exc:
                    errors.append({"job_id": job_id, "error": str(exc)})
                    logger.error("Failed to sync job %d: %s", job_id, exc)

        return {"created": created, "skipped": skipped, "errors": errors}

    async def _sync_job(self, job_id: int) -> int:
        """Sync a single DocumentFlow job to Odoo.

        Returns the created Odoo case ID.
        """
        # Fetch full job details + bookings
        job = await self.docflow.get_job(job_id)
        bookings = await self.docflow.get_bookings(job_id)

        if self.config.dry_run:
            logger.info("[DRY RUN] Would create case for job %d", job_id)
            return 0

        # Create case
        case_vals = transform_job_to_case_vals(job)
        case_id = self.odoo.create_case(case_vals)

        # Add enrichment suggestions
        for sugg in transform_enrichment_suggestions(job):
            self.odoo.add_suggestion(case_id, sugg)

        # Add accounting_entry suggestion from bookings
        acct_sugg = transform_bookings_to_suggestion(job, bookings)
        if acct_sugg["payload"]["lines"]:
            self.odoo.add_suggestion(case_id, acct_sugg)

        # Transition to proposed
        self.odoo.action_propose(case_id)

        return case_id

    async def run_daemon(self) -> None:
        """Run sync loop continuously at configured interval."""
        logger.info(
            "Bridge daemon started (interval=%ds, statuses=%s, dry_run=%s)",
            self.config.sync_interval,
            self.config.sync_statuses,
            self.config.dry_run,
        )
        while True:
            try:
                stats = await self.sync_once()
                logger.info("Sync cycle: %s", stats)
            except Exception as exc:
                logger.error("Sync cycle error: %s", exc)
            await asyncio.sleep(self.config.sync_interval)


def main():
    """CLI entry point for the bridge sync."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = BridgeConfig.from_env()

    # Parse CLI args
    daemon_mode = "--daemon" in sys.argv
    once_mode = "--once" in sys.argv
    if "--dry-run" in sys.argv:
        config.dry_run = True

    if daemon_mode:
        asyncio.run(BridgeSync(config).run_daemon())
    elif once_mode or not daemon_mode:
        stats = asyncio.run(BridgeSync(config).sync_once())
        print("Sync result:", stats)


if __name__ == "__main__":
    main()
