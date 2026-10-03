"""Celery application for LoksewaAI's background jobs.

Two periodic jobs run here, both wrapping plain functions that are also
exposed as management commands (`dispatch_scheduled_notifications`,
`archive_expired_examinations`) so the logic itself can be run and verified
without a broker - only the *scheduling* needs Celery.

Nothing in this file makes those jobs actually run on a schedule by itself.
Production needs two extra long-running processes alongside gunicorn:
    celery -A backend worker --loglevel=info
    celery -A backend beat --loglevel=info
Both need CELERY_BROKER_URL (or REDIS_URL) pointing at a real Redis
instance - see Procfile for the process declarations.
"""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    # Admins can schedule a broadcast for later (AdminNotification.status
    # 'scheduled' + scheduled_for), but until now nothing ever delivered it -
    # they had to remember to come back and press "Send" themselves. Checked
    # every 5 minutes so a scheduled_for time is never more than ~5 minutes late.
    'dispatch-scheduled-notifications': {
        'task': 'core.tasks.dispatch_scheduled_notifications',
        'schedule': crontab(minute='*/5'),
    },
    # Exams stay in 'published' forever after their end_time passes unless an
    # admin manually archives them. Hourly cleanup keeps admin/student exam
    # lists from accumulating exams nobody can start anymore.
    'archive-expired-examinations': {
        'task': 'exams.tasks.archive_expired_examinations',
        'schedule': crontab(minute=0),
    },
    # "Your exam starts soon" notifications. Every 5 minutes with a 30-minute
    # lookahead window (see NotificationService.notify_exams_starting_soon)
    # means a student is notified 25-30 minutes before start, and the
    # related_id dedupe keeps re-running this from ever double-notifying.
    'notify-exams-starting-soon': {
        'task': 'exams.tasks.notify_exams_starting_soon',
        'schedule': crontab(minute='*/5'),
    },
    # "Package expiring soon" / "package expired" notifications for students
    # with an active Subscription. Once daily is enough lead time (see
    # NotificationService.notify_subscription_expiring_soon's 7-day window);
    # the related_id dedupe means running it daily never double-notifies.
    'notify-expiring-and-expired-subscriptions': {
        'task': 'subscriptions.tasks.notify_expiring_and_expired_subscriptions',
        'schedule': crontab(hour=8, minute=0),
    },
    # Production-grade automatic daily database backup.
    # Runs at 02:00 server time, compresses, hashes, and replicates to Cloudflare R2.
    'automatic-daily-database-backup': {
        'task': 'administration.tasks.run_automatic_daily_backup',
        'schedule': crontab(hour=2, minute=0),
    },
    # Automated daily retention policy cleanup.
    # Runs at 03:00 server time, purges expired archives while protecting latest recovery point.
    'cleanup-database-backup-retention': {
        'task': 'administration.tasks.run_backup_retention_cleanup',
        'schedule': crontab(hour=3, minute=0),
    },
}
