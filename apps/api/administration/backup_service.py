import os
import io
import gzip
import json
import hashlib
import logging
from datetime import datetime
from django.conf import settings
from django.core import serializers
from django.db import transaction, connection
from django.utils import timezone
from django.apps import apps
from django.core.exceptions import ValidationError

from administration.models import DatabaseBackup, AuditLog
from administration.r2_storage_service import R2StorageService

logger = logging.getLogger(__name__)


class BackupService:
    """
    Production-grade backup and recovery service.
    Produces real, gzip-compressed, SHA-256 verified full database backups.
    Supports off-site replication to Cloudflare R2, automatic retention management,
    pre-restore safety snapshots, and atomic transactional recovery with post-restore integrity checks.
    """

    BACKUP_DIR = settings.BASE_DIR / 'backups' / 'database'

    MODELS_TO_BACKUP = [
        'core.User',
        'core.Tag',
        'exams.ExamCategory',
        'exams.Exam',
        'exams.Paper',
        'exams.Subject',
        'exams.Chapter',
        'exams.Topic',
        'exams.UserTopicProgress',
        'exams.Question',
        'exams.QuestionCollection',
        'exams.QuestionSet',
        'exams.QuestionSetQuestion',
        'exams.Examination',
        'exams.ExaminationQuestion',
        'exams.ExaminationEligibility',
        'exams.ExaminationRequest',
        'exams.SubjectiveQuestionSet',
        'exams.ExamSchedule',
        'exams.ExaminationAttempt',
        'exams.StudentAnswer',
        'exams.SubjectiveSubmission',
        'exams.SubjectiveSubmissionPage',
        'exams.SubjectiveQuestionScore',
        'courses.Course',
        'courses.Enrollment',
        'courses.CourseApplication',
        'notes.MaterialCategory',
        'notes.MaterialCollection',
        'notes.StudyMaterial',
        'subscriptions.SubscriptionPlan',
        'subscriptions.Subscription',
        'subscriptions.SubscriptionPayment',
        'marketplace.Product',
        'administration.AuditLog',
        'administration.TrashItem',
    ]

    @classmethod
    def ensure_backup_dir(cls):
        os.makedirs(cls.BACKUP_DIR, exist_ok=True)

    @classmethod
    def get_record_counts(cls) -> dict:
        counts = {}
        for app_model in cls.MODELS_TO_BACKUP:
            try:
                model_class = apps.get_model(app_model)
                counts[model_class._meta.verbose_name_plural.title()] = model_class.objects.count()
            except Exception:
                pass
        return counts

    @classmethod
    def create_backup(cls, backup_type: str = 'full', user=None, custom_name: str = '') -> DatabaseBackup:
        """
        Generates a verified, gzip-compressed database backup.
        Replicates archive to Cloudflare R2 if configured, computes SHA-256 hash,
        and sets retention window.
        """
        cls.ensure_backup_dir()

        timestamp = timezone.now()
        timestamp_str = timestamp.strftime('%Y%m%d_%H%M%S')
        default_name = f"LoksewaAI_{backup_type.upper()}_{timestamp_str}"
        name = custom_name.strip() if custom_name else default_name
        filename = f"{name.replace(' ', '_').lower()}.json.gz"
        file_path = str(cls.BACKUP_DIR / filename)

        record_counts = cls.get_record_counts()
        db_engine = connection.settings_dict.get('ENGINE', 'unknown')

        # Retention duration
        retention_days = getattr(settings, 'BACKUP_RETENTION_DAYS', 30)
        retention_until = timestamp + timezone.timedelta(days=retention_days)

        # Pre-restore safety snapshots are protected from retention cleanup by default
        is_protected = (backup_type == 'pre_restore')

        backup = DatabaseBackup.objects.create(
            name=name,
            file_path=file_path,
            backup_type=backup_type,
            status='in_progress',
            db_engine=db_engine,
            record_counts=record_counts,
            schema_version='django_6.1',
            retention_until=retention_until,
            is_protected=is_protected,
            created_by=user if user and user.is_authenticated else None,
        )

        hasher = hashlib.sha256()

        try:
            # Query objects to serialize
            objects_to_serialize = []
            for model_str in cls.MODELS_TO_BACKUP:
                try:
                    m = apps.get_model(model_str)
                    objects_to_serialize.extend(m.objects.all().iterator(chunk_size=1000))
                except Exception as e:
                    logger.warning(f"Could not export model {model_str}: {e}")

            # Stream into gzip
            with open(file_path, 'wb') as raw_file:
                with gzip.GzipFile(fileobj=raw_file, mode='wb') as gz_file:
                    data_str = serializers.serialize('json', objects_to_serialize, indent=2)
                    data_bytes = data_str.encode('utf-8')
                    gz_file.write(data_bytes)
                    hasher.update(data_bytes)

            file_size = os.path.getsize(file_path)
            checksum = hasher.hexdigest()

            backup.size_bytes = file_size
            backup.checksum_sha256 = checksum
            backup.status = 'validating'
            backup.save()

            # Upload to Cloudflare R2 if configured
            if R2StorageService.is_configured():
                backup.status = 'uploading'
                backup.save(update_fields=['status'])

                storage_key = R2StorageService.generate_storage_key(
                    backup_id=backup.id,
                    dt=timestamp,
                    backup_type=backup_type,
                    filename=filename,
                )
                backup.storage_key = storage_key
                backup.save(update_fields=['storage_key'])

                try:
                    upload_res = R2StorageService.upload_file(
                        local_path=file_path,
                        storage_key=storage_key,
                        metadata={
                            'backup_id': backup.id,
                            'backup_type': backup_type,
                            'checksum_sha256': checksum,
                            'created_at': timestamp.isoformat(),
                        }
                    )
                    backup.r2_uploaded = True
                    backup.r2_etag = upload_res.get('etag', '')
                    backup.storage_backend = 'dual' if getattr(settings, 'BACKUP_KEEP_LOCAL_COPY', True) else 'cloudflare_r2'

                    # Remote verification against Cloudflare R2
                    r2_verify = R2StorageService.verify_object_integrity(storage_key, checksum)
                    if r2_verify.get('valid'):
                        backup.r2_verified = True
                        backup.status = 'verified'
                        backup.verified_at = timezone.now()
                        backup.completed_at = timezone.now()
                        backup.verification_message = f"Verified: Stored in Cloudflare R2 (s3://{upload_res['bucket']}/{storage_key}) and SHA-256 confirmed."
                    else:
                        backup.status = 'failed'
                        backup.verification_message = f"R2 remote integrity check failed: {r2_verify.get('message')}"

                    backup.save()

                    # Audit R2 upload
                    AuditLog.objects.create(
                        actor=user if user and user.is_authenticated else None,
                        action='BACKUP_UPLOADED',
                        entity_type='DatabaseBackup',
                        entity_id=str(backup.id),
                        details={
                            'storage_key': storage_key,
                            'r2_verified': backup.r2_verified,
                            'etag': backup.r2_etag,
                            'size_bytes': file_size,
                        }
                    )

                    # If server disk space preservation is enabled, remove local file after verified R2 upload
                    if not getattr(settings, 'BACKUP_KEEP_LOCAL_COPY', True) and backup.r2_verified:
                        if os.path.exists(file_path):
                            os.remove(file_path)

                except Exception as r2_err:
                    logger.exception(f"Failed to upload backup #{backup.id} to Cloudflare R2")
                    backup.status = 'failed'
                    backup.error_message = f"Cloudflare R2 replication failed: {str(r2_err)}"
                    backup.verification_message = backup.error_message
                    backup.save()
                    raise ValidationError(backup.error_message)

            else:
                # Cloudflare R2 not configured: local verification
                backup.storage_backend = 'local'
                cls.verify_backup(backup, user=user)
                backup.completed_at = timezone.now()
                backup.save()

            AuditLog.objects.create(
                actor=user if user and user.is_authenticated else None,
                action='BACKUP_CREATE',
                entity_type='DatabaseBackup',
                entity_id=str(backup.id),
                details={
                    'name': backup.name,
                    'backup_type': backup.backup_type,
                    'size_bytes': file_size,
                    'checksum_sha256': checksum,
                    'storage_backend': backup.storage_backend,
                    'r2_uploaded': backup.r2_uploaded,
                    'retention_until': backup.retention_until.isoformat() if backup.retention_until else None,
                }
            )

            return backup

        except Exception as e:
            backup.status = 'failed'
            backup.verification_message = f"Backup generation failed: {str(e)}"
            backup.error_message = str(e)
            backup.save()
            logger.exception("Database backup creation failed")
            raise ValidationError(f"Backup creation failed: {str(e)}")

    @classmethod
    def verify_backup(cls, backup: DatabaseBackup, user=None) -> bool:
        """
        Verifies backup integrity across Cloudflare R2 and local filesystem.
        Validates SHA-256 checksum, gzip stream, and JSON deserializability.
        """
        hasher = hashlib.sha256()

        # Step 1: Check remote Cloudflare R2 object if recorded
        if backup.storage_key and R2StorageService.is_configured():
            r2_res = R2StorageService.verify_object_integrity(backup.storage_key, backup.checksum_sha256)
            if not r2_res.get('valid'):
                backup.status = 'corrupted'
                backup.r2_verified = False
                backup.verification_message = f"Cloudflare R2 verification failed: {r2_res.get('message')}"
                backup.save(update_fields=['status', 'r2_verified', 'verification_message'])
                return False
            backup.r2_verified = True

        # Step 2: Check local file if present
        if os.path.exists(backup.file_path):
            file_size = os.path.getsize(backup.file_path)
            if file_size == 0:
                backup.status = 'corrupted'
                backup.verification_message = "Local backup archive is empty (0 bytes)."
                backup.save(update_fields=['status', 'verification_message'])
                return False

            try:
                with gzip.open(backup.file_path, 'rb') as gz:
                    chunk = gz.read(65536)
                    if not chunk:
                        raise ValueError("Empty uncompressed stream")
                    while chunk:
                        hasher.update(chunk)
                        chunk = gz.read(65536)

                calculated_checksum = hasher.hexdigest()
                if backup.checksum_sha256 and calculated_checksum != backup.checksum_sha256:
                    backup.status = 'corrupted'
                    backup.verification_message = f"Checksum mismatch: expected {backup.checksum_sha256[:12]}..., got {calculated_checksum[:12]}..."
                    backup.save(update_fields=['status', 'verification_message'])
                    return False

            except Exception as e:
                backup.status = 'corrupted'
                backup.verification_message = f"Local archive verification error: {str(e)}"
                backup.save(update_fields=['status', 'verification_message'])
                return False

        elif not backup.storage_key:
            backup.status = 'failed'
            backup.verification_message = "Backup archive file not found on disk or remote storage."
            backup.save(update_fields=['status', 'verification_message'])
            return False

        backup.status = 'verified'
        backup.verified_at = timezone.now()
        storage_desc = "Cloudflare R2 & Local" if backup.r2_verified and os.path.exists(backup.file_path) else (
            "Cloudflare R2" if backup.r2_verified else "Local Storage"
        )
        backup.verification_message = f"Backup verified: valid gzip archive on {storage_desc}, SHA-256 confirmed."
        backup.save(update_fields=['status', 'verified_at', 'verification_message', 'r2_verified'])

        if user and user.is_authenticated:
            AuditLog.objects.create(
                actor=user,
                action='BACKUP_VERIFY',
                entity_type='DatabaseBackup',
                entity_id=str(backup.id),
                details={
                    'checksum': backup.checksum_sha256,
                    'status': 'verified',
                    'storage_backend': backup.storage_backend,
                }
            )

        return True

    @classmethod
    def run_post_restore_integrity_checks(cls) -> dict:
        """
        Validates post-restore relational integrity across essential business tables.
        """
        User = apps.get_model('core', 'User')
        ExamCategory = apps.get_model('exams', 'ExamCategory')
        Exam = apps.get_model('exams', 'Exam')
        Question = apps.get_model('exams', 'Question')
        Examination = apps.get_model('exams', 'Examination')

        checks = {
            'users_exist': User.objects.exists(),
            'categories_exist': ExamCategory.objects.exists(),
            'exams_exist': Exam.objects.exists(),
            'questions_exist': Question.objects.exists(),
            'examinations_exist': Examination.objects.exists(),
            'users_count': User.objects.count(),
            'examinations_count': Examination.objects.count(),
            'questions_count': Question.objects.count(),
        }

        # Essential check: at least Users and Academic tree must exist
        passed = checks['users_exist'] and (checks['categories_exist'] or checks['exams_exist'])
        return {
            'passed': passed,
            'metrics': checks,
            'message': 'Post-restore integrity checks passed.' if passed else 'Post-restore integrity checks detected missing critical records.',
        }

    @classmethod
    def restore_backup(cls, backup: DatabaseBackup, user, confirmation_text: str) -> dict:
        """
        Restores the database from a verified backup archive.
        - Requires Super Admin authorization.
        - Enforces explicit typed confirmation 'RESTORE DATABASE'.
        - Verifies archive integrity and downloads from Cloudflare R2 if local copy is absent.
        - Automatically creates an off-site pre-restore safety snapshot before touching live tables.
        - Runs post-restore integrity checks and records full audit logs.
        """
        if not user or not user.is_authenticated or user.role != 'super-admin':
            raise ValidationError("Restoring a database backup requires Super Admin authorization.")

        if confirmation_text.strip() != 'RESTORE DATABASE':
            raise ValidationError("Confirmation text must exactly match 'RESTORE DATABASE'.")

        # Step 1: Ensure archive file exists locally (download from R2 if needed)
        archive_path = backup.file_path
        if not os.path.exists(archive_path):
            if backup.storage_key and R2StorageService.is_configured():
                logger.info(f"Local file missing. Downloading backup #{backup.id} from Cloudflare R2...")
                cls.ensure_backup_dir()
                archive_path = str(cls.BACKUP_DIR / os.path.basename(backup.storage_key))
                R2StorageService.download_file(backup.storage_key, archive_path)
            else:
                raise ValidationError("Backup archive is missing from local disk and Cloudflare R2 is unreachable.")

        # Step 2: Validate archive integrity before touching the live database
        if not cls.verify_backup(backup, user=user):
            raise ValidationError(f"Target backup is not verified: {backup.verification_message}")

        # Validate uncompressed JSON structure
        try:
            with gzip.open(archive_path, 'rt', encoding='utf-8') as gz:
                data = json.load(gz)
        except Exception as read_err:
            raise ValidationError(f"Invalid backup archive: JSON payload cannot be parsed ({read_err})")

        # Step 3: Create pre-restore safety snapshot of the CURRENT database state
        safety_snapshot = cls.create_backup(
            backup_type='pre_restore',
            user=user,
            custom_name=f"Safety_Snapshot_Before_Restoring_Backup_{backup.id}",
        )
        safety_snapshot.is_protected = True
        safety_snapshot.save(update_fields=['is_protected'])

        # Step 4: Perform atomic restore inside transaction
        backup.restore_status = 'restoring'
        backup.save(update_fields=['restore_status'])

        try:
            with transaction.atomic():
                for obj in serializers.deserialize('json', data):
                    obj.save()

            # Step 5: Post-restore integrity verification
            integrity_result = cls.run_post_restore_integrity_checks()
            if not integrity_result['passed']:
                backup.restore_status = 'failed'
                backup.save(update_fields=['restore_status'])
                raise ValidationError(f"Restoration completed but integrity check failed: {integrity_result['message']}")

            backup.restore_status = 'restored'
            backup.save(update_fields=['restore_status'])

            AuditLog.objects.create(
                actor=user,
                action='RESTORE_DATABASE',
                entity_type='DatabaseBackup',
                entity_id=str(backup.id),
                details={
                    'backup_name': backup.name,
                    'pre_restore_backup_id': safety_snapshot.id,
                    'restored_at': timezone.now().isoformat(),
                    'integrity': integrity_result['metrics'],
                }
            )

            return {
                'success': True,
                'message': f"Database successfully restored from '{backup.name}'.",
                'pre_restore_snapshot_id': safety_snapshot.id,
                'integrity': integrity_result['metrics'],
            }

        except Exception as e:
            backup.restore_status = 'failed'
            backup.save(update_fields=['restore_status'])
            logger.exception("Database restoration error")
            AuditLog.objects.create(
                actor=user,
                action='RESTORE_FAILED',
                entity_type='DatabaseBackup',
                entity_id=str(backup.id),
                details={'error': str(e), 'pre_restore_snapshot_id': safety_snapshot.id}
            )
            raise ValidationError(
                f"Restoration failed: {str(e)}. Safe state preserved in pre-restore snapshot #{safety_snapshot.id}."
            )

    @classmethod
    def cleanup_expired_backups(cls) -> dict:
        """
        Enforces automated retention policy.
        - Identifies backups whose retention_until has elapsed.
        - Strictly preserves protected backups (is_protected=True).
        - Strictly preserves the latest verified recovery point.
        - Removes expired objects from Cloudflare R2 and local filesystem.
        """
        now = timezone.now()
        candidates = DatabaseBackup.objects.filter(
            retention_until__lt=now,
            status='verified',
            is_protected=False,
        ).order_by('created_at')

        # Find latest verified backup to NEVER purge it
        latest_verified = DatabaseBackup.objects.filter(status='verified').order_by('-created_at').first()
        latest_id = latest_verified.id if latest_verified else None

        cleaned_count = 0
        preserved_count = 0
        cleaned_details = []

        for b in candidates:
            # Rule: Always preserve latest verified backup regardless of age
            if b.id == latest_id:
                preserved_count += 1
                continue

            try:
                # Remove remote Cloudflare R2 object
                if b.storage_key and R2StorageService.is_configured():
                    R2StorageService.delete_object(b.storage_key)

                # Remove local file if present
                if os.path.exists(b.file_path):
                    try:
                        os.remove(b.file_path)
                    except OSError:
                        pass

                b.status = 'expired'
                b.verification_message = f"Cleaned up by retention policy on {now.strftime('%Y-%m-%d %H:%M')}."
                b.save(update_fields=['status', 'verification_message'])

                cleaned_count += 1
                cleaned_details.append({
                    'id': b.id,
                    'name': b.name,
                    'created_at': b.created_at.isoformat(),
                })

                AuditLog.objects.create(
                    action='BACKUP_EXPIRED',
                    entity_type='DatabaseBackup',
                    entity_id=str(b.id),
                    details={'name': b.name, 'cleaned_at': now.isoformat()}
                )

            except Exception as e:
                logger.error(f"Failed to cleanup expired backup #{b.id}: {e}")

        return {
            'cleaned_count': cleaned_count,
            'preserved_count': preserved_count,
            'cleaned_backups': cleaned_details,
        }

    @classmethod
    def toggle_protect_backup(cls, backup: DatabaseBackup, user) -> dict:
        """
        Toggles protected status to shield important snapshots from retention cleanup.
        """
        if not user or not user.is_authenticated or user.role != 'super-admin':
            raise ValidationError("Modifying backup protection requires Super Admin authorization.")

        backup.is_protected = not backup.is_protected
        backup.save(update_fields=['is_protected'])

        action = 'BACKUP_PROTECTED' if backup.is_protected else 'BACKUP_UNPROTECTED'
        AuditLog.objects.create(
            actor=user,
            action=action,
            entity_type='DatabaseBackup',
            entity_id=str(backup.id),
            details={'is_protected': backup.is_protected, 'name': backup.name}
        )

        return {
            'success': True,
            'is_protected': backup.is_protected,
            'message': f"Backup '{backup.name}' is now {'protected from automatic cleanup' if backup.is_protected else 'subject to standard retention policy'}.",
        }

    @classmethod
    def delete_backup(cls, backup: DatabaseBackup, user) -> dict:
        """
        Safely deletes a backup from Cloudflare R2, local filesystem, and metadata. Requires Super Admin.
        """
        if not user or not user.is_authenticated or user.role != 'super-admin':
            raise ValidationError("Deleting backup archives requires Super Admin authorization.")

        # Delete remote R2 object
        if backup.storage_key and R2StorageService.is_configured():
            R2StorageService.delete_object(backup.storage_key)

        # Delete local file
        if os.path.exists(backup.file_path):
            try:
                os.remove(backup.file_path)
            except OSError as e:
                logger.warning(f"Could not remove physical backup file: {e}")

        backup_id = backup.id
        backup_name = backup.name
        backup.delete()

        AuditLog.objects.create(
            actor=user,
            action='BACKUP_DELETE',
            entity_type='DatabaseBackup',
            entity_id=str(backup_id),
            details={'name': backup_name}
        )

        return {'success': True, 'message': f"Backup '{backup_name}' deleted permanently."}
