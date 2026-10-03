import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='administration.tasks.generate_export_job')
def generate_export_job_task(job_id):
    """Runs one ExportJob in the background. Thin wrapper - see
    export_service.generate_export_job for the actual work; that function is
    also called directly by tests and the `run_export_job` management
    command so it's exercised without needing a live Celery worker."""
    from .models import ExportJob
    from .export_service import generate_export_job

    try:
        job = ExportJob.objects.get(id=job_id)
    except ExportJob.DoesNotExist:
        logger.error("generate_export_job_task: ExportJob %s no longer exists.", job_id)
        return

    generate_export_job(job)


@shared_task(name='administration.tasks.run_automatic_daily_backup')
def run_automatic_daily_backup():
    """
    Automated daily database backup job triggered by Celery Beat or cron.
    Generates a compressed snapshot and replicates to Cloudflare R2 if configured.
    Enforces idempotency (won't duplicate if already succeeded today).
    """
    from django.utils import timezone
    from .models import DatabaseBackup
    from .backup_service import BackupService

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    existing_today = DatabaseBackup.objects.filter(
        backup_type='scheduled',
        created_at__gte=today_start,
        status='verified',
    ).first()

    if existing_today:
        logger.info(f"Automatic daily backup already executed for today (Backup #{existing_today.id}). Skipping.")
        return {'status': 'skipped', 'backup_id': existing_today.id}

    logger.info("Starting automatic daily database backup...")
    try:
        backup = BackupService.create_backup(backup_type='scheduled')
        logger.info(f"Automatic daily backup #{backup.id} completed with status: {backup.status}")
        return {'status': 'success', 'backup_id': backup.id, 'verification': backup.status}
    except Exception as e:
        logger.exception("Automatic daily backup task failed")
        return {'status': 'failed', 'error': str(e)}


@shared_task(name='administration.tasks.run_backup_retention_cleanup')
def run_backup_retention_cleanup():
    """
    Automated daily retention policy cleanup.
    Safely prunes expired backups while protecting latest verified backup and shielded snapshots.
    """
    from .backup_service import BackupService

    logger.info("Starting scheduled backup retention cleanup...")
    try:
        result = BackupService.cleanup_expired_backups()
        logger.info(f"Retention cleanup finished: {result.get('cleaned_count', 0)} purged.")
        return result
    except Exception as e:
        logger.exception("Scheduled retention cleanup task failed")
        return {'status': 'failed', 'error': str(e)}
