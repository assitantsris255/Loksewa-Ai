from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from exams.models import Examination, ExaminationRequest, SubjectiveQuestionSet


class SubjectiveExamAssignmentService:
    """Centralized assignment flow for subjective live exam requests.

    The project already has the canonical `ExaminationRequest` and `Examination`
    models. This service keeps all automatic/manual assignment logic in one place
    so that both the admin and queued fallback paths behave identically.
    """

    @staticmethod
    def get_eligible_question_sets(request):
        if request.request_type != 'subjective_live':
            return SubjectiveQuestionSet.objects.none()

        qs = SubjectiveQuestionSet.objects.filter(status='active').select_related(
            'exam_category', 'level', 'course', 'subject', 'created_by'
        )

        if request.academic_exam_id:
            qs = qs.filter(level_id=request.academic_exam_id, exam_category_id=request.academic_exam.category_id)
        else:
            qs = qs.none()

        if request.course_id:
            qs = qs.filter(course_id=request.course_id)
        if request.subject_id:
            qs = qs.filter(subject_id=request.subject_id)

        return qs.order_by('-created_at')

    @staticmethod
    def assign_subjective_exam(request, mode='auto', question_set_id=None):
        if not isinstance(request, ExaminationRequest):
            request = ExaminationRequest.objects.select_related(
                'academic_exam', 'course', 'subject', 'topic'
            ).get(pk=request)

        if request.request_type != 'subjective_live':
            return None

        if request.examination_id:
            return request.examination

        with transaction.atomic():
            locked_request = ExaminationRequest.objects.select_for_update().get(pk=request.pk)
            if locked_request.examination_id:
                return locked_request.examination

            if locked_request.status != 'pending':
                return locked_request.examination

            eligible_sets = SubjectiveExamAssignmentService.get_eligible_question_sets(locked_request)
            if question_set_id is not None:
                eligible_sets = eligible_sets.filter(pk=question_set_id)
            elif mode == 'auto':
                eligible_sets = eligible_sets.order_by('?')

            selected_set = eligible_sets.first()
            if not selected_set:
                return None

            file_size = 0
            if selected_set.pdf_file:
                try:
                    file_size = selected_set.pdf_file.size
                except Exception:
                    file_size = 0

            exam = Examination.objects.create(
                title=selected_set.title,
                description=selected_set.description,
                exam_type='subjective',
                objective_category=None,
                category=locked_request.academic_exam.category,
                exam=locked_request.academic_exam,
                course=locked_request.course or selected_set.course,
                subject=locked_request.subject or selected_set.subject,
                topic=locked_request.topic,
                subjective_question_set=selected_set,
                instructions='',
                total_questions=selected_set.question_count or 0,
                time_limit=selected_set.duration_minutes or 90,
                total_marks=selected_set.total_marks or 0,
                passing_marks=0,
                marks_per_question=1,
                status='published',
                question_paper_pdf=selected_set.pdf_file,
                question_paper_page_count=1,
                question_paper_file_size=file_size,
                created_by=selected_set.created_by,
            )

            locked_request.examination = exam
            locked_request.status = 'approved'
            locked_request.reviewed_at = timezone.now()
            locked_request.rejection_reason = ''
            locked_request.save(update_fields=['examination', 'status', 'reviewed_at', 'rejection_reason', 'updated_at'])

            request.examination = exam
            request.examination_id = exam.id
            request.status = 'approved'
            request.reviewed_at = locked_request.reviewed_at
            request.rejection_reason = ''
            return exam
