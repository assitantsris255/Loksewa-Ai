from django.core.management.base import BaseCommand
from administration.backup_service import BackupService


class Command(BaseCommand):
    help = "Enforces database backup retention policy, safely pruning expired backups while preserving protected items."

    def handle(self, *args, **options):
        self.stdout.write("Running database backup retention cleanup...")

        result = BackupService.cleanup_expired_backups()

        cleaned_count = result.get('cleaned_count', 0)
        preserved_count = result.get('preserved_count', 0)

        if cleaned_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully cleaned up {cleaned_count} expired backup(s). "
                    f"Preserved latest recovery point ({preserved_count})."
                )
            )
            for item in result.get('cleaned_backups', []):
                self.stdout.write(f"  - Purged Backup #{item['id']} ({item['name']})")
        else:
            self.stdout.write(
                self.style.SUCCESS("No expired backups require cleanup. Retention policy is up to date.")
            )
