from rest_framework import viewsets, permissions, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Exam, Subject, Topic, Question, PracticeSession, QuestionAttempt, UserTopicProgress, QuestionMastery
from .serializers import (
    ExamSerializer, SubjectSerializer, TopicSerializer,
    QuestionFullSerializer, SecureQuestionSerializer, PracticeSessionSerializer, PracticeSessionSummarySerializer,
    UserTopicProgressSerializer
)
from .selection_service import QuestionSelectionService
from subscriptions.permissions import HasActiveSubscription

# Minimum answered questions in a topic before its accuracy counts as a
# "weak topic" signal — avoids flagging a topic off one unlucky guess.
WEAK_TOPIC_MIN_ANSWERED = 3
WEAK_TOPIC_ACCURACY_THRESHOLD = 60
RECENT_MISTAKE_WINDOW_DAYS = 7
REVISION_SESSION_SIZE = 20


def _practice_exam_scope(user, course_id=None):
    """Resolve practice content to the student's active or requested course."""
    from courses.access import authorized_courses, authorized_exam_ids, get_course_exam_ids, get_student_course_context
    from courses.models import Course

    if course_id in (None, '') and getattr(user, 'role', None) == 'student':
        active_course = get_student_course_context(user).get('active_course')
        course_id = active_course.get('id') if active_course else None

    if course_id not in (None, ''):
        try:
            course_id = int(course_id)
        except (TypeError, ValueError):
            return set()
        courses = authorized_courses(user) if getattr(user, 'role', None) == 'student' else Course.objects.filter(status='published')
        course = courses.filter(id=course_id, status='published').first()
        return get_course_exam_ids(course) if course else set()

    return authorized_exam_ids(user)


def _revision_buckets(user, course_id=None):
    """Group the user's QuestionMastery history into the signals Revision
    Mode is built on. Never reads Bookmark — saving a question must never
    be mistaken for a weakness signal."""
    from django.utils import timezone
    from django.db.models import Sum

    now = timezone.now()
    service = QuestionSelectionService()
    scope = _practice_exam_scope(user, course_id)
    pool = service.get_base_queryset()
    if scope is not None:
        # Revision draws on the student's own history, but only from exams
        # they are (still) authorised for.
        pool = service.apply_filters(pool, exam_ids=scope)
    approved_ids = pool.values_list('id', flat=True)
    mastery = QuestionMastery.objects.filter(user=user, question_id__in=approved_ids).select_related('question')

    overdue = list(mastery.filter(next_review_at__lte=now).order_by('next_review_at'))
    repeatedly_incorrect = list(
        mastery.filter(consecutive_incorrect__gte=2).order_by('-consecutive_incorrect', '-updated_at')
    )
    week_ago = now - timezone.timedelta(days=RECENT_MISTAKE_WINDOW_DAYS)
    recent_mistakes = list(
        mastery.filter(consecutive_incorrect__gte=1, last_attempted_at__gte=week_ago).order_by('-last_attempted_at')
    )

    topic_stats = (
        mastery.exclude(times_answered=0)
        .values('question__topic')
        .annotate(answered=Sum('times_answered'), correct=Sum('times_correct'))
    )
    weak_topic_ids = [
        t['question__topic'] for t in topic_stats
        if t['answered'] >= WEAK_TOPIC_MIN_ANSWERED and (t['correct'] * 100 / t['answered']) < WEAK_TOPIC_ACCURACY_THRESHOLD
    ]
    weak_topics = (
        list(mastery.filter(question__topic_id__in=weak_topic_ids).order_by('question__topic'))
        if weak_topic_ids else []
    )

    return {
        'overdue': overdue,
        'repeatedly_incorrect': repeatedly_incorrect,
        'recent_mistakes': recent_mistakes,
        'weak_topics': weak_topics,
    }


def _recently_incorrect_questions(user, exam_ids):
    """Return recently incorrect approved questions, using persisted answer history."""
    from django.utils import timezone
    from .models import ExaminationAttempt, StudentAnswer

    since = timezone.now() - timezone.timedelta(days=RECENT_MISTAKE_WINDOW_DAYS)
    service = QuestionSelectionService()
    eligible = service.apply_filters(service.get_base_queryset(), exam_ids=exam_ids)
    eligible_ids = eligible.values_list('id', flat=True)
    latest = {}

    def record(question_id, attempted_at, is_correct):
        if attempted_at and (question_id not in latest or attempted_at >= latest[question_id][0]):
            latest[question_id] = (attempted_at, is_correct)

    for question_id, attempted_at in QuestionMastery.objects.filter(
        user=user,
        question_id__in=eligible_ids,
        consecutive_incorrect__gte=1,
        last_attempted_at__gte=since,
    ).values_list('question_id', 'last_attempted_at'):
        record(question_id, attempted_at, False)

    for question_id, attempted_at, is_correct in QuestionAttempt.objects.filter(
        session__user=user,
        viewed_at__gte=since,
        question_id__in=eligible_ids,
    ).exclude(selected_option__isnull=True).exclude(selected_option='').values_list(
        'question_id', 'viewed_at', 'is_correct'
    ):
        record(question_id, attempted_at, is_correct)

    for question_id, attempted_at, is_correct in StudentAnswer.objects.filter(
        attempt__student=user,
        attempt__status__in=('submitted', 'evaluated'),
        attempt__submitted_at__gte=since,
        question_id__in=eligible_ids,
    ).exclude(selected_option__isnull=True).exclude(selected_option='').values_list(
        'question_id', 'attempt__submitted_at', 'is_correct'
    ):
        record(question_id, attempted_at, is_correct)

    ordered_ids = [
        question_id for question_id, (_at, correct) in
        sorted(latest.items(), key=lambda item: item[1][0], reverse=True)
        if not correct
    ]
    questions_by_id = {question.id: question for question in eligible.filter(id__in=ordered_ids)}
    return [questions_by_id[question_id] for question_id in ordered_ids if question_id in questions_by_id]


def _dedup_questions(mastery_records, limit=None):
    seen = set()
    questions = []
    for m in mastery_records:
        if m.question_id not in seen:
            seen.add(m.question_id)
            questions.append(m.question)
            if limit and len(questions) >= limit:
                break
    return questions


class ExamViewSet(viewsets.ReadOnlyModelViewSet):
    """The exams a user may browse and practise.

    Staff see every active exam. A student sees only the exams their
    purchase / enrollment authorises (courses.access.authorized_exam_ids) -
    decided here on the server, so the Practice dropdown and a hand-typed
    /api/exams/<id>/ agree: an exam outside the set is simply not found (404).
    Behind the same package gate as Practice itself.
    """
    queryset = Exam.objects.filter(is_active=True)  # router basename; get_queryset adds the prefetch
    serializer_class = ExamSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveSubscription]

    def list(self, request, *args, **kwargs):
        from collections import Counter
        exams = list(self.filter_queryset(self.get_queryset()))
        counts = Counter(e.name for e in exams)
        context = self.get_serializer_context()
        context['duplicate_exam_names'] = {name for name, n in counts.items() if n > 1}
        return Response(ExamSerializer(exams, many=True, context=context).data)

    def get_queryset(self):
        from django.db.models import Prefetch
        from courses.access import authorized_courses, authorized_exam_ids, get_course_exam_ids
        from .models import Paper, Chapter
        from courses.models import Course

        # The response nests exam -> subjects -> chapters -> topics. Without
        # prefetching, every level ran one query per parent (8 chapter and 8
        # topic queries here, 16 for subjects) - and each round trip to the
        # hosted database costs ~170ms.
        qs = Exam.objects.filter(is_active=True).select_related('parent', 'category').prefetch_related(
            Prefetch('papers', queryset=Paper.objects.prefetch_related(
                Prefetch('subjects', queryset=Subject.objects.prefetch_related(
                    Prefetch('chapters', queryset=Chapter.objects.prefetch_related('topics'))
                ))
            ))
        ).order_by('category_id', 'order', 'id')

        course_id = self.request.query_params.get('course_id')
        if course_id is not None:
            try:
                course_id = int(course_id)
            except (TypeError, ValueError):
                return Exam.objects.none()

            if self.request.user.role in ('teacher', 'admin', 'super-admin'):
                course = Course.objects.filter(id=course_id, status='published').first()
            else:
                course = authorized_courses(self.request.user).filter(id=course_id, status='published').first()

            if course is None:
                return Exam.objects.none()

            exam_ids = get_course_exam_ids(course)
            return qs.filter(id__in=exam_ids) if exam_ids else Exam.objects.none()

        scope = authorized_exam_ids(self.request.user)
        return qs if scope is None else qs.filter(id__in=scope)

class SubjectViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer

    def get_queryset(self):
        queryset = Subject.objects.all()
        # Subject has no direct `exam` FK - it reaches Exam through Paper.
        exam_id = self.request.query_params.get('exam')
        if exam_id:
            queryset = queryset.filter(paper__exam_id=exam_id).distinct()
        return queryset

class TopicViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer
    filterset_fields = ['subject']

    @action(detail=True, methods=['get'])
    def content(self, request, pk=None):
        topic = self.get_object()
        from notes.models import StudyMaterial
        from notes.serializers import StudyMaterialDetailSerializer, with_student_state
        from courses.models import Enrollment
        from django.db.models import Q
        
        # Enforce Enrollment Access Control for materials
        active_courses = Enrollment.objects.filter(student=request.user, status='active').values_list('course_id', flat=True)
        materials = StudyMaterial.objects.filter(topic=topic, status='published')
        materials = materials.filter(Q(course__isnull=True) | Q(course_id__in=active_courses))
        materials = with_student_state(
            materials.select_related('subject', 'chapter', 'topic', 'course', 'exam', 'exam__parent', 'exam__category'),
            request.user)

        materials_data = StudyMaterialDetailSerializer(materials, many=True, context={'request': request}).data
        
        return Response({
            'id': topic.id,
            'name': topic.name,
            'description': topic.description,
            'materials': materials_data
        })

class QuestionViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only, student-reachable question catalog.

    Only APPROVED questions from the Master Question Bank are ever exposed
    here, and answers are hidden via SecureQuestionSerializer — this endpoint
    has no teacher/admin ownership scoping, so it must never return
    draft/pending/rejected questions or answer keys.
    """
    # Class-level `queryset` is kept only so DRF's router can infer a
    # basename/schema; every actual request is served by get_queryset()
    # below, which is the one that enforces the approval filter.
    queryset = Question.objects.all()
    serializer_class = SecureQuestionSerializer
    filterset_fields = ['topic', 'difficulty']

    def get_queryset(self):
        from courses.access import authorized_exam_ids
        service = QuestionSelectionService()
        scope = authorized_exam_ids(self.request.user)
        qs = service.get_base_queryset()
        # A student only ever sees questions of exams they are authorised for.
        return qs if scope is None else service.apply_filters(qs, exam_ids=scope)

    @action(detail=False, methods=['get'])
    def practice_set(self, request):
        topic_id = request.query_params.get('topic')
        difficulty = request.query_params.get('difficulty')
        limit = int(request.query_params.get('limit', 20))

        difficulty_distribution = {difficulty: limit} if difficulty and difficulty != 'all' else None

        # Use the centralized selection service — approved questions only.
        service = QuestionSelectionService()
        result = service.select(
            topic_id=topic_id if topic_id else None,
            count=limit,
            difficulty_distribution=difficulty_distribution,
            randomize=True,
            question_type='objective',  # MCQ practice UI: never written-answer questions
        )
        serializer = self.get_serializer(result['questions'], many=True)
        return Response(serializer.data)

# Topic-wise practice shows a fixed page of questions at a time (default 20).
STUDY_PAGE_SIZES = (10, 20)
DEFAULT_STUDY_PAGE_SIZE = 20
OPTION_LETTERS = ('a', 'b', 'c', 'd')
# Modes that reveal correctness the moment a question is answered. Their
# first answer is final (the UI locks the question); flexible/timed sessions
# are scored at submit, so the student may change an answer until then.
IMMEDIATE_FEEDBACK_MODES = ('study', 'revision', 'daily', 'saved')


def _note_study_activity(user):
    """Tell gamification the student studied today - at most one cheap cache hit
    per answer, and one small write per Nepal day."""
    from django.core.cache import cache
    from django.utils import timezone
    from zoneinfo import ZoneInfo
    key = f"study-activity:{user.pk}:{timezone.localtime(timezone.now(), ZoneInfo('Asia/Kathmandu')).date()}"
    try:
        if not cache.add(key, 1, 60 * 60 * 30):
            return
    except Exception:
        pass
    try:
        from gamification.services import record_study_activity
        record_study_activity(user)
    except Exception:
        pass


def _attempt_state(attempt):
    """Per-question state the frontend rehydrates from. Correct option and
    explanation are only sent for questions the student has already answered
    or revealed - never for ones they haven't touched."""
    entry = {
        'question_id': attempt.question_id,
        'selected_option': attempt.selected_option,
        'is_correct': attempt.is_correct if attempt.selected_option else None,
        'is_viewed': attempt.is_viewed,
    }
    if attempt.is_viewed:
        entry['correct_option'] = attempt.question.correct_option
        entry['explanation'] = attempt.question.explanation
    return entry


def _session_stats(session):
    """Totals over the WHOLE session (never just the loaded page) from one
    aggregate query."""
    from django.db.models import Count, Q, Subquery
    # `before_first_open` = how many questions come before the first one the
    # student hasn't touched yet - i.e. its 0-based index, which is where a
    # resumed session should land. Computed in the same query.
    first_open = (
        QuestionAttempt.objects.filter(session=session, is_viewed=False)
        .order_by('id').values('id')[:1]
    )
    agg = QuestionAttempt.objects.filter(session=session).aggregate(
        total=Count('id'),
        answered=Count('id', filter=Q(selected_option__isnull=False) & ~Q(selected_option='')),
        correct=Count('id', filter=Q(selected_option__isnull=False) & ~Q(selected_option='') & Q(is_correct=True)),
        before_first_open=Count('id', filter=Q(id__lt=Subquery(first_open))),
    )
    answered = agg['answered']
    return {
        'total': agg['total'],
        'answered': answered,
        'correct': agg['correct'],
        'wrong': answered - agg['correct'],
        'accuracy': round(agg['correct'] * 100 / answered) if answered else 0,
        'resume_index': agg['before_first_open'],
    }


def _clean_page_params(page, page_size):
    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        page_size = DEFAULT_STUDY_PAGE_SIZE
    if page_size not in STUDY_PAGE_SIZES:
        page_size = DEFAULT_STUDY_PAGE_SIZE
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = None
    return page, page_size


def _study_page_payload(session, page, page_size, extra=None):
    """One page of a session's fixed question set.

    The set is the QuestionAttempt rows created when the session started,
    read back in id order - so it never reshuffles between pages and no
    selection runs again. Only this page's questions are loaded/serialized.
    """
    attempts_qs = QuestionAttempt.objects.filter(session=session)
    stats = _session_stats(session)
    total = stats['total']
    total_pages = max(1, -(-total // page_size))

    if page is None:
        # Land on the page holding the first question the student hasn't
        # touched yet, so resuming doesn't drop them back at question 1.
        page = stats['resume_index'] // page_size + 1
    page = min(max(page, 1), total_pages)

    offset = (page - 1) * page_size
    page_attempts = list(
        attempts_qs.select_related('question').order_by('id')[offset:offset + page_size]
    )
    canonical_numbers = {
        question_id: index + 1
        for index, question_id in enumerate(
            attempts_qs.order_by('question_id').values_list('question_id', flat=True)
        )
    }
    questions_data = SecureQuestionSerializer([a.question for a in page_attempts], many=True).data
    for question in questions_data:
        question['canonical_number'] = canonical_numbers[question['id']]
    payload = {
        'session': PracticeSessionSummarySerializer(session).data,
        'questions': questions_data,
        'attempts': [_attempt_state(a) for a in page_attempts],
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'total_questions': total,
        'first_index': offset,
        'stats': stats,
    }
    if extra:
        payload.update(extra)
    return payload


def _new_study_page_payload(session, question_ids, page, page_size):
    """Response for a session that was JUST created: every attempt is
    untouched, so the totals are known without querying them back. Only the
    requested page's questions are loaded."""
    total = len(question_ids)
    total_pages = max(1, -(-total // page_size))
    page = min(max(page or 1, 1), total_pages)
    offset = (page - 1) * page_size
    page_ids = question_ids[offset:offset + page_size]
    by_id = {q.id: q for q in Question.objects.filter(id__in=page_ids)}
    questions = [by_id[i] for i in page_ids if i in by_id]
    canonical_numbers = {question_id: index + 1 for index, question_id in enumerate(sorted(question_ids))}
    questions_data = SecureQuestionSerializer(questions, many=True).data
    for question in questions_data:
        question['canonical_number'] = canonical_numbers[question['id']]
    return {
        'session': PracticeSessionSummarySerializer(session).data,
        'questions': questions_data,
        'attempts': [
            {'question_id': q.id, 'selected_option': None, 'is_correct': None, 'is_viewed': False}
            for q in questions
        ],
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'total_questions': total,
        'first_index': offset,
        'resumed': False,
        'stats': {'total': total, 'answered': 0, 'correct': 0, 'wrong': 0, 'accuracy': 0, 'resume_index': 0},
    }


def _practice_result_payload(session, serializer_data):
    """The result of a COMPLETED session: its totals plus every question with
    the student's answer. Read-only."""
    attempts = (
        QuestionAttempt.objects.filter(session=session)
        .select_related('question').prefetch_related('question__tag_objects')
    )
    return {
        'session': serializer_data,
        'attempts': [{
            'attempt_id': a.id,
            'question': QuestionFullSerializer(a.question).data,
            'selected_option': a.selected_option,
            'is_correct': a.is_correct,
            'is_marked_for_review': a.is_marked_for_review,
        } for a in attempts],
    }


class PracticeSessionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Practice sessions. Read-only through the standard routes: sessions are
    created and mutated only by the purpose-built actions below (create,
    study, daily, start_revision, answer, reveal, submit), so a student can't
    PATCH scores/counters onto their own session or DELETE it."""
    serializer_class = PracticeSessionSummarySerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveSubscription]

    def get_queryset(self):
        return PracticeSession.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        exam_id = request.data.get('exam')
        subject_id = request.data.get('subject')
        topic_id = request.data.get('topic')
        course_id = request.data.get('course')
        difficulty = request.data.get('difficulty')
        mode = request.data.get('mode', 'flexible')
        total_questions = int(request.data.get('total_questions', 20))
        # Optional: draw only from a QuestionCollection (e.g. "Use in Practice"
        # from the admin Collections page) instead of/alongside the syllabus
        # filters above - approval status is still enforced by the service.
        collection_id = request.data.get('collection')
        # Optional structured-Tag filter (search/discovery metadata) - can be
        # combined with the syllabus filters above; never a substitute for
        # collection_id as a question source.
        tag_id = request.data.get('tag')

        # Enforce Enrollment Access Control
        if not course_id and request.user.role == 'student':
            from courses.access import get_student_course_context
            active_course = get_student_course_context(request.user).get('active_course')
            course_id = active_course.get('id') if active_course else None

        exam_filter_ids = None
        if course_id:
            from courses.access import course_access_denial
            from courses.models import Course
            from courses.access import get_course_exam_ids
            denial = course_access_denial(request.user, course_id)
            if denial:
                return Response({'detail': denial[1]}, status=denial[0])
            course = Course.objects.get(id=course_id)
            exam_filter_ids = get_course_exam_ids(course)
            if exam_id and str(exam_id) != 'all':
                try:
                    if int(exam_id) not in exam_filter_ids:
                        return Response({'detail': "This exam is not part of the selected course."}, status=403)
                except (TypeError, ValueError):
                    return Response({'detail': 'Invalid exam.'}, status=400)
            else:
                exam_id = None

        # Exam authorisation. The client's exam id is never trusted: a student
        # may only name an exam their purchase covers, and "all" (or no exam)
        # means "all of MY authorised exams", never the whole platform.
        from courses.access import authorized_exam_ids
        scope = authorized_exam_ids(request.user)
        if exam_filter_ids is None and scope is not None:
            if exam_id and str(exam_id) != 'all':
                try:
                    exam_authorised = int(exam_id) in scope
                except (TypeError, ValueError):
                    return Response({'detail': 'Invalid exam.'}, status=400)
                if not exam_authorised:
                    return Response({'detail': "You don't have access to this exam."}, status=403)
            else:
                exam_filter_ids = scope

        # Build difficulty distribution if a specific difficulty is requested
        difficulty_distribution = None
        if difficulty and difficulty != 'all':
            difficulty_distribution = {difficulty: total_questions}

        # Use centralized selection service — only approved questions
        service = QuestionSelectionService()
        result = service.select(
            exam_id=exam_id if exam_id and str(exam_id) != 'all' else None,
            subject_id=subject_id if subject_id and str(subject_id) != 'all' else None,
            topic_id=topic_id if topic_id and str(topic_id) != 'all' else None,
            collection_id=collection_id if collection_id and str(collection_id) != 'all' else None,
            tag_id=tag_id if tag_id and str(tag_id) != 'all' else None,
            count=total_questions,
            difficulty_distribution=difficulty_distribution,
            randomize=True,
            question_type='objective',  # MCQ practice UI: never written-answer questions
            exam_ids=exam_filter_ids,
        )

        questions = result['questions']

        if len(questions) == 0:
            return Response(
                {'detail': 'No approved questions are available for the selected criteria.'},
                status=400
            )

        if not result['satisfied'] and result['warnings']:
            # We still create the session with available questions, but warn caller
            pass  # warnings are surfaced in response below

        # Resolve exam_id for session record
        resolved_exam_id = exam_id if exam_id and str(exam_id) != 'all' else None
        if not resolved_exam_id:
            first_question = questions[0]
            if first_question.topic_id:
                resolved_exam_id = first_question.topic.chapter.subject.paper.exam_id
            elif first_question.subject_id:
                resolved_exam_id = first_question.subject.paper.exam_id
            if not resolved_exam_id:
                available_scope = exam_filter_ids if exam_filter_ids is not None else scope
                resolved_exam_id = min(available_scope) if available_scope else None

        # Create session
        session = PracticeSession.objects.create(
            user=request.user,
            exam_id=resolved_exam_id,
            subject_id=subject_id if subject_id and str(subject_id) != 'all' else None,
            topic_id=topic_id if topic_id and str(topic_id) != 'all' else None,
            mode=mode,
            difficulty=difficulty if difficulty and difficulty != 'all' else None,
            total_questions=len(questions)
        )

        QuestionAttempt.objects.bulk_create([QuestionAttempt(session=session, question=q) for q in questions])

        from .serializers import SecureQuestionSerializer
        response_data = {
            'session': PracticeSessionSummarySerializer(session).data,
            'questions': SecureQuestionSerializer(questions, many=True).data,
            'selection_info': {
                'available': result['available'],
                'requested': result['requested'],
                'selected': result['selected'],
                'satisfied': result['satisfied'],
                'warnings': result['warnings'],
            }
        }
        return Response(response_data)

    @action(detail=True, methods=['post'])
    def view(self, request, pk=None):
        """Record that a question was displayed to the student, without marking it answered."""
        session = self.get_object()
        question_id = request.data.get('question_id')

        try:
            attempt = QuestionAttempt.objects.get(session=session, question_id=question_id)
            if not attempt.is_viewed:
                from django.utils import timezone
                attempt.is_viewed = True
                attempt.viewed_at = timezone.now()
                attempt.save(update_fields=['is_viewed', 'viewed_at'])
            return Response({'status': 'success'})
        except (QuestionAttempt.DoesNotExist, ValueError, TypeError):
            return Response({'detail': 'Question not found in this session.'}, status=404)

    @action(detail=True, methods=['post'])
    def answer(self, request, pk=None):
        from django.db import transaction
        from django.utils import timezone

        session = self.get_object()
        if session.completed:
            return Response({'detail': 'Session already completed.'}, status=400)

        question_id = request.data.get('question_id')
        selected_option = request.data.get('selected_option')
        is_marked_for_review = bool(request.data.get('is_marked_for_review', False))

        if selected_option is not None:
            selected_option = str(selected_option).strip().lower()
            if selected_option not in OPTION_LETTERS:
                return Response({'detail': 'Choose one of the options A, B, C or D.'}, status=400)

        try:
            # Row lock: two identical requests (double click, retry after a
            # slow response) queue up here, so the second sees the first
            # one's saved answer instead of writing a second one.
            with transaction.atomic():
                attempt = (
                    QuestionAttempt.objects.select_for_update(of=('self',))
                    .select_related('question')
                    .get(session=session, question_id=question_id)
                )
                question = attempt.question
                immediate = session.mode in IMMEDIATE_FEEDBACK_MODES

                if selected_option is not None and immediate and attempt.selected_option:
                    # First answer wins in modes that show the result at once.
                    # Repeating the request returns what was stored and does
                    # not touch attempts, mastery or any counters again.
                    return Response({
                        'status': 'success',
                        'already_answered': True,
                        'selected_option': attempt.selected_option,
                        'is_correct': attempt.is_correct,
                        'correct_option': question.correct_option,
                        'explanation': question.explanation,
                    })

                is_correct = None
                if selected_option is not None:
                    attempt.selected_option = selected_option
                    attempt.is_viewed = True
                    if not attempt.viewed_at:
                        attempt.viewed_at = timezone.now()
                    correct_option = question.correct_option
                    # correct_option is stored uppercase; the frontend sends
                    # lowercase letters - compare case-insensitively.
                    is_correct = bool(correct_option) and selected_option.upper() == correct_option.upper()
                    attempt.is_correct = is_correct

                    # Study/Revision/Saved are no-pressure modes, so score the
                    # answer as soon as it's given -
                    # this is also the single point that feeds Revision Mode's
                    # performance signals (never fed by merely viewing a
                    # question or by Bookmark/Saved Questions).
                    if session.mode in ('study', 'revision', 'saved'):
                        mastery, _ = QuestionMastery.objects.get_or_create(user=session.user, question=question)
                        mastery.record_answer(is_correct)

                attempt.is_marked_for_review = is_marked_for_review
                attempt.save()
        except (QuestionAttempt.DoesNotExist, ValueError, TypeError):
            return Response({'detail': 'Question not found in this session.'}, status=404)

        if selected_option is not None:
            _note_study_activity(request.user)

        response = {'status': 'success'}
        # Flexible/timed sessions are scored at submit - never hand the
        # student the answer key mid-session.
        if is_correct is not None and session.mode in IMMEDIATE_FEEDBACK_MODES:
            response['is_correct'] = is_correct
            response['selected_option'] = selected_option
            response['correct_option'] = question.correct_option
            response['explanation'] = question.explanation
        return Response(response)

    @action(detail=True, methods=['post'])
    def reveal(self, request, pk=None):
        """Show the answer to a question without it counting as an attempt.

        Used by Study/Revision's "Show Answer" action — marks the question
        viewed (never answered) and returns the correct option + explanation.
        """
        session = self.get_object()
        question_id = request.data.get('question_id')

        try:
            attempt = QuestionAttempt.objects.select_related('question').get(session=session, question_id=question_id)
            if not attempt.is_viewed:
                from django.utils import timezone
                attempt.is_viewed = True
                attempt.viewed_at = timezone.now()
                attempt.save(update_fields=['is_viewed', 'viewed_at'])
            return Response({
                'correct_option': attempt.question.correct_option,
                'explanation': attempt.question.explanation,
            })
        except (QuestionAttempt.DoesNotExist, ValueError, TypeError):
            return Response({'detail': 'Question not found in this session.'}, status=404)

    @action(detail=False, methods=['post'])
    def study(self, request):
        """Open-ended Topicwise Study: no timer, no formal submit.

        Resumes an in-progress study session for the topic unless `restart`
        is passed, in which case the old session (and its attempts) is
        discarded and a fresh one is built from every approved question in
        the topic. The question set is fixed once, when the session is
        created; the response carries only one page of it (`page` /
        `page_size`, default 20 - later pages come from `questions/`).
        """
        from django.db import transaction
        from core.models import User

        topic_id = request.data.get('topic')
        subject_id = request.data.get('subject')
        exam_id = request.data.get('exam')
        restart = bool(request.data.get('restart', False))
        shuffle_questions = bool(request.data.get('shuffle_questions', False))
        page, page_size = _clean_page_params(request.data.get('page'), request.data.get('page_size'))

        if not topic_id:
            return Response({'detail': 'topic is required.'}, status=400)

        course_id = request.data.get('course')
        if not course_id and request.user.role == 'student':
            from courses.access import get_student_course_context
            active_course = get_student_course_context(request.user).get('active_course')
            course_id = active_course.get('id') if active_course else None

        # Exam authorisation (students): the exam the client names must be one
        # their purchase covers, and it is what constrains the question pool
        # below - so a topic id from another exam yields nothing.
        scope = _practice_exam_scope(request.user, course_id)
        if scope is not None:
            if not exam_id or str(exam_id) == 'all':
                # No exam named: the topic itself says which exam it belongs to.
                exam_id = Topic.objects.filter(pk=topic_id).values_list(
                    'chapter__subject__paper__exam_id', flat=True
                ).first()
                if not exam_id:
                    return Response({'detail': 'No approved questions are available for this topic yet.'}, status=400)
            try:
                exam_authorised = int(exam_id) in scope
            except (TypeError, ValueError):
                return Response({'detail': 'Invalid exam.'}, status=400)
            if not exam_authorised:
                return Response({'detail': "You don't have access to this exam."}, status=403)

        # Course-scoped study: the same enrollment/published check as create(),
        # and the topic must belong to the course's exam - the client can't
        # pair an authorised course id with somebody else's topic.
        if course_id:
            from courses.access import course_access_denial
            from courses.models import Course
            denial = course_access_denial(request.user, course_id)
            if denial:
                return Response({'detail': denial[1]}, status=denial[0])
            course_exam_id = Course.objects.filter(pk=course_id).values_list('exam_id', flat=True).first()
            if course_exam_id:
                topic_exam_id = Topic.objects.filter(pk=topic_id).values_list(
                    'chapter__subject__paper__exam_id', flat=True
                ).first()
                in_scope = {course_exam_id, *Exam.objects.filter(parent_id=course_exam_id).values_list('id', flat=True)}
                if topic_exam_id not in in_scope:
                    return Response({'detail': 'This topic is not part of the selected course.'}, status=403)

        def find_open_session():
            sessions = PracticeSession.objects.filter(
                user=request.user, topic_id=topic_id, mode='study', completed=False
            )
            if scope is not None:
                sessions = sessions.filter(exam_id__in=scope)   # never resume one whose exam is no longer authorised
            return sessions.order_by('-created_at').first()

        new_question_ids = None
        existing = find_open_session()
        if existing and not restart:
            session = existing
        else:
            # Serialise per student: a double click or a React remount can
            # send two "start" requests at once, and without this both would
            # find "no session yet" and each build one.
            with transaction.atomic():
                User.objects.select_for_update().get(pk=request.user.pk)

                existing = find_open_session()  # may have appeared while we waited
                if existing and restart:
                    existing.delete()
                    existing = None
                    page = None

                if existing:
                    session = existing
                else:
                    # Ids only: the session just records WHICH questions it holds
                    # (as attempts); a page's content is read afterwards. Loading
                    # every full, joined, de-duplicated row of a 100-question
                    # topic here cost ~0.7s for data that was thrown away.
                    question_ids = QuestionSelectionService().select_ids(
                        exam_id=exam_id if exam_id and str(exam_id) != 'all' else None,
                        subject_id=subject_id if subject_id and str(subject_id) != 'all' else None,
                        topic_id=topic_id,
                        limit=None,
                        # Written-answer questions (all of Question.SUBJECTIVE_TYPES,
                        # not just 'subjective') have no options / correct_option and
                        # belong to the subjective-answer system - they can't be shown
                        # in an MCQ browsing screen.
                        question_type='objective',
                    )
                    if not question_ids:
                        return Response({'detail': 'No approved questions are available for this topic yet.'}, status=400)
                    if shuffle_questions:
                        import random
                        random.shuffle(question_ids)

                    resolved_exam_id = exam_id if exam_id and str(exam_id) != 'all' else None
                    if not resolved_exam_id:
                        first_exam = Exam.objects.first()
                        resolved_exam_id = first_exam.id if first_exam else None

                    session = PracticeSession.objects.create(
                        user=request.user,
                        exam_id=resolved_exam_id,
                        subject_id=subject_id if subject_id and str(subject_id) != 'all' else None,
                        topic_id=topic_id,
                        mode='study',
                        shuffle_questions=shuffle_questions,
                        total_questions=len(question_ids),
                    )
                    # One INSERT for the whole set (a topic can hold 100+
                    # questions; one round trip each took ~20s against the
                    # hosted database).
                    QuestionAttempt.objects.bulk_create(
                        [QuestionAttempt(session=session, question_id=qid) for qid in question_ids]
                    )
                    new_question_ids = question_ids

        if existing is None and new_question_ids is not None:
            # Brand-new session: nothing is answered yet, so the first page and
            # the totals are already known - no need to read them back.
            payload = _new_study_page_payload(session, new_question_ids, page, page_size)
        else:
            payload = _study_page_payload(session, page, page_size, extra={'resumed': True})
        payload['resume_index'] = payload['stats']['resume_index']
        return Response(payload)

    @action(detail=True, methods=['get'], url_path='questions')
    def questions(self, request, pk=None):
        """One page of a session's fixed question set, with the student's
        saved state for those questions and whole-session stats."""
        page, page_size = _clean_page_params(request.query_params.get('page', 1), request.query_params.get('page_size'))
        return Response(_study_page_payload(self.get_object(), page or 1, page_size))

    @action(detail=False, methods=['post'])
    def saved(self, request):
        """Start or resume a paged session over the student's saved questions."""
        from django.db import transaction
        from django.db.models import F
        from core.models import User
        from .models import Bookmark

        course_id = request.data.get('course_id')
        scope = _practice_exam_scope(request.user, course_id)
        service = QuestionSelectionService()
        eligible = service.apply_filters(
            service.get_base_queryset(), exam_ids=scope, question_type='objective'
        )
        saved_ids = list(
            Bookmark.objects.filter(user=request.user, question_id__in=eligible.values_list('id', flat=True))
            .order_by(F('custom_order').asc(nulls_last=True), 'created_at', 'id')
            .values_list('question_id', flat=True)
        )
        if not saved_ids:
            return Response({'detail': 'No saved questions are available for this course yet.'}, status=400)

        page, page_size = _clean_page_params(request.data.get('page'), request.data.get('page_size'))
        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.user.pk)
            sessions = PracticeSession.objects.filter(
                user=request.user, mode='saved', completed=False
            )
            if scope is not None:
                sessions = sessions.filter(exam_id__in=scope)
            session = sessions.order_by('-created_at').first()
            if session and request.data.get('restart'):
                session.delete()
                session = None

            if session:
                payload = _study_page_payload(session, page, page_size, extra={'resumed': True})
            else:
                first_question = Question.objects.select_related(
                    'topic__chapter__subject__paper__exam', 'subject__paper__exam'
                ).filter(pk=saved_ids[0]).first()
                exam_id = (
                    first_question.topic.chapter.subject.paper.exam_id
                    if first_question and first_question.topic_id else
                    first_question.subject.paper.exam_id
                    if first_question and first_question.subject_id else None
                )
                if not exam_id:
                    return Response({'detail': 'Saved questions are missing their academic exam context.'}, status=400)
                session = PracticeSession.objects.create(
                    user=request.user,
                    exam_id=exam_id,
                    mode='saved',
                    total_questions=len(saved_ids),
                )
                QuestionAttempt.objects.bulk_create([
                    QuestionAttempt(session=session, question_id=question_id)
                    for question_id in saved_ids
                ])
                payload = _new_study_page_payload(session, saved_ids, page, page_size)

        return Response(payload)

    @action(detail=False, methods=['get'])
    def revision_summary(self, request):
        """Counts behind each Revision Mode signal, without starting a session."""
        from django.core.cache import cache
        course_id = request.query_params.get('course_id')
        scope = _practice_exam_scope(request.user, course_id)
        scope_key = 'all' if scope is None else ','.join(str(value) for value in sorted(scope))
        cache_key = f'student_rev_summary:{request.user.id}:{scope_key}'
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)
        except Exception:
            pass

        buckets = _revision_buckets(request.user, course_id)
        all_records = buckets['overdue'] + buckets['repeatedly_incorrect'] + buckets['recent_mistakes'] + buckets['weak_topics']
        recent_questions = _recently_incorrect_questions(request.user, scope)
        recent_ids = {question.id for question in recent_questions}
        data = {
            'overdue': len({m.question_id for m in buckets['overdue']}),
            'repeatedly_incorrect': len({m.question_id for m in buckets['repeatedly_incorrect']}),
            'recent_mistakes': len(recent_ids),
            'weak_topics': len({m.question_id for m in buckets['weak_topics']}),
            'total_available': len({m.question_id for m in all_records} | recent_ids),
        }
        try:
            cache.set(cache_key, data, 30)
        except Exception:
            pass
        return Response(data)

    @action(detail=False, methods=['post'])
    def start_revision(self, request):
        """Assemble a revision session from the student's own performance history.

        `focus` optionally biases which signal leads the queue (still mixing
        in the others behind it) — lets the practice page's "Weak Topics" /
        "Recently Incorrect" quick-starts point at the same engine instead of
        being separate features.
        """
        from courses.access import authorized_exam_ids

        focus = request.data.get('focus')
        course_id = request.data.get('course_id')
        scope = _practice_exam_scope(request.user, course_id)
        buckets = _revision_buckets(request.user, course_id)

        if focus == 'weak_topics':
            weak_topic_ids = sorted({
                record.question.topic_id
                for record in buckets['weak_topics']
                if record.question.topic_id
            })
            selected = QuestionSelectionService().select(
                exam_ids=scope,
                topic_ids=weak_topic_ids,
                count=REVISION_SESSION_SIZE,
                randomize=True,
                question_type='objective',
            )
            questions = selected['questions']
            question_signal = {question.id: 'weak_topics' for question in questions}
            ordered_records = []
        elif focus == 'recent_mistakes':
            questions = _recently_incorrect_questions(request.user, scope)
            question_signal = {question.id: 'recent_mistakes' for question in questions}
            ordered_records = []
        else:
            question_signal: dict[int, str] = {}
            ordered_records = []
            order = ['overdue', 'repeatedly_incorrect', 'recent_mistakes', 'weak_topics']
            if focus in order:
                order.remove(focus)
                order.insert(0, focus)

            for key in order:
                for record in buckets[key]:
                    if record.question_id not in question_signal:
                        question_signal[record.question_id] = key
                ordered_records += buckets[key]
            questions = _dedup_questions(ordered_records, limit=REVISION_SESSION_SIZE)

        if not questions:
            detail = (
                'No weak topics are available yet. Complete some practice to build your performance profile.'
                if focus == 'weak_topics' else
                'No recently incorrect questions. Keep practicing and this list will update automatically.'
                if focus == 'recent_mistakes' else
                "No revision questions yet — keep practicing and we'll build your revision queue from what you get wrong."
            )
            return Response(
                {'detail': detail},
                status=400
            )

        # Use the student's authorized exam; fall back to any first active exam.
        scope = authorized_exam_ids(request.user)
        if scope:
            session_exam_id = min(scope)
        else:
            first_exam = Exam.objects.filter(is_active=True).first()
            session_exam_id = first_exam.id if first_exam else None

        session = PracticeSession.objects.create(
            user=request.user,
            exam_id=session_exam_id,
            mode='revision',
            total_questions=len(questions),
        )
        QuestionAttempt.objects.bulk_create([QuestionAttempt(session=session, question=q) for q in questions])

        from .serializers import SecureQuestionSerializer
        return Response({
            'session': PracticeSessionSummarySerializer(session).data,
            'questions': SecureQuestionSerializer(questions, many=True).data,
            # Map of question_id -> signal key; used by the frontend to display
            # why each question is in the revision queue.
            'question_signals': question_signal,
        })

    @action(detail=False, methods=['post'])
    def daily(self, request):
        from django.db import transaction
        from core.models import User

        # One Daily session per student per day: lock the student's row so
        # two simultaneous "open Daily Practice" requests (React remount,
        # double click) can't both find no session and each build one.
        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.user.pk)
            return self._daily(request)

    def _daily(self, request):
        """Build (or resume) a Daily Practice session for today.

        Question selection strategy (in priority order):
          1. Questions from the student's weak topics (accuracy < 60 %, min 3 answers)
          2. Questions the student has never seen before across their enrolled exam
          3. Random approved questions from the exam as a fallback

        The session is created once per calendar day and can be resumed if
        the student closes the tab mid-session. A new session is created the
        next calendar day.
        """
        from django.utils import timezone
        from django.db.models import Sum
        import random

        user = request.user
        today = timezone.localdate()
        DAILY_SIZE = 20

        # ── Reuse today's daily session if it already exists ───────────────
        existing = PracticeSession.objects.filter(
            user=user, mode='daily', completed=False,
            created_at__date=today
        ).order_by('-created_at').first()

        if existing:
            attempts = list(
                QuestionAttempt.objects.filter(session=existing)
                .select_related('question')
                .order_by('id')
            )
            resume_index = next((i for i, a in enumerate(attempts) if not a.is_viewed), 0)
            from .serializers import SecureQuestionSerializer
            return Response({
                'session': PracticeSessionSummarySerializer(existing).data,
                'questions': SecureQuestionSerializer(
                    [a.question for a in attempts], many=True
                ).data,
                # Answered / revealed questions come back answered, so a
                # refresh mid-session doesn't wipe the student's progress.
                'attempts': [_attempt_state(a) for a in attempts],
                'resume_index': resume_index,
                'resumed': True,
            })

        # ── Determine the student's enrolled exam ──────────────────────────
        # Daily Practice draws only from the exams the student is authorised
        # for (all exams, for staff) - a Coming Soon / unpublished course or an
        # expired enrollment contributes nothing.
        from courses.access import authorized_exam_ids
        scope = authorized_exam_ids(user)

        base_qs = QuestionSelectionService().get_base_queryset()
        approved_qs = QuestionSelectionService().apply_filters(
            base_qs, exam_ids=scope
        )

        # Exclude questions recently seen (in last 7 days) to maintain freshness
        from django.db.models import Q
        seven_days_ago = timezone.now() - timezone.timedelta(days=7)
        recently_seen_ids = set(
            QuestionAttempt.objects.filter(
                session__user=user,
                is_viewed=True,
                session__created_at__gte=seven_days_ago,
            ).values_list('question_id', flat=True)
        )

        # ── Bucket 1: Weak topic questions ────────────────────────────────
        mastery = QuestionMastery.objects.filter(
            user=user, question_id__in=approved_qs.values_list('id', flat=True)
        ).exclude(times_answered=0)

        topic_stats = mastery.values('question__topic').annotate(
            answered=Sum('times_answered'), correct=Sum('times_correct')
        )
        weak_topic_ids = [
            t['question__topic'] for t in topic_stats
            if t['answered'] >= WEAK_TOPIC_MIN_ANSWERED
            and (t['correct'] * 100 / t['answered']) < WEAK_TOPIC_ACCURACY_THRESHOLD
        ]

        weak_questions = []
        if weak_topic_ids:
            res1 = QuestionSelectionService().select(
                exam_ids=scope,
                topic_ids=weak_topic_ids,
                exclude_ids=list(recently_seen_ids),
                count=DAILY_SIZE,
                question_type='objective',
            )
            weak_questions = res1['questions']

        # ── Bucket 2: Unseen questions ─────────────────────────────────────
        ever_seen_ids = set(
            QuestionAttempt.objects.filter(
                session__user=user, is_viewed=True
            ).values_list('question_id', flat=True)
        )
        unseen_questions = []
        if len(weak_questions) < DAILY_SIZE:
            need = DAILY_SIZE - len(weak_questions)
            already_picked = [q.id for q in weak_questions]
            res2 = QuestionSelectionService().select(
                exam_ids=scope,
                exclude_ids=list(ever_seen_ids) + already_picked,
                count=need,
                question_type='objective',
            )
            unseen_questions = res2['questions']

        # ── Bucket 3: Random fallback ──────────────────────────────────────
        fallback_questions = []
        total_so_far = len(weak_questions) + len(unseen_questions)
        if total_so_far < DAILY_SIZE:
            need = DAILY_SIZE - total_so_far
            already_picked = [q.id for q in weak_questions + unseen_questions]
            res3 = QuestionSelectionService().select(
                exam_ids=scope,
                exclude_ids=already_picked,
                count=need,
                question_type='objective',
            )
            fallback_questions = res3['questions']

        questions = weak_questions + unseen_questions + fallback_questions
        random.shuffle(questions)

        if not questions:
            return Response(
                {'detail': 'No practice questions are available yet. Ask your teacher to publish questions.'},
                status=400,
            )

        if scope:
            session_exam_id = min(scope)
        else:
            first_exam = Exam.objects.first()
            session_exam_id = first_exam.id if first_exam else None
        session = PracticeSession.objects.create(
            user=user,
            exam_id=session_exam_id,
            mode='daily',
            total_questions=len(questions),
        )
        QuestionAttempt.objects.bulk_create([QuestionAttempt(session=session, question=q) for q in questions])

        from .serializers import SecureQuestionSerializer
        return Response({
            'session': PracticeSessionSummarySerializer(session).data,
            'questions': SecureQuestionSerializer(questions, many=True).data,
            'attempts': [
                {'question_id': q.id, 'selected_option': None, 'is_correct': None, 'is_viewed': False}
                for q in questions
            ],
            'resume_index': 0,
            'resumed': False,
        })


    @action(detail=True, methods=['get'])
    def result(self, request, pk=None):
        """Read a finished session's result. Never changes anything: opening
        (or refreshing) a result page must not complete a session - only an
        explicit submit does."""
        session = self.get_object()
        if not session.completed:
            return Response(
                {'detail': 'This practice has not been finished yet.', 'code': 'session_in_progress'},
                status=409,
            )
        return Response(_practice_result_payload(session, self.get_serializer(session).data))

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        session = self.get_object()
        from .serializers import QuestionFullSerializer

        def _attempts_data(attempts):
            return [{
                'attempt_id': attempt.id,
                'question': QuestionFullSerializer(attempt.question).data,
                'selected_option': attempt.selected_option,
                'is_correct': attempt.is_correct,
                'is_marked_for_review': attempt.is_marked_for_review,
            } for attempt in attempts]

        # QuestionFullSerializer('__all__') includes the tag_objects M2M, so
        # every attempts fetch here needs both select_related('question') -
        # for the per-attempt scoring/serialization access to attempt.question
        # below - and prefetch_related('question__tag_objects') - otherwise
        # each is a separate query per attempt (an O(n) round trip each on a
        # 100+ question session was the original cause of ~30s submits).
        if session.completed:
            # Idempotent re-fetch (e.g. the result page re-requesting a
            # session that was already finalized) — still return the full
            # attempts payload the result page needs, not just the session.
            attempts = QuestionAttempt.objects.filter(session=session).select_related('question').prefetch_related('question__tag_objects')
            return Response({
                'session': self.get_serializer(session).data,
                'attempts': _attempts_data(attempts),
            })

        try:
            time_taken_seconds = max(0, int(request.data.get('time_taken_seconds', 0) or 0))
        except (TypeError, ValueError):
            return Response({'detail': 'time_taken_seconds must be a number.'}, status=400)

        from django.db import transaction

        # Score every attempt in Python first, then write the results in one
        # bulk_update instead of one UPDATE per answered attempt - on a
        # fully-answered 100+ question session that was 100+ individual
        # writes. QuestionAttempt has no save()-override, signals, or
        # auto_now fields to preserve (confirmed against the model), so
        # batching the write is behavior-identical to calling .save() per
        # attempt. Wrapped in transaction.atomic() so the attempt scores and
        # the session totals commit together - a mid-submit failure leaves
        # the previous state intact rather than a half-scored session.
        with transaction.atomic():
            # Lock the session row and re-read it: two submits racing (a
            # double click, a retry after a slow response) queue here, and
            # only the first one finalises - so XP is awarded once.
            session = PracticeSession.objects.select_for_update().get(pk=session.pk)
            already_completed = session.completed

            attempts = list(
                QuestionAttempt.objects.filter(session=session)
                .select_related('question')
                .prefetch_related('question__tag_objects')
            )

            if not already_completed:
                correct = 0
                incorrect = 0
                unanswered = 0
                to_score = []

                for attempt in attempts:
                    if not attempt.selected_option:
                        unanswered += 1
                        continue
                    # correct_option is stored uppercase in the DB while the frontend
                    # sends lowercase option letters — compare case-insensitively or
                    # every correct answer is scored as wrong.
                    if attempt.question.correct_option and attempt.selected_option.upper() == attempt.question.correct_option.upper():
                        attempt.is_correct = True
                        correct += 1
                    else:
                        attempt.is_correct = False
                        incorrect += 1
                    to_score.append(attempt)

                if to_score:
                    QuestionAttempt.objects.bulk_update(to_score, ['is_correct'])

                session.correct_count = correct
                session.incorrect_count = incorrect
                session.unanswered_count = unanswered
                session.accuracy = (correct / (correct + incorrect)) * 100 if (correct + incorrect) > 0 else 0
                session.score = correct # No negative marking by default unless specified
                session.time_taken_seconds = time_taken_seconds
                session.completed = True
                session.save()

        if not already_completed:
            # Award XP for practice session (once - only the request that
            # actually finalised the session gets here)
            try:
                from gamification.services import award_xp
                if session.correct_count > 0:
                    award_xp(session.user, session.correct_count, "Practice Session Completed")
            except Exception:
                pass

            try:
                from core.views import invalidate_student_dashboard
                invalidate_student_dashboard(session.user_id)
            except Exception:
                pass

        # After submission, return full data including answers
        return Response({
            'session': self.get_serializer(session).data,
            'attempts': _attempts_data(attempts)
        })

class BookmarkViewSet(viewsets.ModelViewSet):
    from .models import Bookmark
    from .serializers import BookmarkSerializer
    serializer_class = BookmarkSerializer

    def get_queryset(self):
        from django.db.models import F
        scope = _practice_exam_scope(self.request.user, self.request.query_params.get('course_id'))
        eligible = QuestionSelectionService().apply_filters(
            QuestionSelectionService().get_base_queryset(), exam_ids=scope
        )
        return self.Bookmark.objects.filter(
            user=self.request.user,
            question_id__in=eligible.values_list('id', flat=True),
        ).order_by(F('custom_order').asc(nulls_last=True), 'created_at', 'id')

    @action(detail=False, methods=['patch'], url_path='order')
    def set_order(self, request):
        bookmark_ids = request.data.get('bookmark_ids')
        if not isinstance(bookmark_ids, list) or not bookmark_ids:
            return Response({'detail': 'bookmark_ids must be a non-empty list.'}, status=400)

        bookmarks = list(self.get_queryset())
        by_id = {bookmark.id: bookmark for bookmark in bookmarks}
        try:
            requested_ids = [int(bookmark_id) for bookmark_id in bookmark_ids]
        except (TypeError, ValueError):
            return Response({'detail': 'bookmark_ids must contain valid bookmark IDs.'}, status=400)
        if len(set(requested_ids)) != len(requested_ids) or set(requested_ids) != set(by_id):
            return Response({'detail': 'Order must include each authorized saved question exactly once.'}, status=400)

        for order, bookmark_id in enumerate(requested_ids, start=1):
            by_id[bookmark_id].custom_order = order
        self.Bookmark.objects.bulk_update(bookmarks, ['custom_order'])
        return Response({'status': 'ordered', 'count': len(bookmarks)})

    @action(detail=False, methods=['post'], url_path='reset-order')
    def reset_order(self, request):
        count = self.get_queryset().update(custom_order=None)
        return Response({'status': 'reset', 'count': count})

    def create(self, request, *args, **kwargs):
        question_id = request.data.get('question_id')
        scope = _practice_exam_scope(request.user, request.data.get('course_id'))
        eligible = QuestionSelectionService().apply_filters(
            QuestionSelectionService().get_base_queryset(), exam_ids=scope
        )
        if not question_id or not eligible.filter(id=question_id).exists():
            return Response({'detail': 'This question is not available in your authorized course.'}, status=404)
        bookmark, created = self.Bookmark.objects.get_or_create(user=request.user, question_id=question_id)
        if not created:
            # If already exists, toggle it off (delete)
            bookmark.delete()
            return Response({'status': 'removed'})
        return Response({'status': 'added', 'id': bookmark.id})

class UserTopicProgressViewSet(viewsets.ModelViewSet):
    from .models import UserTopicProgress
    from .serializers import UserTopicProgressSerializer
    serializer_class = UserTopicProgressSerializer
    
    def get_queryset(self):
        return self.UserTopicProgress.objects.filter(user=self.request.user)
        
    def create(self, request, *args, **kwargs):
        topic_id = request.data.get('topic')
        status = request.data.get('status', 'not-started')
        progress = request.data.get('progress', 0)
        
        if not topic_id:
            return Response({'error': 'topic is required'}, status=400)
            
        obj, created = self.UserTopicProgress.objects.update_or_create(
            user=request.user,
            topic_id=topic_id,
            defaults={
                'status': status,
                'progress': progress
            }
        )
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        from django.core.cache import cache
        cache_key = f'student_dashboard:{user.id}'
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)
        except Exception:
            pass

        from django.utils import timezone
        from django.db.models import Avg, Sum, Count, Max, Q
        from django.db.models.functions import TruncDate
        
        now = timezone.now()

        # 1. Profile Completion
        try:
            profile = user.student_profile
            completion_score = 40
            if profile.phone: completion_score += 20
            if profile.target_category: completion_score += 20
            if profile.target_position: completion_score += 20
            profile_data = {
                "name": user.get_full_name() or user.username,
                "avatar": user.avatar,
                "targetPosition": profile.target_position.title if profile.target_position else None,
                "completionPercentage": completion_score,
                "phone": profile.phone
            }
        except Exception:
            profile_data = {
                "name": user.get_full_name() or user.username,
                "avatar": user.avatar,
                "targetPosition": None,
                "completionPercentage": 30,
                "phone": ""
            }

        # 2. Stats
        from .models import PracticeSession, QuestionAttempt, ExaminationAttempt, StudentAnswer
        model_attempts = ExaminationAttempt.objects.filter(student=user)
        completed_statuses = ('submitted', 'evaluated')
        practice_sessions = PracticeSession.objects.filter(user=user)

        # Consolidated aggregation for model attempts
        exam_agg = model_attempts.aggregate(
            total=Count('id'),
            completed=Count('id', filter=Q(status__in=completed_statuses)),
            avg_score=Avg('score', filter=Q(status__in=completed_statuses)),
            max_score=Max('score', filter=Q(status__in=completed_statuses)),
            time_sum=Sum('time_taken_seconds', filter=Q(status__in=completed_statuses))
        )
        total_exams = exam_agg['total'] or 0
        completed_exams = exam_agg['completed'] or 0
        avg_score = exam_agg['avg_score'] or 0
        best_score_val = exam_agg['max_score'] or 0
        exam_time = exam_agg['time_sum'] or 0

        # Consolidated aggregation for practice sessions
        practice_agg = practice_sessions.filter(completed=True).aggregate(
            avg_acc=Avg('accuracy'),
            time_sum=Sum('time_taken_seconds')
        )
        avg_accuracy = practice_agg['avg_acc'] or 0
        practice_time = practice_agg['time_sum'] or 0

        exam_questions = StudentAnswer.objects.filter(attempt__student=user).count()
        practice_questions = QuestionAttempt.objects.filter(session__user=user).count()
        questions_attempted = exam_questions + practice_questions

        total_seconds = exam_time + practice_time
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        study_time = f"{hours}h {minutes}m"

        dates = set(model_attempts.annotate(date=TruncDate('started_at')).values_list('date', flat=True))
        dates.update(set(practice_sessions.annotate(date=TruncDate('created_at')).values_list('date', flat=True)))
        sorted_dates = sorted(list(dates), reverse=True)
        
        current_streak = 0
        if sorted_dates:
            check_date = now.date()
            if sorted_dates[0] == check_date or sorted_dates[0] == check_date - timezone.timedelta(days=1):
                curr = sorted_dates[0]
                for d in sorted_dates:
                    if d == curr:
                        current_streak += 1
                        curr = curr - timezone.timedelta(days=1)
                    else:
                        break

        stats = {
            'totalExams': total_exams,
            'completedExams': completed_exams,
            'averageScore': round(avg_score, 1),
            'bestScore': round(best_score_val, 1),
            'accuracy': round(avg_accuracy, 1),
            'questionsAttempted': questions_attempted,
            'studyStreak': current_streak,
            'studyTime': study_time,
            'progress': 0
        }

        # 3. Continue Learning
        continue_learning = None
        in_progress_exam = model_attempts.filter(status='in-progress').select_related('examination').order_by('-started_at').first()
        if in_progress_exam:
            continue_learning = {
                'id': in_progress_exam.id,
                'type': 'model_exam',
                'title': in_progress_exam.examination.title,
                'progress': 0,
                'url': f'/student/exams/{in_progress_exam.examination_id}/attempt/{in_progress_exam.id}'
            }
        else:
            in_progress_practice = practice_sessions.filter(completed=False).select_related('topic').order_by('-created_at').first()
            if in_progress_practice:
                answered = QuestionAttempt.objects.filter(session=in_progress_practice, selected_option__isnull=False).count()
                total = in_progress_practice.total_questions
                continue_learning = {
                    'id': in_progress_practice.id,
                    'type': 'practice',
                    'title': f'Practice: {in_progress_practice.topic.title if in_progress_practice.topic else "Mixed"}',
                    'progress': int((answered / total * 100) if total > 0 else 0),
                    'url': f'/student/practice/session/{in_progress_practice.id}'
                }

        # 4. Today's Plan
        todays_plan = []
        try:
            from study_plan.models import StudyTask
            tasks = StudyTask.objects.filter(study_plan__student=user, date=now.date())
            for t in tasks:
                todays_plan.append({
                    'id': t.id,
                    'title': t.title,
                    'type': t.task_type,
                    'completed': t.status == 'COMPLETED',
                    'duration': t.duration_minutes
                })
        except Exception:
            pass

        # 5. Recent Exams (select_related eliminates N+1 queries)
        recent_exams = []
        for e in model_attempts.filter(status__in=completed_statuses).select_related('examination').order_by('-submitted_at')[:5]:
            recent_exams.append({
                'id': e.id,
                'title': e.examination.title,
                'date': e.submitted_at.strftime('%Y-%m-%d') if e.submitted_at else '',
                'score': float(e.score),
                'percentage': float(e.percentage),
            })

        # 6. Marketplace (select_related eliminates N+1 queries)
        purchases = []
        try:
            from marketplace.models import Purchase, PaymentSubmission
            for p in Purchase.objects.filter(student=user, status='ACTIVE').select_related('product').order_by('-approved_at')[:3]:
                purchases.append({
                    'id': p.id,
                    'title': p.product.title,
                    'status': 'APPROVED',
                    'url': f'/student/marketplace/{p.product.id}'
                })
            for ps in PaymentSubmission.objects.filter(student=user, status='PENDING').select_related('product').order_by('-submitted_at')[:3]:
                purchases.append({
                    'id': ps.id,
                    'title': ps.product.title,
                    'status': 'PENDING',
                    'url': f'/student/marketplace/purchases'
                })
        except Exception:
            pass

        # 7. Support Tickets
        support_tickets = []
        try:
            from support.models import SupportTicket
            tickets = SupportTicket.objects.filter(student=user, status__in=['OPEN', 'IN_PROGRESS']).order_by('-created_at')[:3]
            for t in tickets:
                support_tickets.append({
                    'id': t.id,
                    'title': t.subject,
                    'status': t.status,
                    'url': f'/student/help-support/tickets/{t.id}'
                })
        except Exception:
            pass

        resp_payload = {
            'profile': profile_data,
            'stats': stats,
            'continueLearning': continue_learning,
            'todaysPlan': todays_plan,
            'recentExams': recent_exams,
            'purchases': purchases[:3],
            'supportTickets': support_tickets,
            'subjectPerformance': [
                {"subject": "Constitution", "progress": 72},
                {"subject": "General Knowledge", "progress": 64},
                {"subject": "Current Affairs", "progress": 81}
            ]
        }
        try:
            cache.set(cache_key, resp_payload, 15)
        except Exception:
            pass

        return Response(resp_payload)

# ============================================================
# SUBJECTIVE PRACTICE VIEWS
# ============================================================

class SubjectivePracticeSetViewSet(viewsets.ReadOnlyModelViewSet):
    from .models import SubjectivePracticeSet
    from .serializers import SubjectivePracticeSetSerializer
    serializer_class = SubjectivePracticeSetSerializer

    def get_queryset(self):
        user = self.request.user
        base_qs = self.SubjectivePracticeSet.objects.filter(status='published')
        if not user or not user.is_authenticated:
            return base_qs.none()
        from courses.access import authorized_exam_ids
        allowed_exams = authorized_exam_ids(user)
        if allowed_exams is not None:
            base_qs = base_qs.filter(exam_id__in=allowed_exams)
        return base_qs

class SubjectiveModelExamViewSet(viewsets.ReadOnlyModelViewSet):
    """
    [LEGACY - DEPRECATED]
    This ViewSet is deprecated in favor of the new Examination architecture.
    """
    from .models import Examination
    from .serializers import SubjectiveModelExamSerializer
    serializer_class = SubjectiveModelExamSerializer

    def get_queryset(self):
        user = self.request.user
        base_qs = self.Examination.objects.filter(status='published', exam_type='subjective')
        if not user or not user.is_authenticated:
            return base_qs.none()
        from courses.access import get_authorized_examination_filter
        q_filter = get_authorized_examination_filter(user)
        if q_filter is None:
            return base_qs.none()
        return base_qs.filter(q_filter).distinct()

class SubjectiveQuestionViewSet(viewsets.ReadOnlyModelViewSet):
    from .models import Question
    from .serializers import SubjectiveQuestionSerializer
    serializer_class = SubjectiveQuestionSerializer

    def get_queryset(self):
        # Security: only approved questions are student-facing
        qs = self.Question.objects.filter(status='approved', question_type__in=self.Question.SUBJECTIVE_TYPES)
        topic_id = self.request.query_params.get('topic')
        if topic_id:
            qs = qs.filter(topic_id=topic_id)
        return qs

class SubjectiveAttemptViewSet(viewsets.ModelViewSet):
    from .models import SubjectiveAttempt
    from .serializers import SubjectiveAttemptSerializer
    serializer_class = SubjectiveAttemptSerializer

    def get_queryset(self):
        return self.SubjectiveAttempt.objects.filter(student=self.request.user)

    def create(self, request, *args, **kwargs):
        from .models import SubjectivePracticeSet, SubjectiveModelExam, SubjectiveAnswer, Question, SubjectiveAttempt
        from django.utils import timezone
        from courses.access import authorized_exam_ids

        mode = request.data.get('mode', 'practice')
        practice_set_id = request.data.get('practice_set_id')
        model_exam_id = request.data.get('model_exam_id')
        question_ids = request.data.get('question_ids', [])  # For topic practice

        if mode == 'practice' and practice_set_id:
            try:
                ps = SubjectivePracticeSet.objects.get(id=practice_set_id, status='published')
            except SubjectivePracticeSet.DoesNotExist:
                return Response({'detail': 'Practice set not found.'}, status=404)

            allowed_exams = authorized_exam_ids(request.user)
            if allowed_exams is not None and ps.exam_id not in allowed_exams:
                return Response({'detail': 'You are not enrolled in the course for this practice set.'}, status=403)

            # Resume existing in-progress attempt
            existing = SubjectiveAttempt.objects.filter(
                student=request.user, practice_set=ps, status='in-progress'
            ).first()
            if existing:
                return Response(self.get_serializer(existing).data)

            attempt = SubjectiveAttempt.objects.create(
                student=request.user, practice_set=ps, mode='practice'
            )
            # Only approved questions ever reach a student attempt.
            for q in ps.questions.filter(status='approved'):
                SubjectiveAnswer.objects.create(attempt=attempt, question=q)

        elif mode == 'model_exam' and model_exam_id:
            try:
                me = SubjectiveModelExam.objects.get(id=model_exam_id, status='published')
            except SubjectiveModelExam.DoesNotExist:
                return Response({'detail': 'Model exam not found.'}, status=404)

            allowed_exams = authorized_exam_ids(request.user)
            if allowed_exams is not None and me.exam_id not in allowed_exams:
                return Response({'detail': 'You are not enrolled in the course for this model exam.'}, status=403)

            existing = SubjectiveAttempt.objects.filter(
                student=request.user, model_exam=me, status='in-progress'
            ).first()
            if existing:
                # Check timer
                elapsed = (timezone.now() - existing.started_at).total_seconds()
                if elapsed > me.duration_minutes * 60:
                    existing.status = 'submitted'
                    existing.submitted_at = timezone.now()
                    existing.save()
                    for ans in existing.answers.filter(status='draft'):
                        ans.status = 'submitted'
                        ans.submitted_at = timezone.now()
                        ans.save()
                    return Response(self.get_serializer(existing).data)
                return Response(self.get_serializer(existing).data)

            attempt = SubjectiveAttempt.objects.create(
                student=request.user, model_exam=me, mode='model_exam'
            )
            for q in me.questions.filter(status='approved'):
                SubjectiveAnswer.objects.create(attempt=attempt, question=q)

        elif mode == 'topic' and question_ids:
            attempt = SubjectiveAttempt.objects.create(
                student=request.user, mode='topic'
            )
            for qid in question_ids:
                try:
                    q = Question.objects.get(id=qid, status='approved', question_type__in=Question.SUBJECTIVE_TYPES)
                    SubjectiveAnswer.objects.create(attempt=attempt, question=q)
                except Question.DoesNotExist:
                    pass
        else:
            return Response({'detail': 'Invalid attempt configuration.'}, status=400)

        return Response(self.get_serializer(attempt).data, status=201)

    @action(detail=True, methods=['post'])
    def save_draft(self, request, pk=None):
        from .models import SubjectiveAnswer
        attempt = self.get_object()
        if attempt.status == 'submitted':
            return Response({'detail': 'Attempt already submitted.'}, status=400)

        # Check model exam timer
        if attempt.model_exam:
            from django.utils import timezone
            elapsed = (timezone.now() - attempt.started_at).total_seconds()
            if elapsed > attempt.model_exam.duration_minutes * 60:
                return Response({'detail': 'Time expired.'}, status=403)

        question_id = request.data.get('question_id')
        answer_text = request.data.get('answer_text', '')
        word_count = len(answer_text.split()) if answer_text else 0

        try:
            ans = SubjectiveAnswer.objects.get(attempt=attempt, question_id=question_id)
            # A debounced autosave can land right after the student pressed
            # Submit. It must never pull a submitted (or already evaluated)
            # answer back to 'draft' - that would drop it from the
            # evaluation queue, which lists status='submitted'.
            if ans.status in ('submitted', 'evaluated'):
                return Response({'detail': 'Answer already submitted.'}, status=400)
            ans.answer_text = answer_text
            ans.word_count = word_count
            ans.status = 'draft'
            ans.save()
            return Response({'status': 'saved', 'word_count': word_count, 'last_saved_at': ans.last_saved_at})
        except SubjectiveAnswer.DoesNotExist:
            return Response({'detail': 'Question not in this attempt.'}, status=404)

    @action(detail=True, methods=['post'])
    def submit_answer(self, request, pk=None):
        from .models import SubjectiveAnswer
        from django.utils import timezone

        attempt = self.get_object()
        if attempt.status == 'submitted':
            return Response({'detail': 'Attempt already submitted.'}, status=400)

        question_id = request.data.get('question_id')
        answer_text = request.data.get('answer_text', '')

        try:
            ans = SubjectiveAnswer.objects.get(attempt=attempt, question_id=question_id)
            ans.answer_text = answer_text
            ans.word_count = len(answer_text.split()) if answer_text else 0
            ans.status = 'submitted'
            ans.submitted_at = timezone.now()
            ans.save()

            # Topic practice submits one answer at a time and never calls
            # submit(). Once nothing is left in draft the attempt is complete:
            # finalise it so the student's history shows the submission and
            # its evaluation instead of a perpetual "Continue Draft", and
            # admins are told there is something to evaluate.
            if attempt.mode == 'topic' and not attempt.answers.filter(status='draft').exists():
                attempt.status = 'submitted'
                attempt.submitted_at = timezone.now()
                attempt.save()
                from core.notification_service import NotificationService
                NotificationService.notify_admins(
                    notif_type='evaluation',
                    title='New Submission Awaiting Evaluation',
                    message=f"{attempt.student.get_full_name() or attempt.student.username} submitted a topic practice answer that needs evaluation.",
                    action_url='/admin-dashboard/evaluations',
                )
            return Response({'status': 'submitted'})
        except SubjectiveAnswer.DoesNotExist:
            return Response({'detail': 'Question not in this attempt.'}, status=404)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        from django.utils import timezone
        attempt = self.get_object()
        if attempt.status == 'submitted':
            return Response(self.get_serializer(attempt).data)

        attempt.status = 'submitted'
        attempt.submitted_at = timezone.now()
        attempt.save()

        # Mark all draft answers as submitted
        for ans in attempt.answers.filter(status='draft'):
            ans.status = 'submitted'
            ans.submitted_at = timezone.now()
            ans.save()

        submitted_count = attempt.answers.filter(status='submitted').count()
        if submitted_count:
            label = attempt.model_exam.title if attempt.model_exam else (
                attempt.practice_set.title if attempt.practice_set else 'a practice set'
            )
            from core.notification_service import NotificationService
            NotificationService.notify_admins(
                notif_type='evaluation',
                title='New Submission Awaiting Evaluation',
                message=f"{attempt.student.get_full_name() or attempt.student.username} submitted '{label}' — {submitted_count} answer(s) need evaluation.",
                action_url='/admin-dashboard/evaluations',
            )

        return Response(self.get_serializer(attempt).data)


class TeacherEvaluationViewSet(viewsets.ViewSet):
    """Teacher/Admin evaluation endpoints"""
    permission_classes = [IsAuthenticated]

    def _scoped_answers(self, user):
        """Admins/super-admins see every submission (platform-wide oversight,
        consistent with AdminQuestionReviewViewSet etc). A teacher only sees
        answers from students enrolled in one of their own assigned courses -
        same TeacherCourseAssignment -> Enrollment scoping already used by
        TeacherStudentViewSet, so a teacher can't view/grade another
        teacher's students by guessing an answer id."""
        from .models import SubjectiveAnswer
        qs = SubjectiveAnswer.objects.all()
        if user.role == 'teacher':
            from courses.models import Enrollment, TeacherCourseAssignment
            assigned_courses = TeacherCourseAssignment.objects.filter(teacher=user).values_list('course_id', flat=True)
            student_ids = Enrollment.objects.filter(course_id__in=assigned_courses, status='active').values_list('student_id', flat=True)
            qs = qs.filter(attempt__student_id__in=student_ids)
        return qs

    def list(self, request):
        """List all submitted answers pending evaluation"""
        from .serializers import SubjectiveAnswerListSerializer

        user = request.user
        if user.role not in ('teacher', 'admin', 'super-admin'):
            return Response({'detail': 'Permission denied.'}, status=403)

        status_filter = request.query_params.get('status', 'submitted')
        qs = self._scoped_answers(user).filter(status=status_filter).select_related(
            'attempt__student', 'question__topic'
        ).order_by('-submitted_at')

        serializer = SubjectiveAnswerListSerializer(qs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """Get a single answer with full detail for evaluation"""
        from .models import SubjectiveAnswer
        from .serializers import SubjectiveAnswerSerializer

        user = request.user
        if user.role not in ('teacher', 'admin', 'super-admin'):
            return Response({'detail': 'Permission denied.'}, status=403)

        try:
            answer = self._scoped_answers(user).select_related(
                'attempt__student', 'question__topic'
            ).get(id=pk)
            serializer = SubjectiveAnswerSerializer(answer)
            return Response(serializer.data)
        except SubjectiveAnswer.DoesNotExist:
            return Response({'detail': 'Answer not found.'}, status=404)

    @action(detail=True, methods=['post'])
    def evaluate(self, request, pk=None):
        """Submit evaluation for a specific answer"""
        from .models import SubjectiveAnswer, Evaluation

        user = request.user
        if user.role not in ('teacher', 'admin', 'super-admin'):
            return Response({'detail': 'Permission denied.'}, status=403)

        try:
            answer = self._scoped_answers(user).get(id=pk)
        except SubjectiveAnswer.DoesNotExist:
            return Response({'detail': 'Answer not found.'}, status=404)

        marks = float(request.data.get('marks_obtained', 0))
        feedback = request.data.get('feedback', '')

        if marks > answer.question.marks:
            return Response({'detail': f'Marks cannot exceed {answer.question.marks}.'}, status=400)

        evaluation, created = Evaluation.objects.update_or_create(
            answer=answer,
            defaults={
                'evaluator': user,
                'marks_obtained': marks,
                'feedback': feedback,
            }
        )

        answer.status = 'evaluated'
        answer.save()

        from core.notification_service import NotificationService
        NotificationService.notify_subjective_evaluated(evaluation)

        from .serializers import EvaluationSerializer
        return Response(EvaluationSerializer(evaluation).data)

    @action(detail=True, methods=['post'])
    def annotate(self, request, pk=None):
        """Add annotation to an evaluation"""
        from .models import SubjectiveAnswer, Evaluation, Annotation

        user = request.user
        if user.role not in ('teacher', 'admin', 'super-admin'):
            return Response({'detail': 'Permission denied.'}, status=403)

        try:
            answer = self._scoped_answers(user).get(id=pk)
            evaluation = answer.evaluation
        except (SubjectiveAnswer.DoesNotExist, Evaluation.DoesNotExist):
            return Response({'detail': 'Answer or evaluation not found.'}, status=404)

        annotation = Annotation.objects.create(
            evaluation=evaluation,
            selected_text=request.data.get('selected_text', ''),
            comment=request.data.get('comment', ''),
            start_offset=int(request.data.get('start_offset', 0)),
            end_offset=int(request.data.get('end_offset', 0)),
            created_by=user,
        )

        from .serializers import AnnotationSerializer
        return Response(AnnotationSerializer(annotation).data, status=201)

    @action(detail=True, methods=['post'])
    def video_feedback(self, request, pk=None):
        """Add YouTube video feedback URL"""
        from .models import SubjectiveAnswer, Evaluation, VideoFeedback
        import re

        user = request.user
        if user.role not in ('teacher', 'admin', 'super-admin'):
            return Response({'detail': 'Permission denied.'}, status=403)

        try:
            answer = self._scoped_answers(user).get(id=pk)
            evaluation = answer.evaluation
        except (SubjectiveAnswer.DoesNotExist, Evaluation.DoesNotExist):
            return Response({'detail': 'Answer or evaluation not found.'}, status=404)

        youtube_url = request.data.get('youtube_url', '')
        # Validate YouTube URL
        pattern = r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})'
        if not re.search(pattern, youtube_url):
            return Response({'detail': 'Invalid YouTube URL.'}, status=400)

        vf, _ = VideoFeedback.objects.update_or_create(
            evaluation=evaluation,
            defaults={'youtube_url': youtube_url}
        )

        from .serializers import VideoFeedbackSerializer
        return Response(VideoFeedbackSerializer(vf).data)

from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from administration.permissions import IsTeacher, IsEvaluatorUser

class TeacherQuestionViewSet(viewsets.ModelViewSet):
    # get_queryset already restricted list/retrieve/update/destroy to teachers
    # (returning an empty queryset otherwise), but `create` bypasses
    # get_queryset entirely — without this, any authenticated non-teacher
    # could POST a question straight into the review queue.
    permission_classes = [IsAuthenticated, IsTeacher]
    serializer_class = QuestionFullSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['subject', 'chapter', 'topic', 'difficulty', 'question_type', 'status']
    search_fields = ['text']

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or user.role != 'teacher':
            return Question.objects.none()

        # Questions created by this teacher
        authored = Question.objects.filter(created_by=user).exclude(status='archived')
        
        # Questions assigned to the teacher's courses
        from courses.models import Course
        assigned_courses = Course.objects.filter(
            teachers__teacher=user,
        )
        assigned_exam_ids = assigned_courses.values_list('exam_id', flat=True)
        
        assigned_questions = Question.objects.filter(
            topic__chapter__subject__paper__exam_id__in=assigned_exam_ids
        ).exclude(status='archived')

        return (authored | assigned_questions).distinct().select_related('topic', 'topic__chapter', 'topic__chapter__subject', 'topic__chapter__subject__paper__exam')
        
    def perform_create(self, serializer):
        # Duplicate detection: check for exact normalized text match
        question_text = serializer.validated_data.get('text', '').strip().lower()
        force_create = self.request.data.get('force_create', False)
        if not force_create and question_text:
            import unicodedata
            normalized = unicodedata.normalize('NFKC', question_text)
            existing = Question.objects.filter(text__iexact=normalized).exclude(
                status='archived'
            ).first()
            if existing:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({
                    'duplicate': True,
                    'existing_id': existing.question_id,
                    'detail': (
                        f'A similar question already exists in the Master Question Bank '
                        f'({existing.question_id}, status: {existing.status}). '
                        f'Pass force_create=true to create anyway.'
                    ),
                })
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        question = self.get_object()
        if question.created_by != self.request.user:
            raise PermissionDenied("You can only edit questions you have created.")
        if question.status not in ['draft', 'changes_requested']:
            raise PermissionDenied("You can only edit questions in Draft or Changes Requested status.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.created_by != self.request.user:
            raise PermissionDenied("You can only archive questions you have created.")
        if instance.status not in ['draft', 'changes_requested', 'rejected']:
            raise PermissionDenied("You cannot archive a question that is pending review or approved.")
        instance.status = 'archived'
        instance.save()

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        question = self.get_object()
        if question.created_by != request.user:
            raise PermissionDenied("Not authorized.")
        if question.status not in ['draft', 'changes_requested']:
            return Response({"detail": "Only drafts can be submitted."}, status=400)
        
        from django.utils import timezone
        question.status = 'pending_review'
        question.submitted_at = timezone.now()
        question.save()

        from core.notification_service import NotificationService
        NotificationService.notify_admins(
            notif_type='question_review',
            title='Question Submitted for Review',
            message=f"{request.user.get_full_name() or request.user.username} submitted a question for review: '{question.text[:80]}'.",
            action_url='/admin-dashboard/academic/questions',
        )

        return Response({"detail": "Question submitted for review successfully."})

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        # We expect JSON payload parsed from CSV in the frontend
        # For a robust implementation, validate structure and create questions.
        questions_data = request.data.get('questions', [])
        if not questions_data:
            return Response({"detail": "No questions provided."}, status=400)
            
        created_count = 0
        from django.db import transaction
        
        try:
            with transaction.atomic():
                for q_data in questions_data:
                    q = Question.objects.create(
                        created_by=request.user,
                        text=q_data.get('text', ''),
                        question_type=q_data.get('question_type', 'mcq'),
                        topic_id=q_data.get('topic_id'),
                        difficulty=q_data.get('difficulty', 'medium'),
                        marks=float(q_data.get('marks', 1.0)),
                        negative_marks=float(q_data.get('negative_marks', 0.0)),
                        expected_time_minutes=int(q_data.get('expected_time_minutes', 1)),
                        explanation=q_data.get('explanation', ''),
                        status='draft',
                        
                        option_a=q_data.get('option_a', ''),
                        option_b=q_data.get('option_b', ''),
                        option_c=q_data.get('option_c', ''),
                        option_d=q_data.get('option_d', ''),
                        correct_option=q_data.get('correct_option', ''),
                        model_answer=q_data.get('model_answer', ''),
                    )
                    created_count += 1
            return Response({"detail": f"Successfully imported {created_count} questions as drafts."})
        except Exception as e:
            return Response({"detail": f"Import failed: {str(e)}"}, status=400)

class AdminQuestionReviewViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = QuestionFullSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['topic', 'difficulty', 'question_type', 'status', 'created_by']
    search_fields = ['text']
    
    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or user.role not in ('admin', 'super-admin'):
            return Question.objects.none()

        # Admin can see all questions that have been submitted at some point, or all questions
        # Prioritize pending review
        return Question.objects.exclude(status='draft').exclude(status='archived')

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        question = self.get_object()
        if question.created_by == request.user:
            return Response({"detail": "You cannot approve your own question."}, status=403)
        from django.utils import timezone
        question.status = 'approved'
        question.reviewed_by = request.user
        question.reviewed_at = timezone.now()
        question.reviewer_comment = request.data.get('reviewer_comment', '')
        question.save()

        if question.created_by:
            from core.notification_service import NotificationService
            NotificationService.notify_question_review(
                teacher=question.created_by,
                question_title=question.text[:80],
                status='approved',
                action_url='/teacher/questions',
            )

        return Response({"detail": "Question approved."})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        question = self.get_object()
        reason = (
            request.data.get('reviewer_comment')
            or request.data.get('feedback')
            or request.data.get('reason')
            or request.data.get('note')
        )
        if not reason:
            return Response({"detail": "Rejection reason is required."}, status=400)
            
        from django.utils import timezone
        question.status = 'rejected'
        question.reviewed_by = request.user
        question.reviewed_at = timezone.now()
        question.reviewer_comment = reason
        question.save()

        if question.created_by:
            from core.notification_service import NotificationService
            NotificationService.notify_question_review(
                teacher=question.created_by,
                question_title=question.text[:80],
                status='rejected',
                feedback=reason,
                action_url='/teacher/questions',
            )

        return Response({"detail": "Question rejected."})

    @action(detail=True, methods=['post'], url_path='request-changes')
    def request_changes(self, request, pk=None):
        question = self.get_object()
        feedback = (
            request.data.get('reviewer_comment')
            or request.data.get('feedback')
            or request.data.get('reason')
            or request.data.get('note')
        )
        if not feedback:
            return Response({"detail": "Feedback is required to request changes."}, status=400)
            
        from django.utils import timezone
        question.status = 'changes_requested'
        question.reviewed_by = request.user
        question.reviewed_at = timezone.now()
        question.reviewer_comment = feedback
        question.save()

        if question.created_by:
            from core.notification_service import NotificationService
            NotificationService.notify_question_review(
                teacher=question.created_by,
                question_title=question.text[:80],
                status='changes_requested',
                feedback=feedback,
                action_url=f'/teacher/questions/{question.id}/edit',
            )

        return Response({"detail": "Changes requested."})

from .models import QuestionSet, QuestionSetQuestion
from .serializers import TeacherQuestionSetSerializer
from rest_framework.decorators import action

class TeacherQuestionSetViewSet(viewsets.ModelViewSet):
    # Same gap as TeacherQuestionViewSet: get_queryset scopes reads/writes to
    # teachers, but `create` isn't routed through get_queryset at all.
    permission_classes = [IsAuthenticated, IsTeacher]
    serializer_class = TeacherQuestionSetSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'set_type', 'exam', 'subject']
    search_fields = ['name', 'description']

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or user.role != 'teacher':
            return QuestionSet.objects.none()

        # Questions sets created by this teacher
        return QuestionSet.objects.filter(created_by=user).exclude(status='archived').order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        if self.get_object().created_by != self.request.user:
            raise PermissionDenied("You can only edit practice sets you have created.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.created_by != self.request.user:
            raise PermissionDenied("You can only archive practice sets you have created.")
        # Soft-delete by setting status to 'archived'
        instance.status = 'archived'
        instance.save()

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        original_set = self.get_object()
        if original_set.created_by != request.user:
             raise PermissionDenied("You can only duplicate practice sets you own.")

        # Duplicate the set
        new_set = QuestionSet.objects.get(pk=original_set.pk)
        new_set.pk = None
        new_set.name = f"{original_set.name} (Copy)"
        new_set.status = 'draft' # Always duplicate as draft
        new_set.created_by = request.user
        new_set.save()

        # Duplicate the linked questions
        for qsq in original_set.question_set_questions.all():
            QuestionSetQuestion.objects.create(
                question_set=new_set,
                question=qsq.question,
                order=qsq.order,
                marks=qsq.marks
            )

        serializer = self.get_serializer(new_set)
        return Response(serializer.data, status=201)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        instance = self.get_object()
        from django.utils import timezone
        
        if instance.question_set_questions.count() == 0:
            return Response({"detail": "Cannot submit an empty practice set."}, status=400)
            
        unapproved = instance.question_set_questions.exclude(question__status='approved').exists()
        if unapproved:
            return Response({"detail": "All questions must be approved before submitting the practice set."}, status=400)
            
        instance.status = 'pending_review'
        instance.submitted_at = timezone.now()
        instance.save()

        from core.notification_service import NotificationService
        NotificationService.notify_admins(
            notif_type='question_review',
            title='Question Set Submitted for Review',
            message=f"{request.user.get_full_name() or request.user.username} submitted question set '{instance.name}' for review.",
            action_url='/admin-dashboard/academic/question-sets',
        )

        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=['post'], url_path='generate-blueprint')
    def generate_blueprint(self, request, pk=None):
        """
        Generate questions for a Practice Set using the Master Question Bank.

        Accepts:
          - total_questions: int
          - difficulties: {"easy": int, "medium": int, "hard": int}  (optional)
          - topics: {"<topic_id>": int, ...}  (optional, takes priority)
          - subject_id, exam_id, question_type  (optional filters)
          - replace_existing: bool (default False)
        """
        instance = self.get_object()
        total_questions = int(request.data.get('total_questions', 0))
        difficulties = request.data.get('difficulties', {})
        topics = request.data.get('topics', {})
        subject_id = request.data.get('subject_id')
        exam_id = request.data.get('exam_id') or instance.exam_id
        question_type = request.data.get('question_type')
        replace_existing = request.data.get('replace_existing', False)

        # Exclude questions already in the set (unless replacing)
        exclude_ids = []
        if not replace_existing:
            exclude_ids = list(instance.question_set_questions.values_list('question_id', flat=True))
        else:
            # Clear existing
            instance.question_set_questions.all().delete()

        # Build selection parameters
        difficulty_distribution = {k: int(v) for k, v in difficulties.items() if int(v) > 0} if difficulties else None
        topic_distribution = {str(k): int(v) for k, v in topics.items() if int(v) > 0} if topics else None

        service = QuestionSelectionService()
        result = service.select(
            exam_id=exam_id,
            subject_id=subject_id,
            count=total_questions,
            difficulty_distribution=difficulty_distribution,
            topic_distribution=topic_distribution,
            question_type=question_type,
            exclude_ids=exclude_ids,
            randomize=True,
        )

        if len(result['questions']) == 0:
            return Response(
                {'detail': 'No approved questions found for the selected criteria.', 'warnings': result['warnings']},
                status=400
            )

        from django.db.models import Max
        current_max = instance.question_set_questions.aggregate(Max('order'))['order__max'] or 0
        for idx, q in enumerate(result['questions'], start=1):
            QuestionSetQuestion.objects.get_or_create(
                question_set=instance,
                question=q,
                defaults={'order': current_max + idx, 'marks': q.marks}
            )

        return Response({
            **self.get_serializer(instance).data,
            'generation_info': {
                'available': result['available'],
                'requested': result['requested'],
                'selected': result['selected'],
                'satisfied': result['satisfied'],
                'warnings': result['warnings'],
            }
        })

    @action(detail=True, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request, pk=None):
        instance = self.get_object()
        rows = request.data
        if not isinstance(rows, list):
            return Response({"detail": "Expected a list of questions"}, status=400)
            
        from .models import Question
        from .serializers import QuestionFullSerializer
        from django.db.models import Max
        
        results = {"added_existing": 0, "created_drafts": 0, "errors": []}
        current_max = instance.question_set_questions.aggregate(Max('order'))['order__max'] or 0
        
        for idx, row in enumerate(rows):
            question_id = row.get('id') or row.get('question_id')
            if question_id:
                try:
                    q = Question.objects.get(id=question_id, status='approved')
                    QuestionSetQuestion.objects.get_or_create(
                        question_set=instance,
                        question=q,
                        defaults={'order': current_max + idx + 1, 'marks': q.marks}
                    )
                    results["added_existing"] += 1
                except Question.DoesNotExist:
                    results["errors"].append(f"Row {idx+1}: Approved Question {question_id} not found.")
            else:
                serializer = QuestionFullSerializer(data=row, context={'request': request})
                if serializer.is_valid():
                    q = serializer.save(created_by=request.user, status='draft')
                    QuestionSetQuestion.objects.create(
                        question_set=instance,
                        question=q,
                        order=current_max + idx + 1,
                        marks=q.marks
                    )
                    results["created_drafts"] += 1
                else:
                    results["errors"].append(f"Row {idx+1}: {serializer.errors}")
                    
        return Response(results)

class AdminPracticeSetReviewViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TeacherQuestionSetSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status']
    search_fields = ['name', 'description']
    
    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or user.role not in ('admin', 'super-admin'):
            return QuestionSet.objects.none()

        return QuestionSet.objects.filter(
            status__in=['pending_review', 'approved', 'changes_requested', 'rejected', 'published']
        ).order_by('-submitted_at')

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        instance = self.get_object()
        if instance.created_by == request.user:
            return Response({"detail": "You cannot approve your own practice set."}, status=403)
        from django.utils import timezone
        
        instance.status = 'approved'
        instance.reviewed_by = request.user
        instance.reviewed_at = timezone.now()
        instance.reviewer_comment = request.data.get('feedback', '')
        instance.save()
        return Response({"status": "approved"})

    @action(detail=True, methods=['post'], url_path='request-changes')
    def request_changes(self, request, pk=None):
        instance = self.get_object()
        feedback = request.data.get('feedback')
        if not feedback:
            return Response({"detail": "Feedback is required."}, status=400)
            
        from django.utils import timezone
        instance.status = 'changes_requested'
        instance.reviewed_by = request.user
        instance.reviewed_at = timezone.now()
        instance.reviewer_comment = feedback
        instance.save()
        return Response({"status": "changes_requested"})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        instance = self.get_object()
        feedback = request.data.get('feedback')
        if not feedback:
            return Response({"detail": "Feedback is required."}, status=400)
            
        from django.utils import timezone
        instance.status = 'rejected'
        instance.reviewed_by = request.user
        instance.reviewed_at = timezone.now()
        instance.reviewer_comment = feedback
        instance.save()
        return Response({"status": "rejected"})


class TeacherMockExamViewSet(viewsets.ModelViewSet):
    # get_queryset restricts reads/writes to teacher/admin/super-admin, but
    # `create` bypasses get_queryset entirely — mirror the same roles here.
    permission_classes = [IsAuthenticated, IsEvaluatorUser]

    def get_serializer_class(self):
        from .serializers import TeacherExaminationSerializer
        return TeacherExaminationSerializer
        
    def get_queryset(self):
        from .models import Examination
        user = self.request.user
        if user.role not in ('teacher', 'admin', 'super-admin'):
            return Examination.objects.none()
        return Examination.objects.filter(created_by=user).order_by('-created_at')
        
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def taxonomy(self, request):
        from .models import ExamCategory
        categories = ExamCategory.objects.prefetch_related(
            'exams__papers__subjects__chapters__topics'
        ).filter(is_active=True).order_by('order')
        
        data = []
        for cat in categories:
            cat_data = {
                'id': cat.id,
                'name': cat.name,
                'exams': []
            }
            for exam in cat.exams.filter(is_active=True):
                exam_data = {
                    'id': exam.id,
                    'name': exam.name,
                    'subjects': []
                }
                # Subjects are under Papers which are under Exams
                for paper in exam.papers.filter(is_active=True):
                    for sub in paper.subjects.filter(is_active=True):
                        sub_data = {
                            'id': sub.id,
                            'name': sub.name,
                            'chapters': []
                        }
                        for chap in sub.chapters.filter(is_active=True):
                            chap_data = {
                                'id': chap.id,
                                'name': chap.title,
                                'topics': [{'id': t.id, 'name': t.name} for t in chap.topics.filter(is_active=True)]
                            }
                            sub_data['chapters'].append(chap_data)
                        exam_data['subjects'].append(sub_data)
                cat_data['exams'].append(exam_data)
            data.append(cat_data)
            
        return Response(data)

    @action(detail=True, methods=['post'])
    def auto_generate(self, request, pk=None):
        """
        Auto-generate questions for a Mock Exam using the Master Question Bank.

        Accepts:
          config: {
            subject_id: int (optional)
            topic_id: int (optional)
            exam_id: int (optional, defaults to exam's linked exam)
            question_type: str (optional)
            counts: {"easy": int, "medium": int, "hard": int}
            replace_existing: bool (default False)
          }
        """
        mock_exam = self.get_object()
        if mock_exam.status in ['pending_review', 'approved', 'published']:
            return Response({'detail': 'Cannot modify questions for this exam.'}, status=400)

        config = request.data.get('config', {})
        subject_id = config.get('subject_id')
        topic_id = config.get('topic_id')
        exam_id = config.get('exam_id') or mock_exam.exam_id
        question_type = config.get('question_type')
        counts = config.get('counts', {})
        replace_existing = config.get('replace_existing', False)

        from .models import ExaminationQuestion
        from django.db.models import Max

        if replace_existing:
            mock_exam.examination_questions.all().delete()
            existing_ids = []
        else:
            existing_ids = list(mock_exam.examination_questions.values_list('question_id', flat=True))

        difficulty_distribution = {k: int(v) for k, v in counts.items() if int(v) > 0} if counts else None
        total_count = sum(difficulty_distribution.values()) if difficulty_distribution else 0

        if total_count == 0:
            return Response({'detail': 'No question counts specified in config.counts.'}, status=400)

        service = QuestionSelectionService()
        result = service.select(
            exam_id=exam_id,
            subject_id=subject_id,
            topic_id=topic_id,
            question_type=question_type,
            difficulty_distribution=difficulty_distribution,
            exclude_ids=existing_ids,
            randomize=True,
        )

        if not result['questions']:
            return Response(
                {'detail': 'No approved questions found for the selected criteria.', 'warnings': result['warnings']},
                status=400
            )

        current_max = ExaminationQuestion.objects.filter(examination=mock_exam).aggregate(Max('order'))['order__max'] or 0
        added = 0
        for q in result['questions']:
            current_max += 1
            ExaminationQuestion.objects.create(
                examination=mock_exam,
                question_id=q.id,
                order=current_max,
                marks=mock_exam.marks_per_question
            )
            added += 1

        # Update totals
        mock_exam.total_questions = mock_exam.examination_questions.count()
        mock_exam.total_marks = sum(eq.marks for eq in mock_exam.examination_questions.all())
        mock_exam.save()

        return Response({
            'status': f'{added} question(s) auto-generated.',
            'added': added,
            'generation_info': {
                'available': result['available'],
                'requested': result['requested'],
                'selected': result['selected'],
                'satisfied': result['satisfied'],
                'warnings': result['warnings'],
            }
        })

    @action(detail=True, methods=['post'])
    def submit_review(self, request, pk=None):
        from django.utils import timezone
        exam = self.get_object()
        
        if exam.status not in ['draft', 'changes_requested', 'rejected']:
            return Response({'detail': 'Only draft, changes_requested or rejected exams can be submitted.'}, status=400)
            
        if exam.questions.count() == 0:
            return Response({'detail': 'Cannot submit an exam with no questions.'}, status=400)
            
        exam.status = 'pending_review'
        exam.submitted_at = timezone.now()
        exam.save()

        from core.notification_service import NotificationService
        NotificationService.notify_admins(
            notif_type='question_review',
            title='Exam Submitted for Review',
            message=f"{request.user.get_full_name() or request.user.username} submitted exam '{exam.title}' for review.",
            action_url='/admin-dashboard/exams',
        )

        return Response(self.get_serializer(exam).data)

    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        # get_queryset already scopes this to the teacher's own exams, so
        # get_object() 404s a teacher trying another teacher's exam id -
        # same computation the admin exam analytics endpoint uses.
        from .analytics_utils import build_examination_analytics
        exam = self.get_object()
        return Response(build_examination_analytics(exam))

        return Response({'status': 'Exam submitted for review successfully.'})

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        exam = self.get_object()
        new_exam = exam
        new_exam.pk = None
        new_exam.title = f"{exam.title} (Copy)"
        new_exam.status = 'draft'
        new_exam.submitted_at = None
        new_exam.reviewed_at = None
        new_exam.reviewer_comment = None
        new_exam.reviewed_by = None
        new_exam.save()
        
        # Clone questions
        from .models import ExaminationQuestion
        questions = ExaminationQuestion.objects.filter(examination_id=pk)
        for eq in questions:
            eq.pk = None
            eq.examination = new_exam
            eq.save()
            
        return Response(self.get_serializer(new_exam).data)

    @action(detail=True, methods=['post'], url_path='questions')
    def add_questions(self, request, pk=None):
        exam = self.get_object()
        if exam.status in ['pending_review', 'approved', 'published']:
            return Response({'detail': 'Cannot modify questions for this exam.'}, status=400)
            
        question_ids = request.data.get('question_ids', [])
        marks = request.data.get('marks', exam.marks_per_question)
        
        from .models import Question, ExaminationQuestion
        from django.db.models import Max
        
        current_max = ExaminationQuestion.objects.filter(examination=exam).aggregate(Max('order'))['order__max'] or 0
        added = 0
        
        for qid in question_ids:
            try:
                question = Question.objects.get(id=qid)
                if not ExaminationQuestion.objects.filter(examination=exam, question=question).exists():
                    current_max += 1
                    ExaminationQuestion.objects.create(
                        examination=exam,
                        question=question,
                        order=current_max,
                        marks=marks
                    )
                    added += 1
            except Question.DoesNotExist:
                continue
                
        # Update total questions and marks
        exam.total_questions = exam.examination_questions.count()
        exam.total_marks = sum(q.marks for q in exam.examination_questions.all())
        exam.save()
                
        return Response({'status': f'{added} questions added.'})

    @action(detail=True, methods=['delete'], url_path='questions/(?P<question_id>[^/.]+)')
    def remove_question(self, request, pk=None, question_id=None):
        exam = self.get_object()
        if exam.status in ['pending_review', 'approved', 'published']:
            return Response({'detail': 'Cannot modify questions for this exam.'}, status=400)
            
        from .models import ExaminationQuestion
        try:
            eq = ExaminationQuestion.objects.get(examination=exam, question_id=question_id)
            eq.delete()
            
            # Reorder remaining
            for idx, item in enumerate(exam.examination_questions.order_by('order'), 1):
                item.order = idx
                item.save()
                
            exam.total_questions = exam.examination_questions.count()
            exam.total_marks = sum(q.marks for q in exam.examination_questions.all())
            exam.save()
            return Response({'status': 'Question removed.'})
        except ExaminationQuestion.DoesNotExist:
            return Response({'detail': 'Question not found in this exam.'}, status=404)

    @action(detail=True, methods=['post'], url_path='questions/reorder')
    def reorder_questions(self, request, pk=None):
        exam = self.get_object()
        if exam.status in ['pending_review', 'approved', 'published']:
            return Response({'detail': 'Cannot modify questions for this exam.'}, status=400)
            
        order_data = request.data.get('order_data', []) # [{'question_id': 1, 'order': 1}]
        from .models import ExaminationQuestion
        for item in order_data:
            try:
                eq = ExaminationQuestion.objects.get(examination=exam, question_id=item['question_id'])
                eq.order = item['order']
                eq.save()
            except ExaminationQuestion.DoesNotExist:
                pass
        return Response({'status': 'Questions reordered.'})


class AdminExaminationReviewViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        from .serializers import AdminExaminationReviewSerializer
        return AdminExaminationReviewSerializer
        
    def get_queryset(self):
        from .models import Examination
        user = self.request.user
        if user.role not in ('admin', 'super-admin'):
            return Examination.objects.none()
        return Examination.objects.exclude(status='draft').order_by('-submitted_at', '-created_at')

    @action(detail=True, methods=['post'])
    def moderate(self, request, pk=None):
        from django.utils import timezone
        exam = self.get_object()
        
        action = request.data.get('action') # approve, request_changes, reject
        comment = request.data.get('comment', '')
        
        if action == 'approve':
            exam.status = 'published'
        elif action == 'request_changes':
            exam.status = 'changes_requested'
        elif action == 'reject':
            exam.status = 'rejected'
        else:
            return Response({'detail': 'Invalid action'}, status=400)

        exam.reviewer_comment = comment
        exam.reviewed_by = request.user
        exam.reviewed_at = timezone.now()
        exam.save()

        if action == 'approve':
            from core.notification_service import NotificationService
            NotificationService.notify_students_exam_update(exam, 'published')

        return Response({'status': f'Exam marked as {exam.status}'})


# ============================================================
# QUESTION AVAILABILITY ENDPOINT
# ============================================================

class QuestionAvailabilityView(APIView):
    """
    GET /api/questions/availability/

    Returns the count of approved questions matching the given criteria.
    Used by teachers/admins before generating a practice set or mock exam
    so they know whether the question pool is large enough.

    Query params (all optional):
      exam, paper, subject, chapter, topic, question_type, tags, count
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = request.query_params

        def _int(key):
            val = params.get(key)
            try:
                return int(val) if val else None
            except (ValueError, TypeError):
                return None

        exam_id = _int('exam')
        paper_id = _int('paper')
        subject_id = _int('subject')
        chapter_id = _int('chapter')
        topic_id = _int('topic')
        question_type = params.get('question_type')
        tags = params.get('tags')
        requested = _int('count') or 0

        service = QuestionSelectionService()
        availability = service.check_availability(
            exam_id=exam_id,
            paper_id=paper_id,
            subject_id=subject_id,
            chapter_id=chapter_id,
            topic_id=topic_id,
            question_type=question_type,
            tags=tags,
        )

        total = availability['total']
        sufficient = (total >= requested) if requested else None

        warning = None
        if requested and not sufficient:
            warning = (
                f'Only {total} approved question(s) available for the selected criteria, '
                f'but {requested} were requested.'
            )

        return Response({
            'available': total,
            'requested': requested,
            'sufficient': sufficient,
            'by_difficulty': availability['by_difficulty'],
            'warning': warning,
        })
