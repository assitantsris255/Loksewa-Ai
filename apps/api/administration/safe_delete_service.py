import logging
from django.db import transaction
from django.utils import timezone
from django.apps import apps
from django.core.exceptions import ValidationError

from administration.models import AuditLog, TrashItem
from core.models import User

logger = logging.getLogger(__name__)


class SafeDeleteService:
    """
    Centralized service for safe deletion, trash management, dependency checking,
    and reversible restoration across all LoksewaAI academic and configuration models.
    """

    MODEL_CONFIG = {
        'examination': {
            'app_label': 'exams',
            'model_name': 'Examination',
            'item_type': 'Examination',
            'module': 'Exams',
            'parent_attr': 'exam',
            'parent_type': 'Position / Level',
        },
        'subjectivequestionset': {
            'app_label': 'exams',
            'model_name': 'SubjectiveQuestionSet',
            'item_type': 'Subjective Question Set',
            'module': 'Exams',
            'parent_attr': 'level',
            'parent_type': 'Position / Level',
        },
        'questionset': {
            'app_label': 'exams',
            'model_name': 'QuestionSet',
            'item_type': 'Practice Question Set',
            'module': 'Exams',
            'parent_attr': 'exam',
            'parent_type': 'Position / Level',
        },
        'questioncollection': {
            'app_label': 'exams',
            'model_name': 'QuestionCollection',
            'item_type': 'Question Collection',
            'module': 'Exams',
            'parent_attr': None,
            'parent_type': None,
        },
        'question': {
            'app_label': 'exams',
            'model_name': 'Question',
            'item_type': 'Question',
            'module': 'Academic',
            'parent_attr': 'topic',
            'parent_type': 'Topic',
        },
        'examcategory': {
            'app_label': 'exams',
            'model_name': 'ExamCategory',
            'item_type': 'Exam Category',
            'module': 'Academic',
            'parent_attr': None,
            'parent_type': None,
        },
        'exam': {
            'app_label': 'exams',
            'model_name': 'Exam',
            'item_type': 'Position / Level',
            'module': 'Academic',
            'parent_attr': 'category',
            'parent_type': 'Exam Category',
        },
        'paper': {
            'app_label': 'exams',
            'model_name': 'Paper',
            'item_type': 'Paper',
            'module': 'Academic',
            'parent_attr': 'exam',
            'parent_type': 'Position / Level',
        },
        'subject': {
            'app_label': 'exams',
            'model_name': 'Subject',
            'item_type': 'Subject',
            'module': 'Academic',
            'parent_attr': 'paper',
            'parent_type': 'Paper',
        },
        'chapter': {
            'app_label': 'exams',
            'model_name': 'Chapter',
            'item_type': 'Chapter',
            'module': 'Academic',
            'parent_attr': 'subject',
            'parent_type': 'Subject',
        },
        'topic': {
            'app_label': 'exams',
            'model_name': 'Topic',
            'item_type': 'Topic',
            'module': 'Academic',
            'parent_attr': 'chapter',
            'parent_type': 'Chapter',
        },
        'course': {
            'app_label': 'courses',
            'model_name': 'Course',
            'item_type': 'Course',
            'module': 'Courses',
            'parent_attr': 'exam',
            'parent_type': 'Position / Level',
        },
        'studymaterial': {
            'app_label': 'notes',
            'model_name': 'StudyMaterial',
            'item_type': 'Study Material',
            'module': 'Notes',
            'parent_attr': 'subject',
            'parent_type': 'Subject',
        },
        'subscriptionplan': {
            'app_label': 'subscriptions',
            'model_name': 'SubscriptionPlan',
            'item_type': 'Subscription Package',
            'module': 'Packages',
            'parent_attr': None,
            'parent_type': None,
        },
        'product': {
            'app_label': 'marketplace',
            'model_name': 'Product',
            'item_type': 'Marketplace Listing',
            'module': 'Marketplace',
            'parent_attr': None,
            'parent_type': None,
        },
    }

    @classmethod
    def get_model_meta(cls, instance_or_model):
        model_name = instance_or_model._meta.model_name.lower()
        config = cls.MODEL_CONFIG.get(model_name)
        if config:
            return config
        return {
            'app_label': instance_or_model._meta.app_label,
            'model_name': instance_or_model._meta.object_name,
            'item_type': instance_or_model._meta.verbose_name.title(),
            'module': instance_or_model._meta.app_label.title(),
            'parent_attr': None,
            'parent_type': None,
        }

    @classmethod
    def check_dependencies(cls, instance) -> dict:
        """
        Deeply inspects an instance to classify dependent records as:
        - protected: historical records (attempts, student answers, submissions, orders, payments)
        - recoverable_children: child items that would be deactivated together
        - references: foreign key relationships
        """
        model_name = instance._meta.model_name.lower()
        counts = {}
        protected_reasons = []
        is_protected = False

        try:
            if model_name == 'examination':
                attempts_count = getattr(instance, 'attempts', None).count() if hasattr(instance, 'attempts') else 0
                counts['attempts'] = attempts_count
                counts['questions'] = getattr(instance, 'examination_questions', None).count() if hasattr(instance, 'examination_questions') else 0
                counts['requests'] = getattr(instance, 'student_requests', None).count() if hasattr(instance, 'student_requests') else 0
                if attempts_count > 0:
                    is_protected = True
                    protected_reasons.append(f"{attempts_count} student examination attempt(s) depend on this exam.")

            elif model_name == 'subjectivequestionset':
                exams_count = instance.examinations.count()
                counts['examinations'] = exams_count
                for ex in instance.examinations.all():
                    if hasattr(ex, 'attempts') and ex.attempts.exists():
                        is_protected = True
                        protected_reasons.append(f"Linked Examination #{ex.id} ('{ex.title}') has student attempts.")

            elif model_name == 'question':
                from exams.models import StudentAnswer, QuestionAttempt
                answers_count = StudentAnswer.objects.filter(question=instance).count()
                attempts_count = QuestionAttempt.objects.filter(question=instance).count()
                counts['student_answers'] = answers_count
                counts['practice_attempts'] = attempts_count
                counts['sets'] = instance.question_sets.count() if hasattr(instance, 'question_sets') else 0
                counts['exams'] = instance.examinations_set.count() if hasattr(instance, 'examinations_set') else 0

                if answers_count > 0 or attempts_count > 0:
                    is_protected = True
                    protected_reasons.append(f"Question has {answers_count} student exam answer(s) and {attempts_count} practice attempt(s).")

            elif model_name == 'examcategory':
                from exams.models import Exam, Examination
                counts['exams'] = instance.exams.count()
                counts['examinations'] = Examination.objects.filter(category=instance).count()
                if Examination.objects.filter(category=instance, attempts__isnull=False).exists():
                    is_protected = True
                    protected_reasons.append("Historical student exam attempts exist within this category.")

            elif model_name == 'exam':
                from exams.models import Examination
                counts['children'] = instance.children.count()
                counts['papers'] = instance.papers.count()
                counts['courses'] = instance.courses.count() if hasattr(instance, 'courses') else 0
                counts['examinations'] = Examination.objects.filter(exam=instance).count()
                if Examination.objects.filter(exam=instance, attempts__isnull=False).exists():
                    is_protected = True
                    protected_reasons.append("Historical student exam attempts exist for this position.")

            elif model_name == 'paper':
                counts['subjects'] = instance.subjects.count()

            elif model_name == 'subject':
                from exams.models import Examination, Question
                counts['chapters'] = instance.chapters.count()
                counts['questions'] = Question.objects.filter(subject=instance).count()
                counts['examinations'] = Examination.objects.filter(subject=instance).count()
                if Examination.objects.filter(subject=instance, attempts__isnull=False).exists():
                    is_protected = True
                    protected_reasons.append("Historical student exam attempts exist for this subject.")

            elif model_name == 'chapter':
                from exams.models import Question
                counts['topics'] = instance.topics.count()
                counts['questions'] = Question.objects.filter(chapter=instance).count()

            elif model_name == 'topic':
                from exams.models import Question, UserTopicProgress
                counts['questions'] = Question.objects.filter(topic=instance).count()
                progress_count = UserTopicProgress.objects.filter(topic=instance).count()
                counts['student_progress'] = progress_count
                if progress_count > 0:
                    is_protected = True
                    protected_reasons.append(f"{progress_count} student learning progress record(s) exist for this topic.")

            elif model_name == 'course':
                from courses.models import Enrollment, CourseApplication
                enrollments_count = instance.enrollments.count()
                applications_count = instance.course_applications.count() if hasattr(instance, 'course_applications') else 0
                counts['enrollments'] = enrollments_count
                counts['applications'] = applications_count
                if enrollments_count > 0:
                    is_protected = True
                    protected_reasons.append(f"{enrollments_count} active or historical student enrollment(s) exist in this course.")

            elif model_name == 'subscriptionplan':
                from subscriptions.models import Subscription, SubscriptionPayment
                subs_count = Subscription.objects.filter(plan=instance).count()
                payments_count = SubscriptionPayment.objects.filter(plan=instance).count()
                counts['subscriptions'] = subs_count
                counts['payments'] = payments_count
                if subs_count > 0 or payments_count > 0:
                    is_protected = True
                    protected_reasons.append(f"Package has {subs_count} subscription(s) and {payments_count} payment record(s).")

            elif model_name == 'studymaterial':
                counts['collections'] = instance.collections.count() if hasattr(instance, 'collections') else 0

        except Exception as e:
            logger.warning(f"Error checking dependencies for {instance}: {e}")

        total_dependencies = sum(counts.values())

        return {
            'counts': counts,
            'total_dependencies': total_dependencies,
            'is_protected': is_protected,
            'protection_reasons': protected_reasons,
            'can_soft_delete': True, # Soft delete is always safe!
            'can_permanent_delete': not is_protected,
        }

    @classmethod
    @transaction.atomic
    def soft_delete(cls, instance, user, reason='') -> TrashItem:
        """
        Safely moves an instance into the Trash.
        Marks it as deleted/archived without running physical database CASCADE.
        """
        meta = cls.get_model_meta(instance)
        dep_info = cls.check_dependencies(instance)

        title = str(getattr(instance, 'title', None) or getattr(instance, 'name', None) or str(instance))
        object_id = str(instance.pk)

        # Snapshot essential fields for preview/restore
        snapshot = {
            'id': instance.pk,
            'title': title,
            'model': meta['model_name'],
            'app_label': meta['app_label'],
            'dependencies': dep_info['counts'],
        }

        # Parent links
        if meta.get('parent_attr') and hasattr(instance, meta['parent_attr']):
            parent = getattr(instance, meta['parent_attr'])
            if parent:
                snapshot['parent_id'] = parent.pk
                snapshot['parent_title'] = str(getattr(parent, 'title', None) or getattr(parent, 'name', None) or str(parent))
                snapshot['parent_type'] = meta.get('parent_type')

        # Set soft-delete state on model
        if hasattr(instance, 'is_deleted'):
            instance.is_deleted = True
            instance.deleted_at = timezone.now()
        if hasattr(instance, 'is_active'):
            instance.is_active = False
        if hasattr(instance, 'status'):
            # If status has 'archived' or 'inactive', set it
            status_choices = [c[0] for c in getattr(instance, 'STATUS_CHOICES', [])]
            if 'archived' in status_choices:
                instance.status = 'archived'
            elif 'inactive' in status_choices:
                instance.status = 'inactive'

        instance.save()

        # Create or update TrashItem
        trash_item, _ = TrashItem.objects.update_or_create(
            app_label=meta['app_label'],
            model_name=meta['model_name'].lower(),
            object_id=object_id,
            defaults={
                'title': title,
                'item_type': meta['item_type'],
                'module': meta['module'],
                'deleted_by': user if user and user.is_authenticated else None,
                'deleted_at': timezone.now(),
                'reason': reason or 'Deleted by Admin',
                'details': snapshot,
                'is_restored': False,
                'restored_at': None,
                'restored_by': None,
                'is_permanent_deleted': False,
                'is_protected': dep_info['is_protected'],
                'protection_reasons': dep_info['protection_reasons'],
            }
        )

        # Write canonical AuditLog
        AuditLog.objects.create(
            actor=user if user and user.is_authenticated else None,
            action='DELETE',
            entity_type=meta['model_name'].lower(),
            entity_id=object_id,
            details={
                'trash_item_id': trash_item.id,
                'title': title,
                'item_type': meta['item_type'],
                'module': meta['module'],
                'reason': reason,
                'dependencies': dep_info['counts'],
                'is_protected': dep_info['is_protected'],
            }
        )

        return trash_item

    @classmethod
    @transaction.atomic
    def restore(cls, trash_item: TrashItem, user, restore_parents: bool = False) -> dict:
        """
        Restores a soft-deleted item from Trash back to active state.
        Validates parent hierarchy first to prevent orphaned records.
        """
        try:
            model_class = apps.get_model(trash_item.app_label, trash_item.model_name)
            instance = model_class.objects.filter(pk=trash_item.object_id).first()
        except LookupError:
            raise ValidationError(f"Model '{trash_item.app_label}.{trash_item.model_name}' not found.")

        if not instance:
            raise ValidationError(f"Database record for {trash_item.item_type} #{trash_item.object_id} no longer exists.")

        meta = cls.get_model_meta(instance)
        restored_chain = []

        # Check if parent is in trash
        if meta.get('parent_attr') and hasattr(instance, meta['parent_attr']):
            parent = getattr(instance, meta['parent_attr'])
            if parent:
                parent_meta = cls.get_model_meta(parent)
                parent_trash = TrashItem.objects.filter(
                    app_label=parent_meta['app_label'],
                    model_name=parent_meta['model_name'].lower(),
                    object_id=str(parent.pk),
                    is_restored=False,
                    is_permanent_deleted=False,
                ).first()

                if parent_trash:
                    if not restore_parents:
                        return {
                            'success': False,
                            'needs_parent_restoration': True,
                            'parent_id': parent.pk,
                            'parent_type': parent_meta['item_type'],
                            'parent_title': parent_trash.title,
                            'message': f"Cannot restore {trash_item.item_type} because its parent {parent_meta['item_type']} ('{parent_trash.title}') is still in Trash.",
                        }
                    else:
                        # Recursively restore parent first
                        parent_res = cls.restore(parent_trash, user, restore_parents=True)
                        if parent_res.get('success'):
                            restored_chain.append(f"{parent_meta['item_type']}: {parent_trash.title}")

        # Restore instance
        if hasattr(instance, 'is_deleted'):
            instance.is_deleted = False
            instance.deleted_at = None
        if hasattr(instance, 'is_active'):
            instance.is_active = True
        if hasattr(instance, 'status'):
            status_choices = [c[0] for c in getattr(instance, 'STATUS_CHOICES', [])]
            if 'active' in status_choices:
                instance.status = 'active'
            elif 'draft' in status_choices:
                instance.status = 'draft'
            elif 'ACTIVE' in status_choices:
                instance.status = 'ACTIVE'

        instance.save()

        # Update TrashItem
        trash_item.is_restored = True
        trash_item.restored_at = timezone.now()
        trash_item.restored_by = user if user and user.is_authenticated else None
        trash_item.save(update_fields=['is_restored', 'restored_at', 'restored_by'])

        # AuditLog
        AuditLog.objects.create(
            actor=user if user and user.is_authenticated else None,
            action='RESTORE',
            entity_type=meta['model_name'],
            entity_id=str(instance.pk),
            details={
                'trash_item_id': trash_item.id,
                'title': trash_item.title,
                'restored_parents': restored_chain,
            }
        )

        return {
            'success': True,
            'message': f"{trash_item.item_type} '{trash_item.title}' has been successfully restored.",
            'restored_chain': restored_chain,
        }

    @classmethod
    @transaction.atomic
    def permanent_delete(cls, trash_item: TrashItem, user, confirmation_text: str) -> dict:
        """
        Permanently destroys an item from the database.
        Strictly requires Super Admin role, exact confirmation text 'DELETE PERMANENTLY',
        and non-protected status.
        """
        if not user or not user.is_authenticated or user.role != 'super-admin':
            raise ValidationError("Permanent deletion requires Super Admin authorization.")

        if confirmation_text.strip() != 'DELETE PERMANENTLY':
            raise ValidationError("Confirmation text must exactly match 'DELETE PERMANENTLY'.")

        try:
            model_class = apps.get_model(trash_item.app_label, trash_item.model_name)
            instance = model_class.objects.filter(pk=trash_item.object_id).first()
        except LookupError:
            raise ValidationError("Target model could not be resolved.")

        # Re-check live dependencies
        if instance:
            dep_info = cls.check_dependencies(instance)
            if dep_info['is_protected']:
                trash_item.is_protected = True
                trash_item.protection_reasons = dep_info['protection_reasons']
                trash_item.save(update_fields=['is_protected', 'protection_reasons'])
                raise ValidationError(
                    f"Permanent deletion rejected: {'; '.join(dep_info['protection_reasons'])}"
                )

            # Physically delete
            instance.delete()

        # Update TrashItem
        trash_item.is_permanent_deleted = True
        trash_item.permanent_deleted_at = timezone.now()
        trash_item.permanent_deleted_by = user
        trash_item.save(update_fields=['is_permanent_deleted', 'permanent_deleted_at', 'permanent_deleted_by'])

        # AuditLog
        AuditLog.objects.create(
            actor=user,
            action='PERMANENT_DELETE',
            entity_type=trash_item.model_name,
            entity_id=trash_item.object_id,
            details={
                'trash_item_id': trash_item.id,
                'title': trash_item.title,
                'item_type': trash_item.item_type,
                'module': trash_item.module,
            }
        )

        return {
            'success': True,
            'message': f"{trash_item.item_type} '{trash_item.title}' has been permanently deleted.",
        }
