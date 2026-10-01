from django.db import models
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
