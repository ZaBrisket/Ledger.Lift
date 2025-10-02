from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apps.api.app.services.costs import reconcile_costs
from apps.api.app.services.gdpr import sweep_stale_deletions
from apps.api.app.config_t3 import settings
import logging

log=logging.getLogger(__name__)
scheduler=AsyncIOScheduler()

def start_schedulers():
    if settings.features_t3_costs:
        scheduler.add_job(reconcile_costs, "interval", minutes=5, id="t3_cost_reconcile")
    if settings.features_t3_gdpr:
        scheduler.add_job(sweep_stale_deletions, "interval", seconds=settings.deletion_sweep_interval_seconds, id="t3_deletion_sweep")
    scheduler.start()
