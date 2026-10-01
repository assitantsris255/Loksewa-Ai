import os
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache
from .models import (
    Exam as AcademicExam,
    Examination,
    ExaminationAttempt,
    ExaminationRequest,
    Subject,
    Topic,
    StudentAnswer,
    Question,
    CalmSessionLog,
)
from .selection_service import QuestionSelectionService
from .attempt_timing import (
    attempt_expires_at,
    attempt_remaining_seconds,
    attempt_is_expired,
    enforce_expiry,
    finalize_attempt,
    recompute_after_evaluation,
)
from administration.permissions import IsEvaluatorUser
from .student_serializers import (
    StudentExaminationSerializer, 
    StudentExaminationAttemptSerializer, 
    StudentExaminationResultSerializer,
    StudentExaminationAttemptListSerializer,
    ExaminationRequestSerializer,
    StudentSecureQuestionSerializer,
    StudentReviewQuestionSerializer,
    StudentLeaderboardSerializer
)
from core.pagination import StandardResultsSetPagination
from django.db.models import F, Window, Sum, Avg, Max, Count, FloatField, ExpressionWrapper
from django.db.models.functions import DenseRank
from subscriptions.permissions import HasActiveSubscription

class StudentExaminationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for students to view available exams and start them.
    """
    permission_classes = [IsAuthenticated, HasActiveSubscription]
    serializer_class = StudentExaminationSerializer
    
    def get_queryset(self):
        user = self.request.user
        from django.db.models import Q

        if not user or not user.is_authenticated:
            return Examination.objects.none()

        if user.role in ('teacher', 'admin', 'super-admin'):
            return Examination.objects.filter(status__in=['published', 'live'])

        from courses.access import (
            authorized_courses,
            get_student_course_context,
            get_authorized_examination_filter,
        )

        # For single-object actions, allow the student to access any exam that belongs
        # to ANY of their authorized courses or authorized exam scopes.
        if self.action in ('retrieve', 'start', 'active_attempt', 'question_paper'):
            exam_q = get_authorized_examination_filter(user)
            if exam_q is None:
                return Examination.objects.none()
            base_qs = Examination.objects.filter(status__in=['published', 'live']).filter(exam_q)
            return base_qs.filter(Q(exam_type='custom', created_by=user) | ~Q(exam_type='custom'))

        req_course_id = self.request.query_params.get('course_id')
        auth_courses = authorized_courses(user)
        if not auth_courses.exists():
            base_qs = Examination.objects.filter(
                status__in=['published', 'live'],
                course__isnull=True,
            )
            if self.action == 'list':
                return base_qs
            return base_qs.filter(Q(exam_type='custom', created_by=user) | ~Q(exam_type='custom'))

        target_course = None
        if req_course_id:
            try:
                c_id = int(req_course_id)
                target_course = auth_courses.filter(id=c_id).first()
                if not target_course:
                    # Requested course does NOT belong to student's authorized courses -> strict denial (no fallback)
                    return Examination.objects.none()
            except (ValueError, TypeError):
                return Examination.objects.none()

        if target_course:
            exam_q = get_authorized_examination_filter(user, target_course=target_course)
        else:
            exam_q = get_authorized_examination_filter(user)

        if exam_q is None:
            return Examination.objects.none()

        base_qs = (
            Examination.objects
            .filter(status__in=['published', 'live'])
            .filter(exam_q)
            .select_related('course', 'category', 'exam', 'subject')
        )
        if user.is_authenticated:
            from django.db.models import Prefetch
            base_qs = base_qs.prefetch_related(
                Prefetch(
                    'attempts',
                    queryset=ExaminationAttempt.objects.filter(student=user),
                    to_attr='student_attempts'
                )
            )

        # Exclude subjective exams that do not have an assigned question paper PDF
        base_qs = base_qs.exclude(
            Q(exam_type='subjective') & (Q(question_paper_pdf__isnull=True) | Q(question_paper_pdf=''))
        )

        if self.action == 'list':
            base_qs = base_qs.exclude(exam_type='custom').exclude(objective_category='custom')
            if self.request.query_params.get('topicwise', '').lower() in ('1', 'true', 'yes'):
                base_qs = base_qs.filter(exam_type='subject', topic__isnull=False)
            return base_qs
        return base_qs.filter(Q(exam_type='custom', created_by=user) | ~Q(exam_type='custom'))

    def retrieve(self, request, *args, **kwargs):
        examination = self.get_object()
        user = request.user
        if user.role == 'student':
            from courses.access import is_examination_authorized_for_student
            if not is_examination_authorized_for_student(user, examination):
                return Response(
                    {'detail': 'You do not have access to this course examination.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        serializer = self.get_serializer(examination)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='question-paper')
    def question_paper(self, request, pk=None):
        """Securely stream question paper PDF for authorized students."""
        examination = self.get_object()
        user = request.user

        if user.role == 'student':
            from courses.access import is_examination_authorized_for_student
            if not is_examination_authorized_for_student(user, examination):
                return Response(
                    {'detail': 'You do not have access to this course examination.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        if not examination.question_paper_pdf:
            return Response({'detail': 'No question paper uploaded for this examination.'}, status=status.HTTP_404_NOT_FOUND)

        from django.http import FileResponse
        try:
            return FileResponse(examination.question_paper_pdf.open('rb'), content_type='application/pdf')
        except Exception as e:
            return Response({'detail': f'Could not open question paper: {e}'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['get'], url_path='expert-solution')
    def expert_solution(self, request, pk=None):
        examination = self.get_object()
        if examination.objective_category == 'live':
            return Response(
                {'detail': 'Expert solutions are unavailable for scheduled Live Exams.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if ExaminationAttempt.objects.filter(
            examination=examination, student=request.user, status__in=('in-progress', 'upload_pending')
        ).exists():
            return Response(
                {'detail': 'Expert solutions are unavailable while an examination attempt is active.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        rows = examination.examination_questions.select_related('question').order_by('order', 'id')
        solutions = []
        for row in rows:
            question = row.question
            if not (question.correct_option or question.explanation or question.model_answer):
                continue
            solutions.append({
                'id': question.id,
                'text': question.text,
                'question_type': question.question_type,
                'option_a': question.option_a,
                'option_b': question.option_b,
                'option_c': question.option_c,
                'option_d': question.option_d,
                'correct_option': question.correct_option,
                'explanation': question.explanation,
                'model_answer': question.model_answer,
                'marks': row.marks,
            })
        if not solutions:
            return Response({'detail': 'Expert solution is not available yet.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'examination': examination.id, 'title': examination.title, 'solutions': solutions})

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """
        Create *or resume* an ExaminationAttempt.

        Idempotent by design: a second tab, a refresh, or a double-click
        returns the student's existing in-progress attempt rather than
        creating a duplicate. The attempt row stays the single source of truth
        for "am I in an exam right now", which is what drives exam Focus Mode.
        """
        examination = self.get_object()
        user = request.user

        if user.role == 'student':
            from courses.access import is_examination_authorized_for_student
            if not is_examination_authorized_for_student(user, examination):
                return Response(
                    {'detail': 'You do not have access to this course examination.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        if examination.status not in ['published', 'live']:
            return Response(
                {'detail': 'Exam is not currently active.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        exam_request = ExaminationRequest.objects.filter(
            student=user, examination=examination
        ).order_by('-created_at').first()

        if exam_request and exam_request.status in ('pending', 'rejected'):
            return Response(
                {'detail': 'Admin approval is required before starting this examination.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        requires_request = (
            examination.course_id is not None
            and (
                examination.objective_category in ('past_year', 'model', 'topicwise')
                or (examination.exam_type == 'subject' and examination.topic_id is not None)
            )
        )

        if requires_request and not ExaminationRequest.objects.filter(
            student=user, examination=examination, status='approved'
        ).exists():
            return Response(
                {'detail': 'Admin approval is required before starting this examination.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        now = timezone.now()
        if examination.start_time and now < examination.start_time:
            return Response(
                {'detail': 'This exam has not opened yet.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if examination.end_time and now > examination.end_time:
            return Response(
                {'detail': 'This exam window has closed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if examination.exam_type == 'subjective' and not examination.question_paper_pdf:
            return Response(
                {'detail': 'Question paper for this subjective exam is not available yet.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Lock this student's rows for this exam so two tabs racing on
            # "Start" cannot both create an attempt.
            active_attempt = (
                ExaminationAttempt.objects
                .select_for_update()
                .filter(examination=examination, student=user, status__in=('in-progress', 'upload_pending'))
                .first()
            )

            # allow_resume used to be stored but never read — leaving mid-exam
            # and coming back always silently continued regardless of the
            # flag. Live Exams additionally forbid resume unconditionally
            # (the category's "no pause/restart" rule), not left to the
            # per-exam checkbox.
            resume_allowed = examination.allow_resume and examination.objective_category != 'live'

            if active_attempt:
                # An attempt that ran out of time while the student was away is
                # closed here rather than silently resumed.
                if enforce_expiry(active_attempt):
                    active_attempt = None
                elif not resume_allowed:
                    # Leaving mid-attempt forfeits it: score whatever was
                    # answered so far instead of letting them continue later.
                    finalize_attempt(active_attempt)
                    active_attempt = None
                else:
                    serializer = StudentExaminationAttemptSerializer(active_attempt)
                    return Response(
                        {**serializer.data, 'resumed': True},
                        status=status.HTTP_200_OK,
                    )

            if examination.max_attempts and examination.max_attempts > 0:
                attempts_count = ExaminationAttempt.objects.filter(
                    examination=examination, student=user
                ).count()
                if attempts_count >= examination.max_attempts:
                    return Response(
                        {'detail': 'Maximum attempts reached for this exam.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )

            attempt = ExaminationAttempt.objects.create(
                examination=examination,
                student=user,
                status='in-progress',
            )

        serializer = StudentExaminationAttemptSerializer(attempt)
        return Response(
            {**serializer.data, 'resumed': False},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'], url_path='active-attempt')
    def active_attempt(self, request, pk=None):
        """The student's in-progress attempt for this exam, if any."""
        examination = self.get_object()
        if request.user.role == 'student':
            from courses.access import is_examination_authorized_for_student
            if not is_examination_authorized_for_student(request.user, examination):
                return Response(
                    {'detail': 'You do not have access to this course examination.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        attempt = ExaminationAttempt.objects.filter(
            examination=examination, student=request.user, status__in=('in-progress', 'upload_pending')
        ).first()

        if attempt and enforce_expiry(attempt):
            attempt = None

        if not attempt:
            return Response({'active_attempt': None})

        return Response({
            'active_attempt': StudentExaminationAttemptSerializer(attempt).data
        })

    @action(detail=False, methods=['get'], url_path='academic-hierarchy')
    def academic_hierarchy(self, request):
        user = request.user
        allowed_exam_ids = None

        if user.role == 'student':
            from courses.access import authorized_courses, get_course_exam_ids, authorized_exam_ids
            course_id = request.query_params.get('course_id')
            if course_id:
                try:
                    c_id = int(course_id)
                    auth_c = authorized_courses(user).filter(id=c_id).first()
                    if auth_c:
                        allowed_exam_ids = get_course_exam_ids(auth_c)
                    else:
                        allowed_exam_ids = set()
                except (ValueError, TypeError):
                    allowed_exam_ids = set()
            else:
                allowed_exam_ids = authorized_exam_ids(user)

            if not allowed_exam_ids:
                return Response([])

        from exams.models import ExamCategory
        categories = ExamCategory.objects.filter(is_active=True).prefetch_related(
            'exams', 'exams__papers', 'exams__papers__subjects', 
            'exams__papers__subjects__chapters', 'exams__papers__subjects__chapters__topics'
        )
        tree = []
        for cat in categories:
            exams_qs = cat.exams.filter(is_active=True)
            if allowed_exam_ids is not None:
                exams_qs = exams_qs.filter(id__in=allowed_exam_ids)

            if not exams_qs.exists():
                continue

            cat_data = {
                'id': cat.id, 'name': cat.name, 'is_active': cat.is_active, 'exams': []
            }
            for exam in exams_qs:
                exam_data = {
                    'id': exam.id, 'name': exam.name, 'is_active': exam.is_active, 'papers': []
                }
                for paper in exam.papers.filter(is_active=True):
                    paper_data = {
                        'id': paper.id, 'name': paper.name, 'is_active': paper.is_active, 'subjects': []
                    }
                    for subject in paper.subjects.filter(is_active=True):
                        subject_data = {
                            'id': subject.id, 'name': subject.name, 'is_active': subject.is_active, 'chapters': []
                        }
                        for chapter in subject.chapters.filter(is_active=True):
                            chapter_data = {
                                'id': chapter.id, 'title': chapter.title, 'is_active': chapter.is_active, 'topics': []
                            }
                            for topic in chapter.topics.filter(is_active=True):
                                chapter_data['topics'].append({
                                    'id': topic.id, 'name': topic.name, 'is_active': topic.is_active
                                })
                            subject_data['chapters'].append(chapter_data)
                        paper_data['subjects'].append(subject_data)
                    exam_data['papers'].append(paper_data)
                cat_data['exams'].append(exam_data)
            tree.append(cat_data)
        return Response(tree)

    def _build_question_filter(self, data):
        from django.db.models import Q
        q_filter = Q(status='approved')
        
        category_id = data.get('category_id')
        exam_id = data.get('exam_id')
        paper_id = data.get('paper_id')
        subject_id = data.get('subject_id')
        chapter_id = data.get('chapter_id')
        topic_id = data.get('topic_id')
        difficulty = data.get('difficulty', 'all')
        question_type = data.get('question_type', 'mcq')

        # Question -> topic -> chapter -> subject -> paper -> exam -> category.
        # All multi-hop lookups below were missing the `chapter__` segment
        # (Topic has no direct `subject` field, only via `chapter`), so any
        # selection above chapter-level always hit "Unsupported lookup" -
        # the custom exam builder's availability check and generation both
        # 500'd for any exam/paper/subject-level scope.
        #
        # category_id is the top of the hierarchy (Central/Provincial/
        # Institutional in the client's terms) - it deliberately has no
        # elif chain with exam_id below it: picking a whole category means
        # "every question under every exam in it", not narrowed to one.
        if topic_id:
            q_filter &= Q(topic_id=topic_id)
        elif chapter_id:
            q_filter &= Q(topic__chapter_id=chapter_id)
        elif subject_id:
            q_filter &= Q(topic__chapter__subject_id=subject_id)
        elif paper_id:
            q_filter &= Q(topic__chapter__subject__paper_id=paper_id)
        elif exam_id:
            q_filter &= Q(topic__chapter__subject__paper__exam_id=exam_id)
        elif category_id:
            q_filter &= Q(topic__chapter__subject__paper__exam__category_id=category_id)

        if difficulty and difficulty != 'mixed' and difficulty != 'all':
            q_filter &= Q(difficulty=difficulty)
            
        if question_type:
            q_filter &= Q(question_type=question_type)
            
        return q_filter

    @action(detail=False, methods=['post'], url_path='available-questions')
    def available_questions(self, request):
        # QuestionSelectionService is imported at the top of this module
        data = request.data
        exam_id = data.get('exam_id')

        student_allowed_exam_ids = None
        if request.user.role == 'student':
            from courses.access import authorized_exam_ids
            allowed_exam_ids = authorized_exam_ids(request.user) or set()
            student_allowed_exam_ids = allowed_exam_ids
            if exam_id and int(exam_id) not in allowed_exam_ids:
                return Response({'available': 0})

        avail = QuestionSelectionService().check_availability(
            exam_id=data.get('exam_id'),
            exam_ids=student_allowed_exam_ids,
            category_id=data.get('category_id'),
            paper_id=data.get('paper_id'),
            subject_id=data.get('subject_id'),
            chapter_id=data.get('chapter_id'),
            topic_id=data.get('topic_id'),
            difficulty=data.get('difficulty') if data.get('difficulty') not in ('all', 'mixed', None) else None,
            question_type=data.get('question_type', 'mcq'),
        )
        return Response({'available': avail['total']})

    @action(detail=False, methods=['post'])
    def generate_custom(self, request):
        from exams.models import ExaminationQuestion, Exam
        # QuestionSelectionService is imported at the top of this module
        from django.db import transaction

        data = request.data
        exam_id = data.get('exam_id')
        category_id = data.get('category_id')
        num_questions = int(data.get('question_count', 20))
        difficulty_raw = data.get('difficulty')
        difficulty = difficulty_raw if difficulty_raw not in ('all', 'mixed', None) else None
        question_type = data.get('question_type', 'mcq')

        if not exam_id and not category_id:
            return Response({'detail': 'exam_id or category_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        student_allowed_exam_ids = None
        if request.user.role == 'student':
            from courses.access import authorized_exam_ids
            allowed_exam_ids = authorized_exam_ids(request.user) or set()
            student_allowed_exam_ids = allowed_exam_ids
            if exam_id and int(exam_id) not in allowed_exam_ids:
                return Response({'detail': 'You are not enrolled in the course for this exam.'}, status=status.HTTP_403_FORBIDDEN)

        service = QuestionSelectionService()
        avail = service.check_availability(
            exam_id=exam_id,
            exam_ids=student_allowed_exam_ids,
            category_id=category_id,
            paper_id=data.get('paper_id'),
            subject_id=data.get('subject_id'),
            chapter_id=data.get('chapter_id'),
            topic_id=data.get('topic_id'),
            difficulty=difficulty,
            question_type=question_type,
        )
        if num_questions > avail['total']:
            return Response({
                'detail': f'Only {avail["total"]} questions are available for your selected criteria.'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                result = service.select(
                    exam_id=exam_id,
                    exam_ids=student_allowed_exam_ids,
                    category_id=category_id,
                    paper_id=data.get('paper_id'),
                    subject_id=data.get('subject_id'),
                    chapter_id=data.get('chapter_id'),
                    topic_id=data.get('topic_id'),
                    difficulty=difficulty,
                    question_type=question_type,
                    count=num_questions,
                    randomize=True,
                )
                questions = result['questions']

                # Examination.exam is a required FK to one Position/Level, but
                # a category-wide "full syllabus" exam spans every position
                # under that category - there's no single exam to point at.
                # Fall back to whichever exam the first selected question
                # actually belongs to (purely for display; the real content
                # is the ExaminationQuestion rows below).
                if exam_id:
                    resolved_exam = Exam.objects.get(id=exam_id)
                else:
                    first_question = questions[0] if questions else None
                    resolved_exam = (
                        first_question.topic.chapter.subject.paper.exam
                        if first_question else
                        Exam.objects.filter(category_id=category_id).first()
                    )
                    if not resolved_exam:
                        return Response({'detail': 'No exam found under this category.'}, status=status.HTTP_400_BAD_REQUEST)

                # Scoring awards each question's own marks (Question.marks), so
                # the exam total must be the sum of those - not the question
                # count - or a 2-mark question can push a score past 100%.
                total_marks = sum(q.marks for q in questions)
                from courses.models import Course
                custom_course = Course.objects.filter(exam=resolved_exam).first()
                if not custom_course and resolved_exam.parent_id:
                    custom_course = Course.objects.filter(exam_id=resolved_exam.parent_id).first()

                custom_exam = Examination.objects.create(
                    title=f"Custom Exam - {timezone.now().strftime('%Y-%m-%d %H:%M')}",
                    exam_type='custom',
                    objective_category=None,
                    category=resolved_exam.category,
                    exam=resolved_exam,
                    course=custom_course,
                    total_questions=len(questions),
                    time_limit=len(questions),
                    total_marks=total_marks,
                    passing_marks=total_marks * 0.4,
                    show_correct_answers=True,
                    status='published',
                    created_by=request.user
                )

                exam_questions = [
                    ExaminationQuestion(examination=custom_exam, question=q, order=i, marks=q.marks)
                    for i, q in enumerate(questions)
                ]
                ExaminationQuestion.objects.bulk_create(exam_questions)
                
                attempt = ExaminationAttempt.objects.create(
                    examination=custom_exam,
                    student=request.user,
                    status='in-progress'
                )
                
                serializer = StudentExaminationAttemptSerializer(attempt)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StudentExaminationRequestViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, HasActiveSubscription]
    serializer_class = ExaminationRequestSerializer

    def get_queryset(self):
        return ExaminationRequest.objects.filter(student=self.request.user).select_related(
            'student', 'examination', 'reviewed_by'
        )

    def create(self, request, *args, **kwargs):
        if request.user.role != 'student':
            return Response({'detail': 'Only students can request an examination.'}, status=status.HTTP_403_FORBIDDEN)
        request_type = request.data.get('request_type', 'exam_access')
        if request_type == 'subjective_live':
            try:
                academic_exam_id = int(request.data.get('academic_exam'))
                course_id = int(request.data['course']) if request.data.get('course') else None
                subject_id = int(request.data['subject']) if request.data.get('subject') else None
                topic_id = int(request.data['topic']) if request.data.get('topic') else None
            except (TypeError, ValueError):
                return Response({'detail': 'A valid academic_exam is required.'}, status=status.HTTP_400_BAD_REQUEST)

            academic_exam = AcademicExam.objects.filter(pk=academic_exam_id, is_active=True).first()
            if not academic_exam:
                return Response({'detail': 'An active academic exam is required.'}, status=status.HTTP_404_NOT_FOUND)

            from courses.access import authorized_courses, authorized_exam_ids
            if course_id:
                course = authorized_courses(request.user).filter(pk=course_id, exam_id=academic_exam.id).first()
                if not course:
                    return Response({'detail': 'You are not authorized for this course.'}, status=status.HTTP_403_FORBIDDEN)
            elif academic_exam.id not in (authorized_exam_ids(request.user) or set()):
                return Response({'detail': 'You are not authorized for this academic exam.'}, status=status.HTTP_403_FORBIDDEN)

            subject = None
            if subject_id:
                subject = Subject.objects.filter(
                    pk=subject_id, paper__exam_id=academic_exam.id, is_active=True
                ).first()
                if not subject:
                    return Response({'detail': 'Subject must belong to the selected academic exam.'}, status=status.HTTP_400_BAD_REQUEST)

            topic = None
            if topic_id:
                topic = Topic.objects.filter(
                    pk=topic_id, chapter__subject__paper__exam_id=academic_exam.id, is_active=True
                ).first()
                if not topic or (subject and topic.chapter.subject_id != subject.id):
                    return Response({'detail': 'Topic must belong to the selected exam and subject.'}, status=status.HTTP_400_BAD_REQUEST)

            exam_request, created = ExaminationRequest.objects.get_or_create(
                student=request.user,
                academic_exam=academic_exam,
                request_type='subjective_live',
                status='pending',
                defaults={'course_id': course_id, 'subject': subject, 'topic': topic},
            )
            return Response(
                self.get_serializer(exam_request).data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )

        if request_type != 'exam_access':
            return Response({'detail': 'Unsupported examination request type.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            examination_id = int(request.data.get('examination') or request.data.get('exam_id'))
        except (TypeError, ValueError):
            return Response({'detail': 'examination is required.'}, status=status.HTTP_400_BAD_REQUEST)

        examination = Examination.objects.filter(pk=examination_id, status='published').first()
        if not examination:
            return Response({'detail': 'Published examination not found.'}, status=status.HTTP_404_NOT_FOUND)

        requestable = (
            examination.objective_category in ('past_year', 'model', 'topicwise')
            or examination.exam_type == 'subjective'
            or (examination.exam_type == 'subject' and examination.topic_id is not None)
        )
        if not requestable:
            return Response({'detail': 'This examination does not require an admin request.'}, status=status.HTTP_400_BAD_REQUEST)

        from courses.access import is_examination_authorized_for_student
        if not is_examination_authorized_for_student(request.user, examination):
            return Response({'detail': 'You are not authorized for this examination.'}, status=status.HTTP_403_FORBIDDEN)

        exam_request, created = ExaminationRequest.objects.get_or_create(
            student=request.user,
            examination=examination,
        )
        return Response(
            self.get_serializer(exam_request).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class StudentExaminationAttemptViewSet(viewsets.ModelViewSet):
    """
    ViewSet for students to manage their active and past attempts.
    """
    permission_classes = [IsAuthenticated, HasActiveSubscription]
    serializer_class = StudentExaminationAttemptSerializer
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        user = self.request.user
        qs = (
            ExaminationAttempt.objects
            .filter(student=user)
            .select_related('examination', 'examination__course', 'examination__category', 'subjective_submission')
            .prefetch_related('answers__question')
        )

        if user.role == 'student':
            from courses.access import get_authorized_examination_filter
            course_id = self.request.query_params.get('course_id')
            exam_q = get_authorized_examination_filter(user, target_course=course_id)
            if exam_q is None:
                return qs.none()
            qs = qs.filter(examination__in=Examination.objects.filter(exam_q))

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return StudentExaminationAttemptListSerializer
        if self.action == 'result':
            return StudentExaminationResultSerializer
        return super().get_serializer_class()

    def get_object(self):
        """
        Every read of an attempt first settles its clock. A tab left open past
        the deadline therefore sees a submitted attempt, not a running one.
        Enforces strict course authorization for the underlying examination.
        """
        attempt = super().get_object()
        enforce_expiry(attempt)
        user = self.request.user
        if user.role == 'student':
            from courses.access import is_examination_authorized_for_student
            from rest_framework.exceptions import PermissionDenied
            if not is_examination_authorized_for_student(user, attempt.examination):
                raise PermissionDenied("You do not have access to this examination attempt.")
        return attempt

    @action(detail=False, methods=['get'])
    def active(self, request):
        """
        All still-running attempts for the current student.

        The Focus Mode context calls this on mount so a refresh, a reopened
        tab, or a second device re-applies exam focus from server state rather
        than from anything the browser remembered.
        """
        attempts = self.get_queryset().filter(status='in-progress')
        live = []
        for attempt in attempts:
            if not enforce_expiry(attempt):
                live.append(attempt)
        serializer = StudentExaminationAttemptSerializer(live, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def state(self, request, pk=None):
        """
        Lightweight poll target: attempt status plus remaining time. Used by
        the exam timer and the Focus Mode watchdog to re-sync with the server.
        For subjective exams, returns both writing timer and answer-upload deadline.
        """
        attempt = self.get_object()
        from .attempt_timing import (
            is_subjective_exam,
            subjective_exam_expires_at,
            subjective_exam_remaining_seconds,
            subjective_upload_expires_at,
            subjective_upload_remaining_seconds,
            subjective_upload_is_expired,
            is_subjective_upload_open,
        )
        is_subj = is_subjective_exam(attempt)
        sub_status = getattr(attempt.subjective_submission, 'status', None) if hasattr(attempt, 'subjective_submission') else None

        exam_exp = subjective_exam_expires_at(attempt) if is_subj else attempt_expires_at(attempt)
        upload_exp = subjective_upload_expires_at(attempt) if is_subj else None

        exam_rem = subjective_exam_remaining_seconds(attempt) if is_subj else attempt_remaining_seconds(attempt)
        upload_rem = subjective_upload_remaining_seconds(attempt) if is_subj else None

        return Response({
            'id': attempt.id,
            'status': attempt.status,
            'is_active': (
                (attempt.status in ('in-progress', 'upload_pending') and not subjective_upload_is_expired(attempt))
                if is_subj else (attempt.status == 'in-progress' and not attempt_is_expired(attempt))
            ),
            'is_expired': subjective_upload_is_expired(attempt) if is_subj else attempt_is_expired(attempt),
            'remaining_seconds': exam_rem,
            'time_remaining_seconds': exam_rem,
            'server_time': timezone.now().isoformat(),
            'is_subjective': is_subj,
            'exam_expires_at': exam_exp.isoformat() if exam_exp else None,
            'exam_remaining_seconds': exam_rem,
            'is_exam_expired': (exam_rem == 0) if is_subj else attempt_is_expired(attempt),
            'upload_expires_at': upload_exp.isoformat() if upload_exp else None,
            'upload_remaining_seconds': upload_rem,
            'upload_time_remaining_seconds': upload_rem,
            'is_upload_expired': subjective_upload_is_expired(attempt) if is_subj else None,
            'can_upload': is_subjective_upload_open(attempt) if is_subj else False,
            'submission_status': sub_status,
        })

    @action(detail=True, methods=['get'])
    def questions(self, request, pk=None):
        """Returns questions for this attempt. Exposes correct answers only after submission when review is allowed."""
        attempt = self.get_object()
        examination = attempt.examination
        
        # Get questions depending on whether it's from a question_set or directly mapped
        if examination.question_set:
            questions = list(examination.question_set.questions.all())
        else:
            from .models import ExaminationQuestion
            question_ids = list(
                ExaminationQuestion.objects
                .filter(examination=examination)
                .order_by('order', 'id')
                .values_list('question_id', flat=True)
            )
            q_map = {q.id: q for q in Question.objects.filter(id__in=question_ids)}
            questions = [q_map[qid] for qid in question_ids if qid in q_map]

        if examination.randomize_questions and examination.objective_category != 'past_year':
            import random
            random.Random(attempt.id).shuffle(questions)

        # Check if correct answer review is allowed
        can_review = False
        if attempt.status != 'in-progress':
            if examination.result_visibility == 'manual' and attempt.status != 'evaluated':
                can_review = False
            elif examination.result_visibility == 'after_end' and examination.end_time and timezone.now() < examination.end_time:
                can_review = False
            elif examination.exam_type in ('custom', 'practice') or examination.objective_category == 'custom':
                can_review = True
            else:
                can_review = bool(examination.show_correct_answers)

        if can_review:
            serializer = StudentReviewQuestionSerializer(questions, many=True)
        else:
            serializer = StudentSecureQuestionSerializer(questions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def answer(self, request, pk=None):
        """Save or update an answer for a specific question."""
        attempt = self.get_object()

        if attempt.status != 'in-progress':
            detail = (
                'Time is up - this attempt has been submitted automatically.'
                if attempt.submitted_at else
                'Cannot answer - exam is not in progress.'
            )
            return Response({'detail': detail, 'status': attempt.status},
                            status=status.HTTP_400_BAD_REQUEST)

        question_id = request.data.get('question')
        selected_option = request.data.get('selected_option')
        # Descriptive answer for short_answer/long_answer/subjective questions.
        # 'answer_text' not present in the payload at all (vs explicitly "")
        # distinguishes "this request didn't touch the text answer" from "the
        # student cleared it" - relevant since MCQ saves only ever send
        # selected_option and must never blank out a text answer that isn't
        # part of this request.
        answer_text_provided = 'answer_text' in request.data
        answer_text = request.data.get('answer_text', '')

        if not question_id:
            return Response({'detail': 'Question ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            question = Question.objects.get(pk=question_id)
        except Question.DoesNotExist:
            return Response({'detail': 'Question not found.'}, status=status.HTTP_404_NOT_FOUND)

        defaults = {'selected_option': selected_option}
        if answer_text_provided:
            defaults['answer_text'] = answer_text

        student_answer, created = StudentAnswer.objects.get_or_create(
            attempt=attempt,
            question=question,
            defaults=defaults,
        )

        if not created:
            student_answer.selected_option = selected_option
            if answer_text_provided:
                student_answer.answer_text = answer_text
            student_answer.save()

        return Response({'status': 'saved'})

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """
        Submit the exam attempt and calculate the score.

        Scoring lives in attempt_timing.finalize_attempt so that a manual
        submit and an automatic expiry cannot drift apart, and so a second tab
        pressing Submit is a harmless no-op instead of an error.
        """
        attempt = self.get_object()

        if attempt.status != 'in-progress':
            # get_object() may have just auto-submitted an expired attempt;
            # from the student's point of view that is a success.
            if attempt.submitted_at:
                return Response({
                    'detail': 'Exam submitted.',
                    'attempt_id': attempt.id,
                    'auto_submitted': True,
                })
            return Response({'detail': 'Exam already submitted.'},
                            status=status.HTTP_400_BAD_REQUEST)

        finalize_attempt(attempt)

        return Response({
            'detail': 'Exam submitted successfully.',
            'attempt_id': attempt.id,
            'auto_submitted': False,
        })

    @action(detail=True, methods=['get'])
    def result(self, request, pk=None):
        """View results if visibility allows."""
        attempt = self.get_object()
        
        if attempt.status in ('in-progress', 'upload_pending'):
            return Response({'detail': 'Exam not yet submitted.'}, status=status.HTTP_400_BAD_REQUEST)
            
        if attempt.examination.result_visibility == 'manual' and attempt.status != 'evaluated':
            return Response({'detail': 'Result pending manual review.'}, status=status.HTTP_403_FORBIDDEN)
            
        if attempt.examination.result_visibility == 'after_end':
            if attempt.examination.end_time and timezone.now() < attempt.examination.end_time:
                return Response({'detail': 'Result will be available after the exam window ends.'}, status=status.HTTP_403_FORBIDDEN)

        # Subjective answer-sheet uploads are a separate flow from the canonical
        # in-app descriptive-exam path. Only uploaded submissions that exist and
        # are still unpublished should block the student's result view.
        from .attempt_timing import is_subjective_exam
        if is_subjective_exam(attempt):
            sub = getattr(attempt, 'subjective_submission', None)
            if sub is not None and not sub.is_published:
                return Response({
                    'detail': 'Your answer sheet has been submitted. Your result is currently being evaluated.',
                    'status': attempt.status,
                    'is_published': False,
                    'needs_evaluation': True,
                }, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(attempt)
        return Response(serializer.data)

    @action(detail=True, methods=['get', 'post'], url_path='answer-sheet')
    def answer_sheet(self, request, pk=None):
        if request.method == 'GET':
            return self.get_answer_sheet(request, pk)
        return self.upload_answer_sheet(request, pk)

    def upload_answer_sheet(self, request, pk=None):
        attempt = self.get_object()
        from .attempt_timing import is_subjective_exam, is_subjective_upload_open
        from .subjective_service import SubjectivePdfService
        from .models import SubjectiveSubmission, SubjectiveSubmissionPage

        if not is_subjective_exam(attempt):
            return Response(
                {'detail': 'Answer sheet upload is only supported for Subjective Examinations.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Enforce server-authoritative upload deadline
        if not is_subjective_upload_open(attempt):
            return Response(
                {'detail': 'The answer sheet upload window has closed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Retrieve files
        uploaded_files = request.FILES.getlist('images') or request.FILES.getlist('files')
        single_pdf = request.FILES.get('pdf_file') or request.FILES.get('file')

        # If a single file was passed under 'images' or 'files' but it's a PDF, treat it as single_pdf
        if not single_pdf and uploaded_files and len(uploaded_files) == 1:
            first_f = uploaded_files[0]
            first_name = first_f.name.lower()
            first_f.seek(0)
            header_sample = first_f.read(10)
            first_f.seek(0)
            if first_name.endswith('.pdf') or header_sample.startswith(b'%PDF-') or getattr(first_f, 'content_type', '') in ['application/pdf', 'application/x-pdf']:
                single_pdf = first_f
                uploaded_files = []

        if not uploaded_files and not single_pdf:
            return Response(
                {'detail': 'Please provide at least one answer sheet image or a PDF file.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate max upload size
        max_mb = getattr(attempt.examination, 'max_upload_size_mb', 50) or 50
        max_bytes = max_mb * 1024 * 1024

        submission, _ = SubjectiveSubmission.objects.get_or_create(attempt=attempt)
        submission.status = 'processing'
        submission.save(update_fields=['status'])

        try:
            if single_pdf:
                if single_pdf.size < 100:
                    submission.status = 'processing_failed'
                    submission.save(update_fields=['status'])
                    return Response(
                        {'detail': 'The uploaded PDF file is empty or corrupted.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if single_pdf.size > max_bytes:
                    submission.status = 'processing_failed'
                    submission.save(update_fields=['status'])
                    return Response(
                        {'detail': f'File exceeds maximum allowed upload size of {max_mb}MB.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                content_file, page_count, total_bytes = SubjectivePdfService.validate_and_process_pdf(single_pdf)
                submission.pages.all().delete()
            else:
                total_size = sum(f.size for f in uploaded_files)
                if total_size > max_bytes:
                    submission.status = 'processing_failed'
                    submission.save(update_fields=['status'])
                    return Response(
                        {'detail': f'Total upload size exceeds maximum limit of {max_mb}MB.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Sort by page order if page_order is provided
                page_order_str = request.data.get('page_order')
                if page_order_str:
                    try:
                        import json
                        if isinstance(page_order_str, str) and page_order_str.startswith('['):
                            order_list = json.loads(page_order_str)
                        else:
                            order_list = [x.strip() for x in page_order_str.split(',') if x.strip()]
                        file_map = {f.name: f for f in uploaded_files}
                        ordered_files = [file_map[name] for name in order_list if name in file_map]
                        for f in uploaded_files:
                            if f not in ordered_files:
                                ordered_files.append(f)
                        uploaded_files = ordered_files
                    except Exception:
                        pass

                images_data = []
                for f in uploaded_files:
                    f.seek(0)
                    images_data.append((f.name, f))

                content_file, page_count, total_bytes = SubjectivePdfService.process_and_merge_images(images_data)

                # Save individual pages
                submission.pages.all().delete()
                for idx, (fname, file_obj) in enumerate(images_data):
                    file_obj.seek(0)
                    ext = os.path.splitext(fname)[1].lower()
                    if not ext or ext not in ['.jpg', '.jpeg', '.png', '.webp', '.pdf']:
                        ext = '.jpg'
                    file_obj.name = f"page_{idx+1:03d}{ext}"
                    SubjectiveSubmissionPage.objects.create(
                        submission=submission,
                        page_number=idx + 1,
                        image_file=file_obj,
                        file_size_bytes=file_obj.size,
                    )

            submission.answer_pdf = content_file
            submission.page_count = page_count
            submission.file_size_bytes = total_bytes
            submission.status = 'submitted'
            submission.save()

            now = timezone.now()
            attempt.status = 'submitted'
            attempt.submitted_at = now
            if attempt.started_at:
                attempt.time_taken_seconds = max(0, int((now - attempt.started_at).total_seconds()))
            attempt.save(update_fields=['status', 'submitted_at', 'time_taken_seconds'])

            # Send notification to admins upon successful answer sheet submission
            try:
                from core.notification_service import NotificationService
                NotificationService.notify_admins_subjective_submission(submission)
            except Exception as notif_err:
                import logging
                logging.getLogger(__name__).warning("Failed to send admin subjective submission notification: %s", notif_err)

            return Response({
                'detail': 'Answer sheet uploaded and submitted successfully.',
                'submission_id': submission.id,
                'page_count': page_count,
                'file_size_bytes': total_bytes,
                'attempt_status': attempt.status,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            submission.status = 'processing_failed'
            submission.save(update_fields=['status'])
            return Response(
                {'detail': f'Failed to process answer sheet: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    def get_answer_sheet(self, request, pk=None):
        attempt = self.get_object()
        if not hasattr(attempt, 'subjective_submission') or not attempt.subjective_submission.answer_pdf:
            return Response({'detail': 'No answer-sheet PDF found.'}, status=status.HTTP_404_NOT_FOUND)

        from django.http import FileResponse
        try:
            return FileResponse(attempt.subjective_submission.answer_pdf.open('rb'), content_type='application/pdf')
        except Exception as e:
            return Response({'detail': f'Could not open answer-sheet PDF: {e}'}, status=status.HTTP_404_NOT_FOUND)


class TeacherExaminationAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Subjective evaluation queue for the canonical Examination architecture.

    Read + one write action (evaluate) rather than a full ModelViewSet -
    grading assigns marks to existing StudentAnswer rows, it never creates
    or deletes attempts. Any teacher/admin may grade any attempt (mirrors
    the existing legacy SubjectiveAnswer evaluation queue's access model -
    evaluation is a shared queue, not scoped to "your own students").
    """
    permission_classes = [IsAuthenticated, IsEvaluatorUser]
    # The 'pending' list filter below returns a plain Python list (built
    # from a per-answer check that can't be expressed as a queryset filter
    # without duplicating SUBJECTIVE_TYPES into SQL) - this queue is small
    # (submitted subjective attempts only), so pagination is skipped rather
    # than built around a list.
    pagination_class = None

    def get_serializer_class(self):
        from .serializers import (
            ExaminationAttemptEvaluationListSerializer,
            ExaminationAttemptEvaluationSerializer,
        )
        if self.action == 'list':
            return ExaminationAttemptEvaluationListSerializer
        return ExaminationAttemptEvaluationSerializer

    def get_queryset(self):
        # Only attempts on exams that actually contain a subjective question
        # belong in this queue - a pure-MCQ attempt is already fully scored.
        qs = (
            ExaminationAttempt.objects
            .filter(
                status__in=['submitted', 'evaluated'],
                examination__exam_type='subjective',
            )
            .select_related('examination', 'student')
            .prefetch_related('answers__question')
            .order_by('-submitted_at')
        )
        status_param = self.request.query_params.get('status')
        if status_param == 'pending':
            # Can't filter "has an ungraded subjective answer" in the DB
            # without duplicating the SUBJECTIVE_TYPES check into a query -
            # this queue is small enough (submitted subjective attempts
            # only) that an in-Python filter here is simpler and correct.
            qs = [a for a in qs if any(
                ans.question.question_type in Question.SUBJECTIVE_TYPES and ans.evaluated_at is None
                for ans in a.answers.all()
            )]
        return qs

    @action(detail=True, methods=['post'])
    def evaluate(self, request, pk=None):
        """
        Body: {"answers": [{"answer_id": 1, "marks_awarded": 8}, ...]}
        Each answer_id must belong to this attempt and be a subjective
        question - MCQ answers are auto-graded and cannot be overridden here.
        """
        attempt = self.get_object()
        entries = request.data.get('answers', [])
        if not entries:
            return Response({'detail': 'answers is required.'}, status=status.HTTP_400_BAD_REQUEST)

        answers_by_id = {a.id: a for a in attempt.answers.select_related('question').all()}
        now = timezone.now()
        updated = 0

        for entry in entries:
            answer_id = entry.get('answer_id')
            marks = entry.get('marks_awarded')
            answer = answers_by_id.get(answer_id)
            if not answer or marks is None:
                continue
            if answer.question.question_type not in Question.SUBJECTIVE_TYPES:
                return Response(
                    {'detail': f'Question {answer.question_id} is objective and auto-graded - it cannot be manually evaluated.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                marks = float(marks)
            except (TypeError, ValueError):
                return Response({'detail': f'Invalid marks_awarded for answer {answer_id}.'}, status=status.HTTP_400_BAD_REQUEST)
            if marks < 0 or marks > answer.question.marks:
                return Response(
                    {'detail': f'marks_awarded for answer {answer_id} must be between 0 and {answer.question.marks}.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            answer.marks_awarded = marks
            answer.evaluated_at = now
            answer.save(update_fields=['marks_awarded', 'evaluated_at'])
            updated += 1

        if updated == 0:
            return Response({'detail': 'No valid answers to evaluate.'}, status=status.HTTP_400_BAD_REQUEST)

        recompute_after_evaluation(attempt)
        serializer_class = self.get_serializer_class()
        return Response(serializer_class(attempt, context={'request': request}).data)


def _build_leaderboard_data(request):
    """
    Build a leaderboard from ExaminationAttempt.

    Strategy:
    - Include status 'submitted' or 'evaluated'
    - Best attempt per student per exam is used
    - Returns a list of dicts with student info and ranking data
    """
    exam_id_param = request.query_params.get('exam', 'all')
    time_filter = request.query_params.get('time_filter', 'all')
    ranking_type = request.query_params.get('ranking_type', 'overall')
    search_query = request.query_params.get('search', '').strip()

    # A single leaderboard page view hits list, my-rank and stats
    # independently, and each used to redo this same full-table scan and
    # in-memory ranking from scratch. The ranking only needs to reflect
    # recently submitted exams, not the current second, so a short cache
    # keyed by the exact filter combination lets those three calls (and
    # back-to-back requests from other students browsing the same filters)
    # share one computed ranking instead of recomputing it every time.
    cache_key = 'leaderboard:' + '|'.join([exam_id_param, time_filter, ranking_type, search_query])
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    now = timezone.now()
    
    # ---- ExaminationAttempt ----
    exam_qs = ExaminationAttempt.objects.filter(status__in=['submitted', 'evaluated'])
    
    if exam_id_param != 'all':
        exam_qs = exam_qs.filter(examination_id=exam_id_param)
    
    if time_filter == 'year':
        exam_qs = exam_qs.filter(submitted_at__year=now.year)
    elif time_filter == 'month':
        exam_qs = exam_qs.filter(submitted_at__year=now.year, submitted_at__month=now.month)
    elif time_filter == 'week':
        exam_qs = exam_qs.filter(submitted_at__gte=now - timezone.timedelta(days=7))
    
    if search_query:
        exam_qs = exam_qs.filter(
            student__username__icontains=search_query
        ) | exam_qs.filter(
            student__first_name__icontains=search_query
        ) | exam_qs.filter(
            student__last_name__icontains=search_query
        )

    # Build per-student aggregated data
    # Key: student_id -> best stats
    student_map = {}
    
    def _get_display_name(student):
        name = f"{student.first_name} {student.last_name}".strip()
        return name if name else student.username
    
    # Process ExaminationAttempt (best attempt = highest percentage per student)
    for attempt in exam_qs.select_related('student', 'examination'):
        sid = attempt.student.id
        total_marks = attempt.examination.total_marks or 100
        pct = attempt.percentage if attempt.percentage is not None else 0
        score = attempt.score if attempt.score is not None else 0
        
        if sid not in student_map:
            student_map[sid] = {
                'student_id': sid,
                'student_name': _get_display_name(attempt.student),
                'profile_image': attempt.student.avatar or None,
                'best_percentage': pct,
                'best_score': score,
                'total_exams': 1,
                'avg_percentage': pct,
                'sum_percentage': pct,
            }
        else:
            student_map[sid]['total_exams'] += 1
            student_map[sid]['sum_percentage'] += pct
            student_map[sid]['avg_percentage'] = student_map[sid]['sum_percentage'] / student_map[sid]['total_exams']
            if pct > student_map[sid]['best_percentage']:
                student_map[sid]['best_percentage'] = pct
                student_map[sid]['best_score'] = score

    # Determine sort key based on ranking_type
    if ranking_type == 'overall':
        # Sort by average percentage then best_score
        students = sorted(student_map.values(), key=lambda x: (-x['avg_percentage'], -x['best_score']))
        score_field = 'avg_percentage'
    else:
        # Sort by best percentage then best_score
        students = sorted(student_map.values(), key=lambda x: (-x['best_percentage'], -x['best_score']))
        score_field = 'best_percentage'
    
    # Assign DenseRank (ties get the same rank)
    ranked = []
    current_rank = 0
    prev_key = None
    for i, s in enumerate(students):
        sort_key = (round(s['avg_percentage' if ranking_type == 'overall' else 'best_percentage'], 4), round(s['best_score'], 4))
        if sort_key != prev_key:
            current_rank = i + 1
            prev_key = sort_key
        
        ranked.append({
            'rank': current_rank,
            'student_id': s['student_id'],
            'student_name': s['student_name'],
            'profile_image': s['profile_image'],
            'score': round(s['best_score'], 2),
            'percentage': round(s['avg_percentage' if ranking_type == 'overall' else 'best_percentage'], 2),
            'total_exams': s['total_exams'],
        })

    cache.set(cache_key, ranked, 30)
    return ranked


class LeaderboardViewSet(viewsets.ViewSet):
    """
    Provides leaderboard rankings for students based on ExaminationAttempt data.
    """
    permission_classes = [IsAuthenticated, HasActiveSubscription]

    def list(self, request):
        try:
            ranked = _build_leaderboard_data(request)
        except Exception as e:
            return Response({'detail': f'Error building leaderboard: {str(e)}'}, status=500)
        
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        start = (page - 1) * page_size
        end = start + page_size
        
        count = len(ranked)
        paginated = ranked[start:end]

        return Response({
            'count': count,
            'next': page + 1 if end < count else None,
            'previous': page - 1 if page > 1 else None,
            'results': paginated
        })

    @action(detail=False, methods=['get'], url_path='my-rank')
    def my_rank(self, request):
        try:
            ranked = _build_leaderboard_data(request)
        except Exception as e:
            return Response({'detail': f'Error building leaderboard: {str(e)}'}, status=500)
        
        user_id = request.user.id
        my_item = next((item for item in ranked if item['student_id'] == user_id), None)

        if not my_item:
            return Response({'detail': 'No ranking data available for current user.'}, status=404)

        return Response(my_item)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        try:
            ranked = _build_leaderboard_data(request)
        except Exception as e:
            return Response({'detail': f'Error building stats: {str(e)}'}, status=500)
        
        total_participants = len(ranked)
        avg_pct = 0
        highest_pct = 0

        if total_participants > 0:
            percentages = [item['percentage'] for item in ranked]
            avg_pct = sum(percentages) / total_participants
            highest_pct = max(percentages)

        return Response({
            'totalParticipants': total_participants,
            'averageScore': round(avg_pct, 1),
            'highestScore': round(highest_pct, 1)
        })
class CalmSessionLogView(APIView):
    permission_classes = [IsAuthenticated, HasActiveSubscription]
    
    def post(self, request):
        event_type = request.data.get('event_type')
        meta_data = request.data.get('meta_data', {})
        
        if not event_type:
            return Response({'detail': 'event_type is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        CalmSessionLog.objects.create(
            student=request.user,
            event_type=event_type,
            meta_data=meta_data
        )
        return Response({'status': 'logged'})
