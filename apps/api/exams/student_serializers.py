from django.utils import timezone
from rest_framework import serializers

from .models import (
    Examination, ExaminationAttempt, ExaminationRequest, StudentAnswer, Question,
    SubjectiveSubmission, SubjectiveSubmissionPage, SubjectiveQuestionScore,
)
from .attempt_timing import (
    attempt_expires_at,
    attempt_remaining_seconds,
    attempt_is_expired,
    is_subjective_exam,
    subjective_exam_expires_at,
    subjective_exam_remaining_seconds,
    subjective_upload_expires_at,
    subjective_upload_remaining_seconds,
    subjective_upload_is_expired,
    is_subjective_upload_open,
)


class ExaminationRequestSerializer(serializers.ModelSerializer):
    examination_title = serializers.SerializerMethodField()
    examination_status = serializers.CharField(source='examination.status', read_only=True, allow_null=True)
    requested_exam_name = serializers.CharField(source='academic_exam.name', read_only=True, allow_null=True)
    requested_course_title = serializers.CharField(source='course.title', read_only=True, allow_null=True)
    requested_subject_name = serializers.CharField(source='subject.name', read_only=True, allow_null=True)
    requested_topic_name = serializers.CharField(source='topic.name', read_only=True, allow_null=True)
    student_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ExaminationRequest
        fields = [
            'id', 'request_type', 'student', 'student_name', 'examination', 'examination_title', 'examination_status',
            'academic_exam', 'requested_exam_name', 'course', 'requested_course_title',
            'subject', 'requested_subject_name', 'topic', 'requested_topic_name',
            'status', 'rejection_reason', 'reviewed_by', 'reviewed_by_name',
            'reviewed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_student_name(self, obj):
        return obj.student.get_full_name() or obj.student.username

    def get_examination_title(self, obj):
        if obj.examination_id:
            return obj.examination.title
        if obj.academic_exam_id:
            return f'{obj.academic_exam.name} Subjective Live Exam'
        return 'Examination request'

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by_id:
            return None
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.username

class StudentExaminationSerializer(serializers.ModelSerializer):
    course_id = serializers.IntegerField(source='course.id', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    exam_name = serializers.CharField(source='exam.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    topic_id = serializers.IntegerField(source='topic.id', read_only=True, allow_null=True)
    topic_name = serializers.CharField(source='topic.name', read_only=True, allow_null=True)
    has_attempted = serializers.SerializerMethodField()
    attempts_used = serializers.SerializerMethodField()
    attempts_remaining = serializers.SerializerMethodField()
    active_attempt_id = serializers.SerializerMethodField()
    can_start = serializers.SerializerMethodField()
    start_blocked_reason = serializers.SerializerMethodField()
    has_question_paper = serializers.SerializerMethodField()
    latest_attempt_id = serializers.SerializerMethodField()
    latest_attempt_status = serializers.SerializerMethodField()
    is_result_published = serializers.SerializerMethodField()
    requires_admin_request = serializers.SerializerMethodField()

    # The raw admin-set category, plus effective_category which auto-promotes
    # a Live Exam into the Model Exams listing 48h after its scheduled start
    # — the student list groups by effective_category, not the raw value.
    effective_category = serializers.CharField(read_only=True)

    class Meta:
        model = Examination
        fields = [
            'id', 'title', 'description', 'exam_type', 'objective_category',
            'effective_category', 'category_name', 'course_id', 'course_title',
            'exam_name', 'subject_name', 'topic_id', 'topic_name', 'instructions', 'thumbnail',
            'total_questions', 'time_limit', 'total_marks',
            'passing_marks', 'marks_per_question', 'negative_marking',
            'negative_marking_value', 'max_attempts', 'allow_resume',
            'auto_submit', 'start_time', 'end_time', 'status',
            'has_attempted', 'attempts_used', 'attempts_remaining',
            'active_attempt_id', 'latest_attempt_id', 'latest_attempt_status',
            'is_result_published', 'requires_admin_request',
            'can_start', 'start_blocked_reason',
            'has_question_paper', 'question_paper_page_count',
            'upload_deadline_minutes', 'answer_upload_enabled',
            'allowed_file_types', 'max_upload_size_mb', 'evaluation_type',
        ]

    def get_has_question_paper(self, obj):
        return bool(obj.question_paper_pdf)

    # -- helpers -----------------------------------------------------------
    def _user(self):
        request = self.context.get('request')
        return getattr(request, 'user', None)

    def _attempts(self, obj):
        if hasattr(obj, 'student_attempts'):
            return obj.student_attempts
        user = self._user()
        if not user or not user.is_authenticated:
            return []
        return list(obj.attempts.filter(student=user))

    def _active_attempt(self, obj):
        attempts = self._attempts(obj)
        for att in attempts:
            if att.status in ('in-progress', 'upload_pending'):
                return att
        return None

    def _latest_attempt(self, obj):
        attempts = self._attempts(obj)
        return attempts[0] if attempts else None

    # -- fields ------------------------------------------------------------
    def get_has_attempted(self, obj):
        return len(self._attempts(obj)) > 0

    def get_attempts_used(self, obj):
        return len(self._attempts(obj))

    def get_attempts_remaining(self, obj):
        if obj.max_attempts and obj.max_attempts > 0:
            return max(0, obj.max_attempts - self.get_attempts_used(obj))
        return None  # unlimited

    def get_active_attempt_id(self, obj):
        active = self._active_attempt(obj)
        return active.id if active else None

    def get_latest_attempt_id(self, obj):
        latest = self._latest_attempt(obj)
        return latest.id if latest else None

    def get_latest_attempt_status(self, obj):
        latest = self._latest_attempt(obj)
        return latest.status if latest else None

    def get_is_result_published(self, obj):
        latest = self._latest_attempt(obj)
        if not latest:
            return False
        if obj.exam_type == 'subjective':
            sub = getattr(latest, 'subjective_submission', None)
            return bool(sub and sub.is_published)
        return latest.status == 'evaluated' or (latest.status == 'submitted' and obj.result_visibility == 'immediate')

    def get_requires_admin_request(self, obj):
        return bool(
            obj.course_id is not None
            and (
                obj.objective_category in ('past_year', 'model', 'topicwise')
                or (obj.exam_type == 'subject' and obj.topic_id is not None)
            )
        )

    def get_can_start(self, obj):
        return self.get_start_blocked_reason(obj) is None

    def get_start_blocked_reason(self, obj):
        user = self._user()
        if not user or not user.is_authenticated:
            return 'Sign in to take this exam.'
        if obj.status not in ('published', 'live'):
            return 'This exam is not currently active.'

        now = timezone.now()
        if obj.start_time and now < obj.start_time:
            return 'This exam has not opened yet.'
        if obj.end_time and now > obj.end_time:
            return 'This exam window has closed.'

        # Subjective exam must have a valid question paper attached
        if obj.exam_type == 'subjective' and not obj.question_paper_pdf:
            return 'Subjective question paper is not available yet.'

        # A resumable attempt always wins over the attempt cap.
        if self._active_attempt(obj):
            return None

        # Check request requirement if applicable
        if self.get_requires_admin_request(obj):
            req = ExaminationRequest.objects.filter(
                student=user, examination=obj
            ).order_by('-created_at').first()
            if not req:
                return 'Admin approval is required before starting this examination.'
            if req.status == 'pending':
                return 'Waiting for Admin approval.'
            if req.status == 'rejected':
                return f'Request Rejected: {req.rejection_reason}' if req.rejection_reason else 'Request Rejected by Admin.'

        remaining = self.get_attempts_remaining(obj)
        if remaining is not None and remaining <= 0:
            return 'You have used all of your attempts for this exam.'
        return None

class StudentSecureQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = [
            'id', 'text', 'question_type', 'difficulty',
            'option_a', 'option_b', 'option_c', 'option_d',
            'marks', 'negative_marks'
        ]

class StudentReviewQuestionSerializer(serializers.ModelSerializer):
    """
    Exposes full question details including correct option, explanation,
    and model answer for post-submission review when permitted.
    """
    class Meta:
        model = Question
        fields = [
            'id', 'text', 'question_type', 'difficulty',
            'option_a', 'option_b', 'option_c', 'option_d',
            'marks', 'negative_marks', 'correct_option',
            'explanation', 'model_answer'
        ]

class StudentAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentAnswer
        fields = ['id', 'question', 'selected_option', 'answer_text', 'is_correct', 'marks_awarded', 'evaluated_at']
        read_only_fields = ['is_correct', 'marks_awarded', 'evaluated_at']

class StudentAnswerReviewSerializer(serializers.ModelSerializer):
    """
    Serializes a student answer with associated question details and,
    if answer review is allowed for this attempt, the correct option,
    explanation, and model answer.
    """
    question_text = serializers.CharField(source='question.text', read_only=True)
    question_type = serializers.CharField(source='question.question_type', read_only=True)
    max_marks = serializers.FloatField(source='question.marks', read_only=True)
    option_a = serializers.CharField(source='question.option_a', read_only=True)
    option_b = serializers.CharField(source='question.option_b', read_only=True)
    option_c = serializers.CharField(source='question.option_c', read_only=True)
    option_d = serializers.CharField(source='question.option_d', read_only=True)
    correct_option = serializers.SerializerMethodField()
    explanation = serializers.SerializerMethodField()
    model_answer = serializers.SerializerMethodField()

    class Meta:
        model = StudentAnswer
        fields = [
            'id', 'question', 'selected_option', 'answer_text',
            'is_correct', 'marks_awarded', 'evaluated_at',
            'question_text', 'question_type', 'max_marks',
            'option_a', 'option_b', 'option_c', 'option_d',
            'correct_option', 'explanation', 'model_answer'
        ]
        read_only_fields = ['is_correct', 'marks_awarded', 'evaluated_at']

    def _review_allowed(self, obj):
        if 'can_review_answers' in self.context:
            return self.context['can_review_answers']
        attempt = getattr(obj, 'attempt', None)
        if not attempt or attempt.status == 'in-progress':
            return False
        exam = attempt.examination
        if exam.result_visibility == 'manual' and attempt.status != 'evaluated':
            return False
        if exam.result_visibility == 'after_end' and exam.end_time and timezone.now() < exam.end_time:
            return False
        if exam.exam_type in ('custom', 'practice') or exam.objective_category == 'custom':
            return True
        return bool(exam.show_correct_answers)

    def get_correct_option(self, obj):
        if not self._review_allowed(obj):
            return None
        return obj.question.correct_option

    def get_explanation(self, obj):
        if not self._review_allowed(obj):
            return None
        return obj.question.explanation or ""

    def get_model_answer(self, obj):
        if not self._review_allowed(obj):
            return None
        return obj.question.model_answer or ""

class AttemptTimingMixin(serializers.Serializer):
    """
    Server-authoritative timing for an ExaminationAttempt.

    The client never invents a deadline: it reads `expires_at` /
    `remaining_seconds` alongside `server_time` so it can correct for clock
    skew, and re-reads them after every refresh or tab reopen.
    For subjective exams, it provides two distinct server-authoritative countdowns:
    1. Exam Writing Timer (exam_expires_at, exam_remaining_seconds)
    2. Answer Upload Deadline (upload_expires_at, upload_remaining_seconds)
    """
    time_limit_minutes = serializers.IntegerField(
        source='examination.time_limit', read_only=True
    )
    auto_submit = serializers.BooleanField(
        source='examination.auto_submit', read_only=True
    )
    allow_resume = serializers.BooleanField(
        source='examination.allow_resume', read_only=True
    )
    server_time = serializers.SerializerMethodField()
    expires_at = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    # Subjective dual-timer fields
    is_subjective = serializers.SerializerMethodField()
    exam_expires_at = serializers.SerializerMethodField()
    exam_remaining_seconds = serializers.SerializerMethodField()
    is_exam_expired = serializers.SerializerMethodField()
    upload_expires_at = serializers.SerializerMethodField()
    upload_remaining_seconds = serializers.SerializerMethodField()
    is_upload_expired = serializers.SerializerMethodField()
    can_upload = serializers.SerializerMethodField()

    def get_server_time(self, obj):
        return timezone.now().isoformat()

    def get_expires_at(self, obj):
        expires = attempt_expires_at(obj)
        return expires.isoformat() if expires else None

    def get_remaining_seconds(self, obj):
        return attempt_remaining_seconds(obj)

    def get_is_expired(self, obj):
        return attempt_is_expired(obj)

    def get_is_active(self, obj):
        if is_subjective_exam(obj):
            return obj.status in ('in-progress', 'upload_pending') and not subjective_upload_is_expired(obj)
        return obj.status == 'in-progress' and not attempt_is_expired(obj)

    def get_is_subjective(self, obj):
        return is_subjective_exam(obj)

    def get_exam_expires_at(self, obj):
        if not is_subjective_exam(obj):
            return self.get_expires_at(obj)
        exp = subjective_exam_expires_at(obj)
        return exp.isoformat() if exp else None

    def get_exam_remaining_seconds(self, obj):
        if not is_subjective_exam(obj):
            return self.get_remaining_seconds(obj)
        return subjective_exam_remaining_seconds(obj)

    def get_is_exam_expired(self, obj):
        if not is_subjective_exam(obj):
            return self.get_is_expired(obj)
        rem = subjective_exam_remaining_seconds(obj)
        return rem is not None and rem <= 0

    def get_upload_expires_at(self, obj):
        if not is_subjective_exam(obj):
            return None
        exp = subjective_upload_expires_at(obj)
        return exp.isoformat() if exp else None

    def get_upload_remaining_seconds(self, obj):
        if not is_subjective_exam(obj):
            return None
        return subjective_upload_remaining_seconds(obj)

    def get_is_upload_expired(self, obj):
        if not is_subjective_exam(obj):
            return None
        return subjective_upload_is_expired(obj)

    def get_can_upload(self, obj):
        if not is_subjective_exam(obj):
            return False
        return is_subjective_upload_open(obj)


TIMING_FIELDS = [
    'time_limit_minutes', 'auto_submit', 'allow_resume',
    'server_time', 'expires_at', 'remaining_seconds',
    'is_expired', 'is_active',
    'is_subjective', 'exam_expires_at', 'exam_remaining_seconds',
    'is_exam_expired', 'upload_expires_at', 'upload_remaining_seconds',
    'is_upload_expired', 'can_upload',
]


class RankedAttemptMixin(serializers.Serializer):
    rank = serializers.SerializerMethodField()
    total_participants = serializers.SerializerMethodField()

    def get_rank(self, obj):
        if obj.percentage is None or obj.status not in ['submitted', 'evaluated']:
            return None
        
        # DenseRank logic: number of distinct higher percentages + 1
        # This matches exactly how the leaderboard ranks students.
        higher_scores_count = ExaminationAttempt.objects.filter(
            examination=obj.examination,
            status__in=['submitted', 'evaluated'],
            percentage__gt=obj.percentage
        ).values('percentage').distinct().count()
        return higher_scores_count + 1

    def get_total_participants(self, obj):
        return ExaminationAttempt.objects.filter(
            examination=obj.examination,
            status__in=['submitted', 'evaluated']
        ).values('student').distinct().count()

class StudentExaminationAttemptSerializer(AttemptTimingMixin, serializers.ModelSerializer):
    examination_title = serializers.CharField(source='examination.title', read_only=True)
    answers = StudentAnswerSerializer(many=True, read_only=True)
    subjective_submission = serializers.SerializerMethodField()

    class Meta:
        model = ExaminationAttempt
        fields = [
            'id', 'examination', 'examination_title', 'started_at', 'submitted_at',
            'status', 'score', 'percentage', 'passed', 'time_taken_seconds', 'answers',
            'subjective_submission'
        ] + TIMING_FIELDS
        read_only_fields = [
            'examination', 'started_at', 'submitted_at',
            'status', 'score', 'percentage', 'passed', 'time_taken_seconds'
        ]

    def get_subjective_submission(self, obj):
        if hasattr(obj, 'subjective_submission'):
            sub = obj.subjective_submission
            return {
                'id': sub.id,
                'status': sub.status,
                'page_count': sub.page_count,
                'file_size_bytes': sub.file_size_bytes,
                'has_answer_pdf': bool(sub.answer_pdf),
                'ocr_status': sub.ocr_status,
                'is_published': sub.is_published,
                'created_at': sub.created_at.isoformat(),
            }
        return None

class StudentExaminationAttemptListSerializer(RankedAttemptMixin, AttemptTimingMixin, serializers.ModelSerializer):
    """Lighter serializer for list views. Computes stats instead of sending all answers."""
    examination_title = serializers.CharField(source='examination.title', read_only=True)
    total_marks = serializers.SerializerMethodField()
    is_published = serializers.SerializerMethodField()
    total_questions = serializers.SerializerMethodField()
    correct_answers = serializers.SerializerMethodField()
    wrong_answers = serializers.SerializerMethodField()
    unanswered = serializers.SerializerMethodField()
    needs_evaluation = serializers.SerializerMethodField()

    class Meta:
        model = ExaminationAttempt
        fields = [
            'id', 'examination', 'examination_title', 'total_marks', 'is_published', 'started_at', 'submitted_at',
            'status', 'score', 'percentage', 'passed', 'time_taken_seconds',
            'total_questions', 'correct_answers', 'wrong_answers', 'unanswered', 'needs_evaluation',
            'rank', 'total_participants'
        ] + TIMING_FIELDS

    def get_total_marks(self, obj):
        if hasattr(obj, 'subjective_submission') and obj.subjective_submission.is_published:
            scores = list(obj.subjective_submission.question_scores.all())
            if scores:
                t = sum(qs.max_marks for qs in scores)
                if t > 0:
                    return t
        return float(obj.examination.total_marks or 100)

    def get_is_published(self, obj):
        if hasattr(obj, 'subjective_submission'):
            return obj.subjective_submission.is_published
        return obj.status == 'evaluated'

    def get_needs_evaluation(self, obj):
        if obj.examination.exam_type == 'subjective':
            if hasattr(obj, 'subjective_submission'):
                return not obj.subjective_submission.is_published
            return obj.status != 'evaluated'
        from .models import Question
        return obj.status != 'in-progress' and any(
            a.question.question_type in Question.SUBJECTIVE_TYPES and a.evaluated_at is None
            for a in obj.answers.all()
        )

    def get_total_questions(self, obj):
        return obj.examination.total_questions

    def get_correct_answers(self, obj):
        return sum(1 for a in obj.answers.all() if a.is_correct)

    def get_wrong_answers(self, obj):
        return sum(1 for a in obj.answers.all() if not a.is_correct and a.selected_option)

    def get_unanswered(self, obj):
        # A subjective answer has no selected_option even when the student
        # wrote a full response - answer_text is what "answered" means there.
        return sum(1 for a in obj.answers.all() if not a.selected_option and not a.answer_text)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Security: if subjective exam and unpublished, never expose draft scores
        if hasattr(instance, 'subjective_submission') and not instance.subjective_submission.is_published:
            data['score'] = None
            data['percentage'] = None
            data['passed'] = None
        return data


class StudentExaminationResultSerializer(RankedAttemptMixin, AttemptTimingMixin, serializers.ModelSerializer):
    """Includes correct answers and explanations for completed exams when review is allowed."""
    examination_title = serializers.CharField(source='examination.title', read_only=True)
    examination_exam_type = serializers.CharField(source='examination.exam_type', read_only=True)
    total_marks = serializers.SerializerMethodField()
    is_published = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()
    needs_evaluation = serializers.SerializerMethodField()
    show_correct_answers = serializers.SerializerMethodField()
    can_review_answers = serializers.SerializerMethodField()
    evaluator_feedback = serializers.SerializerMethodField()
    evaluator_name = serializers.SerializerMethodField()
    evaluated_at = serializers.SerializerMethodField()
    has_submitted_answer_pdf = serializers.SerializerMethodField()
    question_scores = serializers.SerializerMethodField()
    subjective_submission = serializers.SerializerMethodField()

    class Meta:
        model = ExaminationAttempt
        fields = [
            'id', 'examination', 'examination_title', 'examination_exam_type', 'total_marks',
            'is_published', 'started_at', 'submitted_at', 'status', 'score', 'percentage', 'passed',
            'time_taken_seconds', 'answers', 'needs_evaluation',
            'show_correct_answers', 'can_review_answers',
            'evaluator_feedback', 'evaluator_name', 'evaluated_at', 'has_submitted_answer_pdf',
            'question_scores', 'subjective_submission',
            'rank', 'total_participants'
        ] + TIMING_FIELDS

    def get_total_marks(self, obj):
        if hasattr(obj, 'subjective_submission') and obj.subjective_submission.is_published:
            scores = list(obj.subjective_submission.question_scores.all())
            if scores:
                t = sum(qs.max_marks for qs in scores)
                if t > 0:
                    return t
        return float(obj.examination.total_marks or 100)

    def get_is_published(self, obj):
        if hasattr(obj, 'subjective_submission'):
            return obj.subjective_submission.is_published
        return obj.status == 'evaluated'

    def get_question_scores(self, obj):
        if hasattr(obj, 'subjective_submission') and obj.subjective_submission.is_published:
            return [
                {
                    'id': qs.id,
                    'question_number': qs.question_number,
                    'max_marks': qs.max_marks,
                    'marks_obtained': qs.marks_obtained,
                    'feedback': qs.feedback,
                }
                for qs in obj.subjective_submission.question_scores.order_by('question_number', 'id')
            ]
        return []

    def get_evaluator_name(self, obj):
        if hasattr(obj, 'subjective_submission') and obj.subjective_submission.is_published and obj.subjective_submission.evaluator:
            ev = obj.subjective_submission.evaluator
            return ev.get_full_name() or ev.username
        return None

    def get_evaluated_at(self, obj):
        if hasattr(obj, 'subjective_submission') and obj.subjective_submission.is_published and obj.subjective_submission.evaluated_at:
            return obj.subjective_submission.evaluated_at.isoformat()
        return None

    def _can_review(self, obj):
        if 'can_review_answers' in self.context:
            return self.context['can_review_answers']
        if obj.status in ('in-progress', 'upload_pending'):
            return False
        exam = obj.examination
        if exam.result_visibility == 'manual' and obj.status != 'evaluated':
            return False
        if exam.result_visibility == 'after_end' and exam.end_time and timezone.now() < exam.end_time:
            return False
        if exam.exam_type in ('custom', 'practice') or exam.objective_category == 'custom':
            return True
        return bool(exam.show_correct_answers)

    def get_can_review_answers(self, obj):
        return self._can_review(obj)

    def get_show_correct_answers(self, obj):
        return self._can_review(obj)

    def get_answers(self, obj):
        context = {**self.context, 'can_review_answers': self._can_review(obj)}
        return StudentAnswerReviewSerializer(obj.answers.all(), many=True, context=context).data

    def get_needs_evaluation(self, obj):
        if obj.examination.exam_type == 'subjective':
            if hasattr(obj, 'subjective_submission'):
                return not obj.subjective_submission.is_published
            return obj.status != 'evaluated'
        from .models import Question
        return obj.status != 'in-progress' and any(
            a.question.question_type in Question.SUBJECTIVE_TYPES and a.evaluated_at is None
            for a in obj.answers.all()
        )

    def get_evaluator_feedback(self, obj):
        if hasattr(obj, 'subjective_submission'):
            return obj.subjective_submission.evaluator_feedback
        return ""

    def get_has_submitted_answer_pdf(self, obj):
        if hasattr(obj, 'subjective_submission'):
            return bool(obj.subjective_submission.answer_pdf)
        return False

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Security: if subjective exam and unpublished, mask scores and feedback
        if hasattr(instance, 'subjective_submission') and not instance.subjective_submission.is_published:
            data['score'] = None
            data['percentage'] = None
            data['passed'] = None
            data['evaluator_feedback'] = ""
        return data

    def get_subjective_submission(self, obj):
        if hasattr(obj, 'subjective_submission'):
            sub = obj.subjective_submission
            question_scores = []
            if sub.is_published:
                question_scores = [
                    {
                        'id': qs.id,
                        'question_number': qs.question_number,
                        'max_marks': qs.max_marks,
                        'marks_obtained': qs.marks_obtained,
                        'feedback': qs.feedback,
                    }
                    for qs in sub.question_scores.order_by('question_number', 'id')
                ]
            return {
                'id': sub.id,
                'status': sub.status,
                'page_count': sub.page_count,
                'file_size_bytes': sub.file_size_bytes,
                'has_answer_pdf': bool(sub.answer_pdf),
                'evaluator_feedback': sub.evaluator_feedback if sub.is_published else "",
                'evaluated_at': sub.evaluated_at.isoformat() if sub.evaluated_at and sub.is_published else None,
                'is_published': sub.is_published,
                'published_at': sub.published_at.isoformat() if sub.published_at else None,
                'question_scores': question_scores,
            }
        return None

class StudentLeaderboardSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    student_id = serializers.IntegerField(source='student__id')
    student_name = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()
    score = serializers.FloatField()
    percentage = serializers.FloatField()
    total_exams = serializers.IntegerField()
    time_taken_seconds = serializers.IntegerField(required=False)
    trend = serializers.CharField(required=False)

    def get_student_name(self, obj):
        first_name = obj.get('student__first_name', '')
        last_name = obj.get('student__last_name', '')
        if first_name or last_name:
            return f"{first_name} {last_name}".strip()
        return obj.get('student__username', 'Unknown')

    def get_profile_image(self, obj):
        return obj.get('student__avatar', None)
