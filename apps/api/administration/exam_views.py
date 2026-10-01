from rest_framework import viewsets, status, serializers, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Avg
from django.utils import timezone
import copy

from exams.models import (
    Exam as AcademicExam,
    ExamCategory,
    Examination,
    ExaminationAttempt,
    ExaminationQuestion,
    ExaminationRequest,
    QuestionSet,
    Subject,
    SubjectiveQuestionSet,
    Topic,
)
from courses.models import Course
from exams.assignment_service import SubjectiveExamAssignmentService
from exams.selection_service import QuestionSelectionService
from exams.student_serializers import ExaminationRequestSerializer
from .exam_serializers import ExaminationSerializer, ExaminationAttemptSerializer
from .examination_question_views import ExaminationQuestionMixin
# rest_framework.permissions.IsAdminUser checks Django's is_staff flag, which
# this app's admin accounts don't necessarily have - every other admin
# viewset here gates on role (admin/super-admin) via this app's own
# IsAdminUser instead. Using the DRF one 403'd every admin whose account
# wasn't separately flagged is_staff, silently blocking exam creation.
from .permissions import IsAdminUser, IsEvaluatorUser


from rest_framework.pagination import PageNumberPagination


class SubjectiveQuestionSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class SubjectiveQuestionSetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='exam_category.name', read_only=True)
    category_id = serializers.IntegerField(source='exam_category_id', read_only=True)
    level_name = serializers.CharField(source='level.name', read_only=True)
    level_id = serializers.IntegerField(read_only=True)
    course_name = serializers.CharField(source='course.title', read_only=True, allow_null=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True, allow_null=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True, allow_null=True)
    usage_count = serializers.IntegerField(read_only=True)
    last_used_at = serializers.DateTimeField(read_only=True)
    file_name = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()

    def get_file_name(self, obj):
        try:
            if not obj.pdf_file:
                return None
            basename = obj.pdf_file.name.replace('\\', '/').split('/')[-1]
            if '__' in basename:
                parts = basename.split('__', 1)
                return parts[1] if len(parts) > 1 else basename
            return basename
        except Exception:
            return None

    def get_file_size(self, obj):
        try:
            return obj.pdf_file.size if obj.pdf_file else 0
        except Exception:
            return 0

    class Meta:
        model = SubjectiveQuestionSet
        fields = [
            'id', 'title', 'description', 'pdf_file', 'file_name', 'file_size',
            'exam_category', 'category_id', 'category_name',
            'level', 'level_id', 'level_name',
            'course', 'course_name',
            'subject', 'subject_name',
            'duration_minutes', 'total_marks', 'question_count', 'status',
            'created_by', 'created_by_name', 'created_at', 'updated_at', 'usage_count', 'last_used_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_by_name', 'created_at', 'updated_at', 'usage_count', 'last_used_at']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        instance = SubjectiveQuestionSet(**validated_data)
        instance.full_clean()
        instance.save()
        return instance

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.full_clean()
        instance.save()
        return instance


class SubjectiveQuestionSetViewSet(viewsets.ModelViewSet):
    queryset = SubjectiveQuestionSet.objects.select_related(
        'exam_category', 'level', 'course', 'subject', 'created_by'
    ).order_by('-created_at')
    serializer_class = SubjectiveQuestionSetSerializer
    pagination_class = SubjectiveQuestionSetPagination
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description', 'subject__name', 'level__name', 'exam_category__name']
    filterset_fields = {
        'status': ['exact'],
        'exam_category': ['exact'],
        'level': ['exact'],
        'subject': ['exact', 'isnull'],
        'course': ['exact', 'isnull'],
    }
    ordering_fields = ['created_at', 'total_marks', 'duration_minutes', 'title']

    @action(detail=True, methods=['post'], url_path='archive')
    def archive(self, request, pk=None):
        instance = self.get_object()
        instance.status = 'archived'
        instance.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='activate')
    def activate(self, request, pk=None):
        instance = self.get_object()
        instance.status = 'active'
        instance.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='assign')
    def assign(self, request, pk=None):
        request_id = request.data.get('request_id')
        if request_id is None:
            return Response({'detail': 'request_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            exam_request = ExaminationRequest.objects.select_related(
                'academic_exam', 'course', 'subject', 'topic'
            ).get(pk=request_id, request_type='subjective_live')
        except ExaminationRequest.DoesNotExist:
            return Response({'detail': 'Pending subjective request not found.'}, status=status.HTTP_404_NOT_FOUND)

        exam = SubjectiveExamAssignmentService.assign_subjective_exam(
            exam_request,
            mode='manual',
            question_set_id=pk,
        )
        if exam is None:
            return Response({'detail': 'No active eligible subjective question set was found for this request.'}, status=status.HTTP_409_CONFLICT)
        return Response({
            'id': exam.id,
            'title': exam.title,
            'subjective_question_set_id': exam.subjective_question_set_id,
            'request_id': exam_request.id,
            'status': exam.status,
        }, status=status.HTTP_200_OK)


class ExaminationViewSet(ExaminationQuestionMixin, viewsets.ModelViewSet):
    queryset = Examination.objects.all().select_related('category', 'exam', 'subject', 'topic', 'question_set').order_by('-created_at')
    serializer_class = ExaminationSerializer
    permission_classes = [IsAdminUser]

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError
        from django.db import transaction

        request_id = serializer.validated_data.pop('request_id', None)
        with transaction.atomic():
            examination = serializer.save(created_by=self.request.user)
            if request_id:
                exam_request = ExaminationRequest.objects.select_for_update().filter(
                    pk=request_id, request_type='subjective_live', status='pending'
                ).first()
                if not exam_request:
                    raise ValidationError({'request_id': 'Pending subjective exam request not found.'})
                if examination.exam_type != 'subjective' or examination.exam_id != exam_request.academic_exam_id:
                    raise ValidationError({'request_id': 'The draft must be a subjective exam for the requested academic exam.'})
                if exam_request.course_id and examination.course_id != exam_request.course_id:
                    raise ValidationError({'request_id': 'The draft course must match the student request.'})
                if exam_request.subject_id and examination.subject_id != exam_request.subject_id:
                    raise ValidationError({'request_id': 'The draft subject must match the student request.'})
                if exam_request.topic_id and examination.topic_id != exam_request.topic_id:
                    raise ValidationError({'request_id': 'The draft topic must match the student request.'})
                if exam_request.examination_id:
                    raise ValidationError({'request_id': 'This request is already linked to an examination.'})
                exam_request.examination = examination
                exam_request.save(update_fields=['examination', 'updated_at'])

    @action(detail=False, methods=['post'], url_path='generate-subjective-live')
    def generate_subjective_live(self, request):
        import uuid
        from django.core.exceptions import ValidationError
        from django.core.files.base import ContentFile
        from django.db import IntegrityError, transaction
        from django.utils import timezone
        from django.utils.dateparse import parse_datetime
        from exams.subjective_paper_generator import build_subjective_paper_pdf

        try:
            generation_key = uuid.UUID(str(request.data.get('generation_key', '')))
            raw_exam_id = request.data.get('exam') or request.data.get('exam_id')
            academic_exam_id = int(raw_exam_id) if raw_exam_id else None
            question_count = int(request.data.get('question_count'))
            duration = int(request.data.get('time_limit', 90))
            request_id = int(request.data['request_id']) if request.data.get('request_id') else None
        except (TypeError, ValueError, AttributeError):
            return Response({'detail': 'generation_key and question_count are required, with valid exam/request IDs.'}, status=status.HTTP_400_BAD_REQUEST)
        if not 1 <= question_count <= 200 or not 1 <= duration <= 1440:
            return Response({'detail': 'Question count must be 1-200 and duration must be 1-1440 minutes.'}, status=status.HTTP_400_BAD_REQUEST)

        subjective_request = None
        if request_id:
            subjective_request = ExaminationRequest.objects.select_related(
                'academic_exam', 'course', 'subject', 'topic'
            ).filter(pk=request_id, request_type='subjective_live', status='pending').first()
            if not subjective_request:
                return Response({'detail': 'Pending subjective exam request not found.'}, status=status.HTTP_404_NOT_FOUND)
            if academic_exam_id and academic_exam_id != subjective_request.academic_exam_id:
                return Response({'detail': 'The selected academic exam does not match this request.'}, status=status.HTTP_400_BAD_REQUEST)
            academic_exam_id = subjective_request.academic_exam_id
        if academic_exam_id is None:
            return Response({'detail': 'exam or request_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        academic_exam = AcademicExam.objects.select_related('category').filter(pk=academic_exam_id, is_active=True).first()
        if not academic_exam:
            return Response({'detail': 'An active academic exam is required.'}, status=status.HTTP_400_BAD_REQUEST)

        existing = None
        if subjective_request and subjective_request.examination_id:
            existing = Examination.objects.filter(pk=subjective_request.examination_id).first()
            if not existing or existing.exam_type != 'subjective' or existing.status != 'draft':
                return Response({'detail': 'The request is already linked to a non-draft examination.'}, status=status.HTTP_409_CONFLICT)
            generation_key = existing.generation_key
        else:
            existing = Examination.objects.filter(generation_key=generation_key).first()
        regenerate = str(request.data.get('regenerate', '')).lower() in ('1', 'true', 'yes')
        if existing:
            if existing.created_by_id != request.user.id or existing.exam_type != 'subjective':
                return Response({'detail': 'This generation key is not available to this admin.'}, status=status.HTTP_409_CONFLICT)
            if existing.status != 'draft':
                return Response({'detail': 'Published or reviewed papers cannot be regenerated.'}, status=status.HTTP_409_CONFLICT)
            if not regenerate:
                if subjective_request:
                    with transaction.atomic():
                        locked_request = ExaminationRequest.objects.select_for_update().get(pk=subjective_request.pk)
                        if locked_request.status != 'pending':
                            return Response({'detail': 'This subjective request is no longer pending.'}, status=status.HTTP_409_CONFLICT)
                        locked_request.examination = existing
                        locked_request.save(update_fields=['examination', 'updated_at'])
                return Response({
                    'id': existing.id, 'title': existing.title, 'status': existing.status,
                    'total_questions': existing.total_questions, 'total_marks': existing.total_marks,
                    'has_question_paper': bool(existing.question_paper_pdf), 'reused': True,
                }, status=status.HTTP_200_OK)

        subject_id = request.data.get('subject') or (subjective_request.subject_id if subjective_request else None)
        subject = None
        if subject_id:
            subject = Subject.objects.filter(pk=subject_id, paper__exam_id=academic_exam.id).first()
            if not subject:
                return Response({'detail': 'Subject must belong to the selected academic exam.'}, status=status.HTTP_400_BAD_REQUEST)

        topic_id = request.data.get('topic') or (subjective_request.topic_id if subjective_request else None)
        topic = None
        if topic_id:
            topic = Topic.objects.filter(pk=topic_id, chapter__subject__paper__exam_id=academic_exam.id).first()
            if not topic or (subject and topic.chapter.subject_id != subject.id):
                return Response({'detail': 'Topic must belong to the selected exam and subject.'}, status=status.HTTP_400_BAD_REQUEST)

        course = None
        course_id = request.data.get('course') or (subjective_request.course_id if subjective_request else None)
        if course_id:
            from courses.models import Course
            course = Course.objects.filter(pk=course_id, exam_id=academic_exam.id, status='published').first()
            if not course:
                return Response({'detail': 'Course must be published and belong to the selected academic exam.'}, status=status.HTTP_400_BAD_REQUEST)

        question_type = str(request.data.get('question_type') or 'subjective').strip().lower()
        allowed_question_types = {'subjective', 'objective', 'mixed', 'mcq', 'true_false'}
        if question_type not in allowed_question_types:
            return Response({'detail': 'Unsupported question type for a subjective examination.'}, status=status.HTTP_400_BAD_REQUEST)
        selection_type = None if question_type == 'mixed' else question_type
        excluded_ids = list(existing.examination_questions.values_list('question_id', flat=True)) if existing and regenerate else []
        selection = QuestionSelectionService().select(
            exam_id=academic_exam.id,
            subject_id=subject.id if subject else None,
            topic_id=topic.id if topic else None,
            question_type=selection_type,
            count=question_count,
            randomize=True,
            exclude_ids=excluded_ids,
        )
        if not selection['satisfied']:
            return Response({
                'detail': 'Not enough approved questions are available for this paper.',
                'requested': selection['requested'], 'available': selection['available'],
                'selected': selection['selected'], 'warnings': selection['warnings'],
            }, status=status.HTTP_409_CONFLICT)

        questions = selection['questions']
        total_marks = sum(question.marks or 0 for question in questions)
        title = str(request.data.get('title') or f'{academic_exam.name} Subjective Live Exam').strip()
        if not title:
            return Response({'detail': 'A title is required.'}, status=status.HTTP_400_BAD_REQUEST)
        start_value = request.data.get('start_time')
        end_value = request.data.get('end_time')
        start_time = parse_datetime(start_value) if start_value else None
        end_time = parse_datetime(end_value) if end_value else None
        if (start_value and start_time is None) or (end_value and end_time is None):
            return Response({'detail': 'Start and end times must be valid ISO-8601 datetimes.'}, status=status.HTTP_400_BAD_REQUEST)
        if start_time and timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time)
        if end_time and timezone.is_naive(end_time):
            end_time = timezone.make_aware(end_time)
        if start_time and end_time and end_time <= start_time:
            return Response({'detail': 'The end time must come after the start time.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            pdf_bytes = build_subjective_paper_pdf(
                title=title,
                position_name=academic_exam.name,
                subject_name=subject.name if subject else '',
                course_name=course.title if course else '',
                duration_minutes=duration,
                total_marks=total_marks,
                start_time=start_time,
                instructions=str(request.data.get('instructions') or '').strip(),
                questions=questions,
            )
        except ValidationError as exc:
            return Response({'detail': '; '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        old_file = None
        new_storage = None
        new_file_name = None
        try:
            with transaction.atomic():
                locked_request = None
                if subjective_request:
                    locked_request = ExaminationRequest.objects.select_for_update().get(pk=subjective_request.pk)
                    if locked_request.status != 'pending':
                        return Response({'detail': 'This subjective request is no longer pending.'}, status=status.HTTP_409_CONFLICT)
                    expected_exam_id = existing.id if existing else None
                    if locked_request.examination_id and locked_request.examination_id != expected_exam_id:
                        return Response({'detail': 'This request is already linked to another examination.'}, status=status.HTTP_409_CONFLICT)
                if existing:
                    examination = Examination.objects.select_for_update().get(pk=existing.pk)
                    if examination.status != 'draft':
                        return Response({'detail': 'Only draft papers can be regenerated.'}, status=status.HTTP_409_CONFLICT)
                    old_file = examination.question_paper_pdf.name if examination.question_paper_pdf else None
                    examination.examination_questions.all().delete()
                else:
                    examination = Examination.objects.create(
                        generation_key=generation_key,
                        title=title,
                        exam_type='subjective',
                        objective_category=None,
                        category=academic_exam.category,
                        exam=academic_exam,
                        course=course,
                        subject=subject,
                        topic=topic,
                        instructions=str(request.data.get('instructions') or '').strip(),
                        total_questions=len(questions),
                        time_limit=duration,
                        total_marks=total_marks,
                        passing_marks=0,
                        marks_per_question=1,
                        start_time=start_time,
                        end_time=end_time,
                        randomize_questions=False,
                        status='draft',
                        created_by=request.user,
                    )

                examination.title = title
                examination.course = course
                examination.subject = subject
                examination.topic = topic
                examination.instructions = str(request.data.get('instructions') or '').strip()
                examination.total_questions = len(questions)
                examination.time_limit = duration
                examination.total_marks = total_marks
                examination.start_time = start_time
                examination.end_time = end_time
                examination.question_paper_pdf.save(
                    f'subjective-exam-{generation_key}-{uuid.uuid4().hex}.pdf',
                    ContentFile(pdf_bytes),
                    save=False,
                )
                new_storage = examination.question_paper_pdf.storage
                new_file_name = examination.question_paper_pdf.name
                examination.question_paper_page_count = max(1, pdf_bytes.count(b'/Type /Page'))
                examination.question_paper_file_size = len(pdf_bytes)
                examination.save()
                ExaminationQuestion.objects.bulk_create([
                    ExaminationQuestion(
                        examination=examination,
                        question=question,
                        order=index,
                        marks=question.marks or 1,
                    )
                    for index, question in enumerate(questions, start=1)
                ])
                if locked_request:
                    locked_request.examination = examination
                    locked_request.save(update_fields=['examination', 'updated_at'])
                if old_file:
                    storage = examination.question_paper_pdf.storage
                    transaction.on_commit(lambda: storage.delete(old_file))
        except IntegrityError:
            if new_storage and new_file_name:
                new_storage.delete(new_file_name)
            same_request = Examination.objects.filter(generation_key=generation_key).first()
            if same_request:
                return Response({
                    'id': same_request.id, 'title': same_request.title, 'status': same_request.status,
                    'total_questions': same_request.total_questions, 'total_marks': same_request.total_marks,
                    'has_question_paper': bool(same_request.question_paper_pdf), 'reused': True,
                }, status=status.HTTP_200_OK)
            raise
        except Exception:
            if new_storage and new_file_name:
                new_storage.delete(new_file_name)
            raise

        return Response({
            'id': examination.id,
            'title': examination.title,
            'status': examination.status,
            'total_questions': examination.total_questions,
            'total_marks': examination.total_marks,
            'time_limit': examination.time_limit,
            'has_question_paper': bool(examination.question_paper_pdf),
            'question_paper_page_count': examination.question_paper_page_count,
            'question_paper_file_size': examination.question_paper_file_size,
            'reused': False,
        }, status=status.HTTP_201_CREATED if not existing else status.HTTP_200_OK)

    def perform_update(self, serializer):
        exam = self.get_object()
        was_published = exam.status == 'published'
        old_start = exam.start_time
        old_end = exam.end_time

        instance = serializer.save()

        if was_published and instance.status == 'published' and (
            instance.start_time != old_start or instance.end_time != old_end
        ):
            from core.notification_service import NotificationService
            NotificationService.notify_students_exam_update(instance, 'schedule_changed')

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        exam = self.get_object()
        new_exam = copy.copy(exam)
        new_exam.pk = None
        new_exam.title = f"Copy of {exam.title}"
        new_exam.status = 'draft'
        new_exam.created_by = request.user
        new_exam.save()
        
        # Copy eligibility rules
        for rule in exam.eligibility_rules.all():
            rule.pk = None
            rule.examination = new_exam
            rule.save()
            
        serializer = self.get_serializer(new_exam)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        exam = self.get_object()
        
        # Questions come from the canonical ExaminationQuestion assignment, not
        # from a QuestionSet — the builder attaches them directly.
        assigned = exam.examination_questions.count()

        errors = []
        if not exam.title or not exam.title.strip():
            errors.append("The exam needs a title.")
        if not exam.category_id or not exam.exam_id:
            errors.append("Academic targeting is incomplete: choose a category and a position.")
        is_subjective_pdf = exam.exam_type == 'subjective' and bool(exam.question_paper_pdf)
        if exam.exam_type == 'subjective':
            if not is_subjective_pdf and assigned < 1:
                errors.append("Assign or upload a valid Subjective Question Paper (PDF) before publishing.")
            elif exam.question_paper_pdf:
                try:
                    if not exam.question_paper_pdf.storage.exists(exam.question_paper_pdf.name):
                        errors.append("The assigned question paper PDF file could not be found in storage.")
                except Exception:
                    pass
        elif assigned < 1:
            errors.append("Add at least one question before publishing.")
        if exam.exam_type == 'subject' and exam.topic_id:
            valid_assigned = exam.examination_questions.filter(
                question__topic_id=exam.topic_id,
                question__status='approved',
                question__question_type__in=('mcq', 'true_false'),
            ).count()
            if valid_assigned != assigned:
                errors.append("Every Topicwise Test question must be approved, objective, and belong to the selected topic.")
            if exam.total_questions != assigned:
                errors.append("The Topicwise Test question count must match its assigned questions.")
            if not exam.course_id:
                errors.append("Choose a course before publishing this Topicwise Test.")
        if exam.time_limit < 1:
            errors.append("Time Limit must be greater than 0.")
        if exam.total_marks < 1:
            errors.append("Total Marks must be greater than 0.")
        if exam.passing_marks and exam.passing_marks > exam.total_marks:
            errors.append("Passing Marks cannot exceed Total Marks.")
        if exam.start_time and exam.end_time and exam.end_time <= exam.start_time:
            errors.append("The end time must come after the start time.")
        if not is_subjective_pdf and exam.total_questions and assigned < exam.total_questions:
            errors.append(
                f"This exam targets {exam.total_questions} question(s) but only {assigned} "
                f"are assigned."
            )

        if errors:
            return Response(
                {"error": "Cannot publish exam.", "details": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 'published' is the only valid published state in Examination.STATUS_CHOICES;
        # scheduling is expressed by start_time/end_time, not by extra statuses.
        exam.status = 'published'
        exam.save(update_fields=['status', 'updated_at'])

        from exams.models import ExaminationRequest
        now = timezone.now()
        ExaminationRequest.objects.filter(
            examination=exam,
            request_type='subjective_live',
            status='pending',
        ).update(
            status='approved',
            reviewed_by=request.user,
            reviewed_at=now,
            rejection_reason='',
            updated_at=now,
        )

        from core.notification_service import NotificationService
        NotificationService.notify_students_exam_update(exam, 'published')

        serializer = self.get_serializer(exam)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='assign-subjective-set')
    def assign_subjective_set(self, request, pk=None):
        examination = self.get_object()
        if examination.status == 'published':
            return Response({'detail': 'Cannot modify paper on an already published examination.'}, status=status.HTTP_400_BAD_REQUEST)

        question_set_id = request.data.get('question_set_id')
        if not question_set_id:
            return Response({'detail': 'question_set_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        from exams.models import SubjectiveQuestionSet
        try:
            qset = SubjectiveQuestionSet.objects.get(pk=question_set_id, status='active')
        except SubjectiveQuestionSet.DoesNotExist:
            return Response({'detail': 'Active subjective question set not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not qset.pdf_file:
            return Response({'detail': 'The selected question set does not have an attached PDF file.'}, status=status.HTTP_400_BAD_REQUEST)

        examination.subjective_question_set = qset
        examination.question_paper_pdf = qset.pdf_file
        examination.question_paper_page_count = 1
        examination.question_paper_file_size = qset.pdf_file.size if qset.pdf_file else 0
        if qset.duration_minutes:
            examination.time_limit = qset.duration_minutes
        if qset.total_marks:
            examination.total_marks = qset.total_marks
        if qset.question_count:
            examination.total_questions = qset.question_count
        examination.save()

        serializer = self.get_serializer(examination)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        exam = self.get_object()
        # Archiving a still-upcoming/live exam is a real cancellation the
        # students it was visible to need to hear about. Archiving one that
        # already finished is routine cleanup — computed_status is 'COMPLETED'
        # by then, so no notification fires.
        was_cancellation = exam.status == 'published' and exam.computed_status in ('UPCOMING', 'LIVE')
        exam.status = 'archived'
        exam.save()

        if was_cancellation:
            from core.notification_service import NotificationService
            NotificationService.notify_students_exam_update(exam, 'cancelled')

        serializer = self.get_serializer(exam)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        """Student's-eye view of the exam, built from its assigned questions."""
        exam = self.get_object()

        rows = exam.examination_questions.select_related('question').order_by('order', 'id')
        if not rows.exists():
            return Response(
                {"error": "This exam has no questions assigned yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Correct answers are deliberately omitted — this mirrors what a student sees.
        questions = [{
            'id': row.question.id,
            'question_id': row.question.question_id,
            'text': row.question.text,
            'question_type': row.question.question_type,
            'difficulty': row.question.difficulty,
            'option_a': row.question.option_a,
            'option_b': row.question.option_b,
            'option_c': row.question.option_c,
            'option_d': row.question.option_d,
            'marks': row.marks,
            'order': row.order,
        } for row in rows]

        return Response({
            'title': exam.title,
            'instructions': exam.instructions,
            'time_limit': exam.time_limit,
            'total_marks': exam.total_marks,
            'total_questions': len(questions),
            'questions': questions,
        })


    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        from exams.analytics_utils import build_examination_analytics
        exam = self.get_object()
        return Response(build_examination_analytics(exam))

    @action(detail=True, methods=['get'])
    def results(self, request, pk=None):
        from django.core.paginator import Paginator
        from django.db.models import Count, Q, F, Window
        from django.db.models.functions import Rank
        
        exam = self.get_object()
        
        # Using Window function for rank
        # A subjective answer has no selected_option even when the student
        # wrote a full response - answer_text is what "answered" means there,
        # so "skipped" must check both or every subjective submission in a
        # Subjective Model Exam's results table reads as unattempted.
        attempts = exam.attempts.select_related('student').annotate(
            correct_answers=Count('answers', filter=Q(answers__is_correct=True)),
            skipped_answers=Count('answers', filter=Q(answers__selected_option__isnull=True) & Q(answers__answer_text='')),
            incorrect_answers=Count('answers', filter=Q(answers__is_correct=False) & Q(answers__selected_option__isnull=False)),
            rank=Window(
                expression=Rank(),
                order_by=[F('score').desc(), F('time_taken_seconds').asc()]
            )
        )
        
        # We need a subquery or a python sort if we filter after window function? 
        # Actually window function rank is computed over the entire queryset. 
        # If we filter the queryset, the rank is recomputed for the filtered subset.
        # This is correct if we want rank among the filtered subset.
        # If we want global rank, we should compute it first or do it in python.
        # For simplicity, Django's Window function computes it on the current QuerySet.
        
        # Filtering
        status_filter = request.query_params.get('status')
        if status_filter:
            attempts = attempts.filter(status=status_filter)
            
        passed_filter = request.query_params.get('passed')
        if passed_filter is not None:
            passed = passed_filter.lower() == 'true'
            attempts = attempts.filter(passed=passed)
            
        search = request.query_params.get('search')
        if search:
            attempts = attempts.filter(
                Q(student__first_name__icontains=search) | 
                Q(student__last_name__icontains=search) |
                Q(student__email__icontains=search) |
                Q(student__username__icontains=search)
            )
            
        ordering = request.query_params.get('ordering', '-score')
        if ordering:
            attempts = attempts.order_by(ordering, 'time_taken_seconds')
            
        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        paginator = Paginator(attempts, page_size)
        
        try:
            current_page = paginator.page(page)
        except Exception:
            return Response({"results": [], "count": 0})
            
        results = []
        for attempt in current_page.object_list:
            results.append({
                "id": attempt.id,
                "student_id": attempt.student.id,
                "student_name": f"{attempt.student.first_name} {attempt.student.last_name}".strip() or attempt.student.username,
                "email": attempt.student.email,
                "started_at": attempt.started_at,
                "submitted_at": attempt.submitted_at,
                "status": attempt.status,
                "score": attempt.score,
                "percentage": attempt.percentage,
                "passed": attempt.passed,
                "time_taken_seconds": attempt.time_taken_seconds,
                "correct_answers": attempt.correct_answers,
                "incorrect_answers": attempt.incorrect_answers,
                "skipped_answers": attempt.skipped_answers,
                "rank": attempt.rank if attempt.status == 'evaluated' else None
            })
            
        return Response({
            "count": paginator.count,
            "num_pages": paginator.num_pages,
            "current_page": page,
            "results": results
        })

    @action(detail=True, methods=['post'], url_path='question-paper')
    def upload_question_paper(self, request, pk=None):
        import os
        import io
        from PIL import Image, ImageOps
        from django.core.files.base import ContentFile

        exam = self.get_object()
        file = request.FILES.get('file') or request.FILES.get('question_paper') or request.FILES.get('pdf_file')
        if not file:
            return Response({'detail': 'No question paper file was provided.'}, status=status.HTTP_400_BAD_REQUEST)
        if file.size < 100:
            return Response({'detail': 'The uploaded file is empty or corrupted.'}, status=status.HTTP_400_BAD_REQUEST)
        if file.size > 20 * 1024 * 1024:
            return Response({'detail': 'File size exceeds maximum allowed limit (20MB).'}, status=status.HTTP_400_BAD_REQUEST)

        file_name_lower = file.name.lower()
        content = file.read()
        file.seek(0)

        # 1. Handle PDF
        if file_name_lower.endswith('.pdf') or content.startswith(b'%PDF-'):
            if not content.startswith(b'%PDF-'):
                return Response({'detail': 'The uploaded file is not a valid PDF document (missing %PDF- header).'}, status=status.HTTP_400_BAD_REQUEST)
            page_count = max(1, content.count(b'/Type /Page\n') + content.count(b'/Type /Page\r') + content.count(b'/Type/Page'))
            final_file = file
            final_file.seek(0)
            final_size = file.size
        # 2. Handle image formats (JPG, PNG, WEBP) by converting to standardized PDF
        elif any(file_name_lower.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.webp')) or (file.content_type and file.content_type.startswith('image/')):
            try:
                img = Image.open(file)
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                pdf_buffer = io.BytesIO()
                img.save(pdf_buffer, format='PDF', quality=85, resolution=150.0)
                pdf_bytes = pdf_buffer.getvalue()
                clean_name = f"{os.path.splitext(file.name)[0]}.pdf"
                final_file = ContentFile(pdf_bytes, name=clean_name)
                page_count = 1
                final_size = len(pdf_bytes)
            except Exception as e:
                return Response({'detail': f'Failed to process question paper image: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'detail': 'Only PDF documents and image files (JPG, PNG, WEBP) are accepted for the question paper.'}, status=status.HTTP_400_BAD_REQUEST)

        exam.question_paper_pdf = final_file
        exam.question_paper_page_count = page_count
        exam.question_paper_file_size = final_size
        exam.save(update_fields=['question_paper_pdf', 'question_paper_page_count', 'question_paper_file_size', 'updated_at'])

        return Response({
            'detail': 'Question paper uploaded successfully.',
            'page_count': page_count,
            'file_size': final_size,
            'filename': os.path.basename(exam.question_paper_pdf.name),
        }, status=status.HTTP_200_OK)

    @upload_question_paper.mapping.delete
    def delete_question_paper(self, request, pk=None):
        exam = self.get_object()
        if exam.question_paper_pdf:
            exam.question_paper_pdf.delete(save=False)
            exam.question_paper_pdf = None
            exam.question_paper_page_count = 0
            exam.question_paper_file_size = 0
            exam.save(update_fields=['question_paper_pdf', 'question_paper_page_count', 'question_paper_file_size', 'updated_at'])
        return Response({'detail': 'Question paper removed successfully.'})

    @upload_question_paper.mapping.get
    def get_question_paper(self, request, pk=None):
        from django.http import FileResponse
        exam = self.get_object()
        if not exam.question_paper_pdf:
            return Response({'detail': 'No question paper uploaded for this exam.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            return FileResponse(exam.question_paper_pdf.open('rb'), content_type='application/pdf')
        except Exception as e:
            return Response({'detail': f'Could not open question paper: {e}'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['get'], url_path='submissions')
    def submissions(self, request, pk=None):
        from exams.models import SubjectiveSubmission
        from exams.serializers import AdminSubjectiveSubmissionListSerializer
        exam = self.get_object()
        submissions = (
            SubjectiveSubmission.objects
            .filter(attempt__examination=exam)
            .select_related('attempt', 'attempt__student', 'attempt__examination', 'evaluator')
            .order_by('-created_at')
        )
        status_param = request.query_params.get('status')
        if status_param == 'pending':
            submissions = submissions.filter(is_published=False)
        elif status_param == 'evaluated':
            submissions = submissions.filter(status='evaluated')
        elif status_param == 'published':
            submissions = submissions.filter(is_published=True)
        elif status_param and status_param != 'all':
            submissions = submissions.filter(status=status_param)

        serializer = AdminSubjectiveSubmissionListSerializer(submissions, many=True)
        return Response(serializer.data)


class AdminExaminationRequestViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = ExaminationRequestSerializer

    def get_queryset(self):
        queryset = ExaminationRequest.objects.select_related(
            'student', 'examination', 'reviewed_by', 'academic_exam', 'course', 'subject', 'topic'
        ).all()
        status_filter = self.request.query_params.get('status')
        if status_filter in ('pending', 'approved', 'rejected'):
            queryset = queryset.filter(status=status_filter)
        return queryset

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        from django.db import transaction
        from django.utils import timezone

        with transaction.atomic():
            exam_request = ExaminationRequest.objects.select_for_update().get(pk=self.get_object().pk)
            if exam_request.status != 'pending':
                return Response({'detail': 'Only pending requests can be approved.'}, status=status.HTTP_409_CONFLICT)
            if exam_request.request_type == 'subjective_live':
                if not exam_request.examination_id:
                    auto_exam = SubjectiveExamAssignmentService.assign_subjective_exam(exam_request, mode='auto')
                    if auto_exam is None:
                        return Response(
                            {'detail': 'No active subjective question set is available to auto-assign for this request.'},
                            status=status.HTTP_409_CONFLICT,
                        )
                    exam_request = ExaminationRequest.objects.select_related(
                        'student', 'examination', 'reviewed_by', 'academic_exam', 'course', 'subject', 'topic'
                    ).get(pk=exam_request.pk)
                elif exam_request.examination.status != 'published':
                    return Response(
                        {'detail': 'Generate, review, and publish the subjective paper before approving its request.'},
                        status=status.HTTP_409_CONFLICT,
                    )
            exam_request.status = 'approved'
            exam_request.reviewed_by = request.user
            exam_request.reviewed_at = timezone.now()
            exam_request.rejection_reason = ''
            exam_request.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'updated_at'])
        return Response(self.get_serializer(exam_request).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        from django.db import transaction
        from django.utils import timezone

        reason = str(request.data.get('rejection_reason') or '').strip()
        if not reason:
            return Response({'detail': 'rejection_reason is required.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            exam_request = ExaminationRequest.objects.select_for_update().get(pk=self.get_object().pk)
            if exam_request.status != 'pending':
                return Response({'detail': 'Only pending requests can be rejected.'}, status=status.HTTP_409_CONFLICT)
            exam_request.status = 'rejected'
            exam_request.reviewed_by = request.user
            exam_request.reviewed_at = timezone.now()
            exam_request.rejection_reason = reason
            exam_request.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'updated_at'])
        return Response(self.get_serializer(exam_request).data)


class AdminSubjectiveSubmissionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsEvaluatorUser]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        from django.db import models as db_models
        from exams.models import SubjectiveSubmission
        queryset = (
            SubjectiveSubmission.objects
            .select_related('attempt', 'attempt__student', 'attempt__examination', 'evaluator')
            .prefetch_related('pages', 'question_scores')
            .all()
        )
        exam_id = self.request.query_params.get('exam_id')
        if exam_id:
            queryset = queryset.filter(attempt__examination_id=exam_id)

        status_param = self.request.query_params.get('status')
        if status_param == 'pending':
            queryset = queryset.filter(is_published=False)
        elif status_param == 'evaluated':
            queryset = queryset.filter(status='evaluated')
        elif status_param == 'published':
            queryset = queryset.filter(is_published=True)
        elif status_param and status_param != 'all':
            queryset = queryset.filter(status=status_param)

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                db_models.Q(attempt__student__username__icontains=search) |
                db_models.Q(attempt__student__email__icontains=search) |
                db_models.Q(attempt__student__first_name__icontains=search) |
                db_models.Q(attempt__student__last_name__icontains=search) |
                db_models.Q(attempt__examination__title__icontains=search)
            )

        student_id = self.request.query_params.get('student_id')
        if student_id:
            queryset = queryset.filter(attempt__student_id=student_id)

        evaluation_status = self.request.query_params.get('evaluation_status')
        if evaluation_status == 'pending':
            queryset = queryset.filter(is_published=False, status__in=['submitted', 'processing', 'under_review'])
        elif evaluation_status == 'evaluated':
            queryset = queryset.filter(status='evaluated', is_published=False)
        elif evaluation_status == 'published':
            queryset = queryset.filter(is_published=True)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return queryset

    def get_serializer_class(self):
        from exams.serializers import AdminSubjectiveSubmissionListSerializer, AdminSubjectiveSubmissionDetailSerializer
        if self.action in ['retrieve', 'by_attempt']:
            return AdminSubjectiveSubmissionDetailSerializer
        return AdminSubjectiveSubmissionListSerializer

    def retrieve(self, request, *args, **kwargs):
        from exams.models import SubjectiveSubmission
        from exams.serializers import AdminSubjectiveSubmissionDetailSerializer
        pk = kwargs.get('pk')
        try:
            submission = (
                SubjectiveSubmission.objects
                .select_related('attempt', 'attempt__student', 'attempt__examination', 'evaluator')
                .prefetch_related('pages', 'question_scores')
                .get(pk=pk)
            )
        except SubjectiveSubmission.DoesNotExist:
            try:
                submission = (
                    SubjectiveSubmission.objects
                    .select_related('attempt', 'attempt__student', 'attempt__examination', 'evaluator')
                    .prefetch_related('pages', 'question_scores')
                    .get(attempt_id=pk)
                )
            except SubjectiveSubmission.DoesNotExist:
                return Response({'detail': f'Submission #{pk} not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminSubjectiveSubmissionDetailSerializer(submission)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='by-attempt/(?P<attempt_id>[^/.]+)')
    def by_attempt(self, request, attempt_id=None):
        from exams.models import SubjectiveSubmission
        from exams.serializers import AdminSubjectiveSubmissionDetailSerializer
        try:
            submission = (
                SubjectiveSubmission.objects
                .select_related('attempt', 'attempt__student', 'attempt__examination', 'evaluator')
                .prefetch_related('pages', 'question_scores')
                .get(attempt_id=attempt_id)
            )
        except SubjectiveSubmission.DoesNotExist:
            # Fallback: if caller passed submission.id instead of attempt_id
            try:
                submission = (
                    SubjectiveSubmission.objects
                    .select_related('attempt', 'attempt__student', 'attempt__examination', 'evaluator')
                    .prefetch_related('pages', 'question_scores')
                    .get(id=attempt_id)
                )
            except SubjectiveSubmission.DoesNotExist:
                return Response({'detail': f'Submission for attempt #{attempt_id} not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminSubjectiveSubmissionDetailSerializer(submission)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='answer-sheet')
    def answer_sheet(self, request, pk=None):
        from django.http import FileResponse
        submission = self.get_object()
        if not submission.answer_pdf:
            return Response({'detail': 'No answer PDF uploaded for this submission.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            return FileResponse(submission.answer_pdf.open('rb'), content_type='application/pdf')
        except Exception as e:
            return Response({'detail': f'Could not open answer PDF: {e}'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'], url_path='ocr')
    def run_ocr(self, request, pk=None):
        from exams.ocr_service import SubjectiveOCRService
        from exams.serializers import AdminSubjectiveSubmissionDetailSerializer
        submission = self.get_object()
        SubjectiveOCRService.extract_and_transcribe_submission(submission)
        submission.refresh_from_db()
        serializer = AdminSubjectiveSubmissionDetailSerializer(submission)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='update-transcription')
    def update_transcription(self, request, pk=None):
        from exams.serializers import AdminSubjectiveSubmissionDetailSerializer
        submission = self.get_object()
        extracted_text = request.data.get('extracted_text')
        if extracted_text is not None:
            submission.extracted_text = extracted_text
            submission.save(update_fields=['extracted_text', 'updated_at'])
        serializer = AdminSubjectiveSubmissionDetailSerializer(submission)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='evaluate')
    def evaluate(self, request, pk=None):
        from exams.models import SubjectiveQuestionScore
        from exams.serializers import AdminSubjectiveSubmissionDetailSerializer
        from django.db import transaction

        submission = self.get_object()
        data = request.data

        # If already published, require explicit edit_published flag
        if submission.is_published and not data.get('edit_published', False):
            return Response(
                {'detail': 'This result has already been published. Please enable editing of published results to make changes.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        question_scores_data = data.get('question_scores', [])
        if not isinstance(question_scores_data, list):
            return Response({'detail': 'question_scores must be a list.'}, status=status.HTTP_400_BAD_REQUEST)

        validated_scores = []
        total_score = 0.0
        total_max = 0.0

        for idx, q_score in enumerate(question_scores_data):
            try:
                q_num = int(q_score.get('question_number', idx + 1))
            except (ValueError, TypeError):
                q_num = idx + 1

            try:
                marks_obtained = float(q_score.get('marks_obtained', 0))
            except (ValueError, TypeError):
                return Response({'detail': f'Question #{q_num}: Obtained marks must be a valid number.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                max_marks = float(q_score.get('max_marks', 10))
            except (ValueError, TypeError):
                return Response({'detail': f'Question #{q_num}: Maximum marks must be a valid number.'}, status=status.HTTP_400_BAD_REQUEST)

            if max_marks <= 0:
                return Response({'detail': f'Question #{q_num}: Maximum marks must be greater than 0.'}, status=status.HTTP_400_BAD_REQUEST)

            if marks_obtained < 0:
                return Response({'detail': f'Question #{q_num}: Obtained marks cannot be negative.'}, status=status.HTTP_400_BAD_REQUEST)

            if marks_obtained > max_marks:
                return Response({
                    'detail': f'Question #{q_num}: Obtained marks ({marks_obtained:g}) cannot exceed maximum marks ({max_marks:g}).'
                }, status=status.HTTP_400_BAD_REQUEST)

            feedback = str(q_score.get('feedback', '') or '').strip()
            validated_scores.append({
                'question_number': q_num,
                'marks_obtained': marks_obtained,
                'max_marks': max_marks,
                'feedback': feedback
            })
            total_score += marks_obtained
            total_max += max_marks

        with transaction.atomic():
            if 'evaluator_feedback' in data:
                submission.evaluator_feedback = str(data['evaluator_feedback'] or '').strip()
            submission.evaluator = request.user
            submission.evaluated_at = timezone.now()
            submission.status = 'evaluated'

            submission.question_scores.all().delete()
            for q in validated_scores:
                SubjectiveQuestionScore.objects.create(
                    submission=submission,
                    question_number=q['question_number'],
                    marks_obtained=q['marks_obtained'],
                    max_marks=q['max_marks'],
                    feedback=q['feedback']
                )

            attempt = submission.attempt
            attempt.score = total_score
            effective_total = total_max if total_max > 0 else float(attempt.examination.total_marks or 100)
            attempt.percentage = round((total_score / effective_total) * 100, 2) if effective_total > 0 else 0.0

            exam_total = float(attempt.examination.total_marks or 100)
            exam_pass = float(attempt.examination.passing_marks or (exam_total * 0.4))
            pass_ratio = (exam_pass / exam_total) if exam_total > 0 else 0.4
            pass_marks = effective_total * pass_ratio
            attempt.passed = total_score >= pass_marks
            attempt.status = 'evaluated'
            attempt.save(update_fields=['status', 'score', 'percentage', 'passed'])
            submission.save()

        serializer = AdminSubjectiveSubmissionDetailSerializer(submission)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        from exams.serializers import AdminSubjectiveSubmissionDetailSerializer
        from core.notification_service import NotificationService
        from django.db import transaction

        submission = self.get_object()

        # Validation checks prior to publishing
        if not submission.attempt:
            return Response({'detail': 'Cannot publish: Attempt not found.'}, status=status.HTTP_400_BAD_REQUEST)
        if not submission.attempt.student:
            return Response({'detail': 'Cannot publish: Student not found.'}, status=status.HTTP_400_BAD_REQUEST)
        if not submission.attempt.examination:
            return Response({'detail': 'Cannot publish: Examination not found.'}, status=status.HTTP_400_BAD_REQUEST)

        scores = list(submission.question_scores.all())
        if not scores:
            return Response({'detail': 'Cannot publish yet: Please add and evaluate at least one question.'}, status=status.HTTP_400_BAD_REQUEST)

        for qs in scores:
            if qs.max_marks <= 0:
                return Response({'detail': f'Cannot publish: Question #{qs.question_number} maximum marks must be greater than 0.'}, status=status.HTTP_400_BAD_REQUEST)
            if qs.marks_obtained < 0:
                return Response({'detail': f'Cannot publish: Question #{qs.question_number} obtained marks cannot be negative.'}, status=status.HTTP_400_BAD_REQUEST)
            if qs.marks_obtained > qs.max_marks:
                return Response({
                    'detail': f'Cannot publish: Question #{qs.question_number} obtained marks ({qs.marks_obtained:g}) cannot exceed maximum marks ({qs.max_marks:g}).'
                }, status=status.HTTP_400_BAD_REQUEST)

        total_max = sum(qs.max_marks for qs in scores)
        if total_max <= 0:
            return Response({'detail': 'Cannot publish: Total maximum marks must be greater than 0.'}, status=status.HTTP_400_BAD_REQUEST)

        total_score = sum(qs.marks_obtained for qs in scores)
        percentage = round((total_score / total_max * 100), 2)

        with transaction.atomic():
            submission.is_published = True
            submission.published_at = timezone.now()
            submission.status = 'evaluated'
            submission.evaluator = request.user
            submission.save(update_fields=['is_published', 'published_at', 'status', 'evaluator', 'updated_at'])

            attempt = submission.attempt
            attempt.score = total_score
            attempt.percentage = percentage
            exam_total = float(attempt.examination.total_marks or 100)
            exam_pass = float(attempt.examination.passing_marks or (exam_total * 0.4))
            pass_ratio = (exam_pass / exam_total) if exam_total > 0 else 0.4
            pass_marks = total_max * pass_ratio
            attempt.passed = total_score >= pass_marks
            attempt.status = 'evaluated'
            attempt.save(update_fields=['status', 'score', 'percentage', 'passed'])

            transaction.on_commit(lambda: NotificationService.notify_subjective_result_published(submission))

        serializer = AdminSubjectiveSubmissionDetailSerializer(submission)
        return Response(serializer.data)

