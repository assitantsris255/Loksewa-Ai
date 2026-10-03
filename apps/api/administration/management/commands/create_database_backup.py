import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from administration.models import DatabaseBackup
from administration.backup_service import BackupService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Creates a verified, compressed database backup and uploads to Cloudflare R2 if configured."

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            default='scheduled',
            choices=['daily', 'scheduled', 'manual', 'full', 'pre_restore'],
            help="Type of database backup to create (default: scheduled)",
        )
        parser.add_argument(
            '--name',
            type=str,
            default='',
            help="Optional custom label for the backup",
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help="Force creation even if a daily backup already ran today (idempotency override)",
        )

    def handle(self, *args, **options):
        backup_type = options['type']
        custom_name = options['name']
        force = options['force']

        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Idempotency check for automated daily/scheduled backups
        if backup_type in ('scheduled', 'daily') and not force:
            existing_today = DatabaseBackup.objects.filter(
                backup_type__in=['scheduled', 'daily'],
                created_at__gte=today_start,
                status='verified',
            ).first()

            if existing_today:
                self.stdout.write(
                    self.style.WARNING(
                        f"Idempotency: Verified daily backup already exists for today "
                        f"(ID: {existing_today.id}, Created: {existing_today.created_at}). "
                        f"Use --force to override."
                    )
                )
                return

        self.stdout.write(f"Initiating {backup_type} database backup...")

        try:
            backup = BackupService.create_backup(
                backup_type=backup_type,
                custom_name=custom_name,
            )

            status_style = self.style.SUCCESS if backup.status == 'verified' else self.style.WARNING
            self.stdout.write(
                status_style(
                    f"Backup #{backup.id} completed. Status: {backup.status.upper()}. "
                    f"Size: {backup.size_bytes} bytes. "
                    f"Storage: {backup.storage_backend}. "
                    f"Checksum: {backup.checksum_sha256[:16]}..."
                )
            )
            if backup.storage_key:
                self.stdout.write(f"Cloudflare R2 Object Key: {backup.storage_key}")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Backup failed: {str(e)}"))
            raise e
