from django.db import models
from django.utils import timezone
from core.models import User

class AuditLog(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=100, null=True, blank=True) # Changed to CharField to support Q-000001
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.actor} - {self.action} on {self.entity_type} {self.entity_id}"

class CSVImport(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('validated', 'Validated'),
        ('imported', 'Imported'),
        ('failed', 'Failed'),
    )
    admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    # Syllabus placement and defaults are chosen in the UI, not in the CSV, and
    # apply to every row of the file.
    category = models.ForeignKey(
        'exams.ExamCategory', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='csv_imports',
    )
    exam = models.ForeignKey(
        'exams.Exam', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='csv_imports',
    )
    subject = models.ForeignKey(
        'exams.Subject', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='csv_imports',
    )
    chapter = models.ForeignKey(
        'exams.Chapter', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='csv_imports',
    )
    topic = models.ForeignKey(
        'exams.Topic', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='csv_imports',
    )
    question_type = models.CharField(max_length=20, default='mcq')
    difficulty = models.CharField(max_length=10, default='medium', blank=True, null=True)
    # Optional: imported questions can be added to a Collection and/or tagged.
    # Membership/tagging does not bypass approval - see commit() in import_views.py.
    collection = models.ForeignKey(
        'exams.QuestionCollection', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='csv_imports',
    )
    tag_objects = models.ManyToManyField('core.Tag', blank=True, related_name='csv_imports')
    total_rows = models.IntegerField(default=0)
    valid_rows = models.IntegerField(default=0)
    duplicate_rows = models.IntegerField(default=0)
    error_rows = models.IntegerField(default=0)
    report_data = models.JSONField(default=dict, blank=True, help_text="Detailed error and validation info per row")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Import {self.file_name} ({self.status})"


class ExportJob(models.Model):
    """A CSV export generated off the request/response cycle.

    AdminAuditLogExportView built the whole CSV synchronously in one request
    - fine for a small dataset, but audit logs grow unboundedly, and nothing
    bounded how large that export could get before it either timed out the
    request or blocked a web worker for real users. This model is the
    tracking row for the same export run as a Celery job instead: the admin
    gets a job id back immediately, and downloads the file once
    administration.tasks.generate_export_job finishes writing it.
    """
    EXPORT_TYPE_CHOICES = (
        ('audit_logs', 'Audit Logs'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    export_type = models.CharField(max_length=50, choices=EXPORT_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    # The query params the admin had applied (search/category filters) when
    # they requested the export, so the background job reproduces exactly
    # what they were looking at - not just "all audit logs ever".
    filters = models.JSONField(default=dict, blank=True)
    file = models.FileField(upload_to='exports/', null=True, blank=True)
    row_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)

    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='export_jobs')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_export_type_display()} export ({self.status})"


class TrashItem(models.Model):
    """
    Centralized Trash / Recycle Bin tracking for safely deleted business data.
    Preserves historical identity, metadata snapshot, dependency status,
    and enables single or cascading restoration.
    """
    app_label = models.CharField(max_length=50, db_index=True)
    model_name = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=100, db_index=True)
    title = models.CharField(max_length=255)
    item_type = models.CharField(max_length=100)
    module = models.CharField(max_length=50, db_index=True)
    
    deleted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deleted_trash_items'
    )
    deleted_at = models.DateTimeField(default=timezone.now, db_index=True)
    reason = models.TextField(blank=True, default='')
    details = models.JSONField(default=dict, blank=True)
    
    is_restored = models.BooleanField(default=False, db_index=True)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='restored_trash_items'
    )
    
    is_permanent_deleted = models.BooleanField(default=False, db_index=True)
    permanent_deleted_at = models.DateTimeField(null=True, blank=True)
    permanent_deleted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='permanently_deleted_trash_items'
    )
    
    is_protected = models.BooleanField(default=False, help_text="True if historical records depend on this item, preventing permanent deletion")
    protection_reasons = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-deleted_at']
        indexes = [
            models.Index(fields=['is_restored', 'is_permanent_deleted', 'deleted_at']),
            models.Index(fields=['app_label', 'model_name', 'object_id']),
        ]

    def __str__(self):
        return f"{self.item_type}: {self.title} (Trash #{self.id})"

    @property
    def protection_reason(self):
        return "; ".join(self.protection_reasons) if self.protection_reasons else ""


class DatabaseBackup(models.Model):
    """
    Production-grade database backup record with verification metrics,
    checksums, real storage references, and pre-restore snapshot tracking.
    """
    BACKUP_TYPES = (
        ('full', 'Full Database Backup'),
        ('pre_restore', 'Pre-Restore Safety Snapshot'),
        ('manual', 'Manual Database Backup'),
        ('scheduled', 'Scheduled Automatic Backup'),
    )
    STATUS_CHOICES = (
        ('in_progress', 'Creating Backup...'),
        ('uploading', 'Uploading to Cloudflare R2...'),
        ('validating', 'Validating Archive...'),
        ('verified', 'Verified'),
        ('failed', 'Failed'),
        ('corrupted', 'Corrupted'),
        ('expired', 'Expired / Cleaned'),
    )
    STORAGE_BACKEND_CHOICES = (
        ('local', 'Local Storage'),
        ('cloudflare_r2', 'Cloudflare R2'),
        ('dual', 'Local & Cloudflare R2'),
    )

    name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    backup_type = models.CharField(max_length=30, choices=BACKUP_TYPES, default='full', db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress', db_index=True)
    size_bytes = models.BigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    record_counts = models.JSONField(default=dict, blank=True)
    schema_version = models.CharField(max_length=100, blank=True)
    db_engine = models.CharField(max_length=100, blank=True)

    # Cloudflare R2 & Off-site Storage
    storage_backend = models.CharField(max_length=50, choices=STORAGE_BACKEND_CHOICES, default='local', db_index=True)
    storage_key = models.CharField(max_length=500, blank=True, help_text="R2 S3-compatible object key")
    r2_uploaded = models.BooleanField(default=False, db_index=True)
    r2_verified = models.BooleanField(default=False, db_index=True)
    r2_etag = models.CharField(max_length=100, blank=True)

    # Retention Policy & Lifecycle
    retention_until = models.DateTimeField(null=True, blank=True, db_index=True)
    is_protected = models.BooleanField(default=False, db_index=True, help_text="Protected backups cannot be auto-purged by retention")
    completed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    restore_status = models.CharField(max_length=30, blank=True, default='not_restored')
    error_message = models.TextField(blank=True)
    
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='database_backups'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_message = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} [{self.get_backup_type_display()}] ({self.status}) - {self.storage_backend}"

    @property
    def is_verified(self):
        return self.status == 'verified'

