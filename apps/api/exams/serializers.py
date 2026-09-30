from rest_framework import serializers
from .models import Exam, Subject, Chapter, Topic, Question, PracticeSession, QuestionAttempt, UserTopicProgress

class TopicSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    accuracy = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    title = serializers.CharField(source='name')

    class Meta:
        model = Topic
        fields = ['id', 'title', 'name', 'status', 'progress', 'accuracy', 'description']

    def _progress_for(self, obj):
        """This student's UserTopicProgress row for `obj`, or None.

        All of the student's rows are read once per request and kept in the
        serializer context - a syllabus tree has dozens of topics, and each
        of the three fields below used to run its own query per topic.
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        cache = self.context.setdefault('_topic_progress', {})
        if request.user.pk not in cache:
            cache[request.user.pk] = {
                p.topic_id: p for p in UserTopicProgress.objects.filter(user=request.user)
            }
        return cache[request.user.pk].get(obj.pk)

    def get_status(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 'not-started'
        progress = self._progress_for(obj)
        return progress.status if progress else 'not-started'

    def get_progress(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        progress = self._progress_for(obj)
        return progress.progress if progress else 0

    def get_accuracy(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        progress = self._progress_for(obj)
        return progress.accuracy if progress else None

class ChapterSerializer(serializers.ModelSerializer):
    topics = TopicSerializer(many=True, read_only=True)

    class Meta:
        model = Chapter
        fields = ['id', 'title', 'topics']

class SubjectSerializer(serializers.ModelSerializer):
    chapters = ChapterSerializer(many=True, read_only=True)
    units = ChapterSerializer(source='chapters', many=True, read_only=True)
    progress = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    title = serializers.CharField(source='name')
    
    class Meta:
        model = Subject
        fields = ['id', 'title', 'name', 'code', 'progress', 'description', 'chapters', 'units']

    def get_progress(self, obj):
        # Calculate subject progress based on topics (Mocking 0 for now unless fully implemented)
        # We will just return 0 to prevent complexity, or a simple average.
        return 0

    def get_description(self, obj):
        # We didn't add description to Subject model, but mock data expects it.
        # Let's just return a generic description or empty string
        return f"Study materials for {obj.name}"

class ExamSerializer(serializers.ModelSerializer):
    subjects = serializers.SerializerMethodField()
    title = serializers.CharField(source='name') # map name to title
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = ['id', 'title', 'display_name', 'description', 'category', 'subjects']

    def get_display_name(self, obj):
        """The exam's name, qualified only when another exam in the same list
        has the identical name. The qualifier is the exam's real parent (its
        Level, e.g. "5th Level Exam") or, for a top-level exam, its category
        (e.g. "Civil Service") - never an invented label."""
        if obj.name in self.context.get('duplicate_exam_names', ()):
            qualifier = obj.parent.name if obj.parent_id else obj.category.name
            return f"{obj.name} \u2014 {qualifier}"
        return obj.name

    def get_subjects(self, obj):
        from .models import Subject
        if 'papers' in getattr(obj, '_prefetched_objects_cache', {}):
            # The list endpoint prefetches papers -> subjects -> chapters ->
            # topics in a handful of queries; read from that instead of
            # querying again for every exam.
            subjects = sorted(
                (s for paper in obj.papers.all() for s in paper.subjects.all()),
                key=lambda s: s.id,
            )
        else:
            subjects = list(Subject.objects.filter(paper__exam=obj).distinct())

        if not subjects:
            fallback = list(Subject.objects.filter(examinations__exam=obj).distinct())
            if fallback:
                subjects = sorted(fallback, key=lambda s: s.id)

        return SubjectSerializer(subjects, many=True, context=self.context).data

class QuestionFullSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = '__all__'
        read_only_fields = ['created_by', 'status', 'reviewer_comment', 'reviewed_by', 'reviewed_at', 'submitted_at']

from .models import QuestionSet, QuestionSetQuestion

class TeacherQuestionSetQuestionSerializer(serializers.ModelSerializer):
    question_details = QuestionFullSerializer(source='question', read_only=True)

    class Meta:
        model = QuestionSetQuestion
        fields = ['id', 'question', 'question_details', 'order', 'marks']
        read_only_fields = ['id']

class TeacherQuestionSetSerializer(serializers.ModelSerializer):
    questions_list = TeacherQuestionSetQuestionSerializer(source='question_set_questions', many=True, read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    position_name = serializers.CharField(source='exam.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    chapter_name = serializers.CharField(source='chapter.title', read_only=True)
    topic_name = serializers.CharField(source='topic.name', read_only=True)

    # For creating/updating questions via through model in one go
    questions_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = QuestionSet
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at', 'updated_at', 'status', 'reviewer_comment', 'reviewed_by', 'submitted_at', 'reviewed_at']

    def create(self, validated_data):
        questions_data = validated_data.pop('questions_data', [])
        question_set = super().create(validated_data)
        
        for q_data in questions_data:
            QuestionSetQuestion.objects.create(
                question_set=question_set,
                question_id=q_data['question_id'],
                order=q_data.get('order', 0),
                marks=q_data.get('marks', 1)
            )
        return question_set

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions_data', None)
        instance = super().update(instance, validated_data)
        
        if questions_data is not None:
            # Clear existing and recreate (simple approach for updating)
            instance.question_set_questions.all().delete()
            for q_data in questions_data:
                QuestionSetQuestion.objects.create(
                    question_set=instance,
                    question_id=q_data['question_id'],
                    order=q_data.get('order', 0),
                    marks=q_data.get('marks', 1)
                )
        return instance

class QuestionAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAttempt
        fields = '__all__'

class PracticeSessionSerializer(serializers.ModelSerializer):
    attempts = QuestionAttemptSerializer(many=True, read_only=True)
    
    class Meta:
        model = PracticeSession
        fields = '__all__'
        read_only_fields = ['user', 'score', 'completed']

class PracticeSessionSummarySerializer(serializers.ModelSerializer):
    """A session's own fields only - no nested attempts.

    Practice responses already carry the per-question state they need (the
    `attempts` list beside `questions`), so nesting every QuestionAttempt
    inside the session as well doubled the payload and cost an extra query
    per response. Every field is read-only: a student can never write scores
    or counters onto their own session through the API.
    """
    class Meta:
        model = PracticeSession
        fields = '__all__'
        read_only_fields = [f.name for f in PracticeSession._meta.fields]


class UserTopicProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserTopicProgress
        fields = ['topic', 'status', 'progress', 'accuracy']

class SecureQuestionSerializer(serializers.ModelSerializer):
    """Used for practice sessions to hide correct option and explanation before submission."""
    class Meta:
        model = Question
        fields = ['id', 'topic', 'text', 'option_a', 'option_b', 'option_c', 'option_d', 'difficulty', 'hint']

class BookmarkQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'topic', 'text', 'option_a', 'option_b', 'option_c', 'option_d', 'difficulty']


class BookmarkSerializer(serializers.ModelSerializer):
    question_detail = BookmarkQuestionSerializer(source='question', read_only=True)
    saved_at = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        from .models import Bookmark
        model = Bookmark
        fields = ['id', 'question', 'question_detail', 'created_at', 'saved_at', 'custom_order']
        read_only_fields = ['id', 'created_at', 'saved_at', 'custom_order']

# ============================================================
# SUBJECTIVE SERIALIZERS
# ============================================================

class SubjectiveQuestionSerializer(serializers.ModelSerializer):
    topic_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()

    class Meta:
        from .models import Question
        model = Question
        fields = ['id', 'topic', 'topic_name', 'subject_name', 'text', 'marks', 'expected_time_minutes', 'difficulty', 'status']

    def get_topic_name(self, obj):
        return obj.topic.name if obj.topic else ''

    def get_subject_name(self, obj):
        return obj.topic.chapter.subject.name if obj.topic else ''

class SubjectiveQuestionWithModelAnswerSerializer(serializers.ModelSerializer):
    """For evaluators - includes model answer"""
    topic_name = serializers.SerializerMethodField()

    class Meta:
        from .models import Question
        model = Question
        fields = ['id', 'topic', 'topic_name', 'text', 'marks', 'expected_time_minutes', 'difficulty', 'model_answer']

    def get_topic_name(self, obj):
        return obj.topic.name if obj.topic else ''

class SubjectivePracticeSetSerializer(serializers.ModelSerializer):
    subject_name = serializers.SerializerMethodField()
    topic_name = serializers.SerializerMethodField()
    question_count = serializers.SerializerMethodField()

    class Meta:
        from .models import SubjectivePracticeSet
        model = SubjectivePracticeSet
        fields = ['id', 'title', 'description', 'exam', 'subject', 'subject_name', 'topic', 'topic_name', 'question_count', 'estimated_time_minutes', 'difficulty', 'status']

    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else ''

    def get_topic_name(self, obj):
        return obj.topic.name if obj.topic else ''

    def get_question_count(self, obj):
        return obj.questions.count()

class SubjectiveModelExamSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()
    duration_minutes = serializers.IntegerField(source='time_limit')

    class Meta:
        from .models import Examination
        model = Examination
        fields = ['id', 'title', 'description', 'exam', 'duration_minutes', 'total_marks', 'passing_marks', 'status', 'question_count']

    def get_question_count(self, obj):
        return obj.questions.count()

class AnnotationSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import Annotation
        model = Annotation
        fields = ['id', 'selected_text', 'comment', 'start_offset', 'end_offset', 'created_by', 'created_at']
        read_only_fields = ['created_by', 'created_at']

class VideoFeedbackSerializer(serializers.ModelSerializer):
    embed_url = serializers.SerializerMethodField()

    class Meta:
        from .models import VideoFeedback
        model = VideoFeedback
        fields = ['id', 'youtube_url', 'embed_url', 'created_at']

    def get_embed_url(self, obj):
        import re
        url = obj.youtube_url or ''
        # Extract video ID from various YouTube URL formats
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return f'https://www.youtube.com/embed/{match.group(1)}'
        return ''

class EvaluationSerializer(serializers.ModelSerializer):
    annotations = AnnotationSerializer(many=True, read_only=True)
    video_feedback = VideoFeedbackSerializer(read_only=True)
    evaluator_name = serializers.SerializerMethodField()

    class Meta:
        from .models import Evaluation
        model = Evaluation
        fields = ['id', 'answer', 'evaluator', 'evaluator_name', 'marks_obtained', 'feedback', 'evaluated_at', 'annotations', 'video_feedback']
        read_only_fields = ['evaluator', 'evaluated_at']

    def get_evaluator_name(self, obj):
        return obj.evaluator.get_full_name() or obj.evaluator.username if obj.evaluator else 'Unknown'

class SubjectiveAnswerSerializer(serializers.ModelSerializer):
    question = SubjectiveQuestionSerializer(read_only=True)
    evaluation = EvaluationSerializer(read_only=True)

    class Meta:
        from .models import SubjectiveAnswer
        model = SubjectiveAnswer
        fields = ['id', 'attempt', 'question', 'answer_text', 'file_url', 'status', 'last_saved_at', 'submitted_at', 'word_count', 'evaluation']

class SubjectiveAttemptSerializer(serializers.ModelSerializer):
    answers = SubjectiveAnswerSerializer(many=True, read_only=True)
    practice_set_detail = SubjectivePracticeSetSerializer(source='practice_set', read_only=True)
    model_exam_detail = SubjectiveModelExamSerializer(source='model_exam', read_only=True)

    class Meta:
        from .models import SubjectiveAttempt
        model = SubjectiveAttempt
        fields = ['id', 'student', 'practice_set', 'practice_set_detail', 'model_exam', 'model_exam_detail', 'mode', 'started_at', 'submitted_at', 'status', 'answers']
        read_only_fields = ['student', 'started_at']

class SubjectiveAnswerListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for teacher pending list"""
    question = SubjectiveQuestionSerializer(read_only=True)
    student_name = serializers.SerializerMethodField()
    has_evaluation = serializers.SerializerMethodField()

    class Meta:
        from .models import SubjectiveAnswer
        model = SubjectiveAnswer
        fields = ['id', 'attempt', 'question', 'answer_text', 'file_url', 'status', 'submitted_at', 'word_count', 'student_name', 'has_evaluation']

    def get_student_name(self, obj):
        return obj.attempt.student.get_full_name() or obj.attempt.student.username

    def get_has_evaluation(self, obj):
        return hasattr(obj, 'evaluation')


class TeacherExaminationQuestionSerializer(serializers.ModelSerializer):
    question_detail = QuestionFullSerializer(source='question', read_only=True)

    class Meta:
        from .models import ExaminationQuestion
        model = ExaminationQuestion
        fields = ['id', 'question', 'question_detail', 'order', 'marks']
        read_only_fields = ['id']

class TeacherExaminationSerializer(serializers.ModelSerializer):
    questions_list = TeacherExaminationQuestionSerializer(source='examination_questions', many=True, read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    exam_name = serializers.CharField(source='exam.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    evaluation_type = serializers.ChoiceField(
        choices=[
            ('admin', 'Admin Evaluation'),
            ('manual', 'Manual Examiner Evaluation'),
            ('ai', 'AI Evaluation'),
            ('ai_assisted', 'AI-Assisted Evaluation'),
            ('hybrid', 'Hybrid Evaluation'),
        ],
        required=False,
        default='admin',
    )

    def validate_evaluation_type(self, value):
        if value == 'manual':
            return 'admin'
        if value == 'ai_assisted':
            return 'ai'
        return value

    class Meta:
        from .models import Examination
        model = Examination
        fields = [
            'id', 'title', 'description', 'exam_type', 'objective_category', 'category', 'category_name', 'exam', 'exam_name',
            'subject', 'subject_name', 'total_questions', 'time_limit', 'total_marks', 'passing_marks',
            'marks_per_question', 'negative_marking', 'negative_marking_value', 'max_attempts', 
            'allow_resume', 'auto_submit', 'result_visibility', 'show_correct_answers', 'randomize_questions', 
            'randomize_options', 'start_time', 'end_time', 'status', 'reviewer_comment', 'reviewed_by', 
            'submitted_at', 'reviewed_at', 'questions_list', 'created_at', 'updated_at',
            'question_paper_pdf', 'question_paper_page_count', 'question_paper_file_size',
            'answer_upload_enabled', 'upload_deadline_minutes', 'upload_start_time',
            'upload_end_time', 'allowed_file_types', 'max_upload_size_mb', 'evaluation_type'
        ]
        read_only_fields = [
            'status', 'reviewer_comment', 'reviewed_by', 'submitted_at', 'reviewed_at',
            'created_at', 'updated_at', 'question_paper_page_count', 'question_paper_file_size'
        ]

class AdminExaminationReviewSerializer(serializers.ModelSerializer):
    questions_list = TeacherExaminationQuestionSerializer(source='examination_questions', many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        from .models import Examination
        model = Examination
        fields = '__all__'
    
    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return "Unknown"


# ---------------------------------------------------------------------------
# Subjective evaluation queue (teacher/admin) - grades StudentAnswer rows on
# a canonical ExaminationAttempt. Deliberately reuses StudentAnswer/
# ExaminationAttempt rather than the legacy SubjectiveAnswer/Evaluation pair,
# which stays untouched for the older SubjectivePracticeSet/SubjectiveModelExam
# flows it still serves.
# ---------------------------------------------------------------------------

class EvaluationQuestionSerializer(serializers.ModelSerializer):
    """What an evaluator needs to grade a subjective answer - includes the
    reference model_answer, which must never reach a student-facing
    serializer."""
    class Meta:
        from .models import Question
        model = Question
        fields = ['id', 'text', 'question_type', 'marks', 'model_answer']


class EvaluationAnswerSerializer(serializers.ModelSerializer):
    question_detail = EvaluationQuestionSerializer(source='question', read_only=True)

    class Meta:
        from .models import StudentAnswer
        model = StudentAnswer
        fields = ['id', 'question', 'question_detail', 'answer_text', 'marks_awarded', 'evaluated_at']
        read_only_fields = ['question', 'question_detail']


class ExaminationAttemptEvaluationSerializer(serializers.ModelSerializer):
    """Detail view for one attempt's evaluation queue entry - the student's
    subjective answers alongside the exam context, nothing else."""
    examination_title = serializers.CharField(source='examination.title', read_only=True)
    student_name = serializers.SerializerMethodField()
    answers = EvaluationAnswerSerializer(many=True, read_only=True)

    class Meta:
        from .models import ExaminationAttempt
        model = ExaminationAttempt
        fields = [
            'id', 'examination', 'examination_title', 'student', 'student_name',
            'submitted_at', 'status', 'score', 'percentage', 'answers',
        ]

    def get_student_name(self, obj):
        return obj.student.get_full_name() or obj.student.username


class ExaminationAttemptEvaluationListSerializer(serializers.ModelSerializer):
    """Lightweight queue-row version - no answer bodies, just enough to
    triage which attempts still need grading."""
    examination_title = serializers.CharField(source='examination.title', read_only=True)
    student_name = serializers.SerializerMethodField()
    pending_count = serializers.SerializerMethodField()

    class Meta:
        from .models import ExaminationAttempt
        model = ExaminationAttempt
        fields = [
            'id', 'examination', 'examination_title', 'student', 'student_name',
            'submitted_at', 'status', 'score', 'percentage', 'pending_count',
        ]

    def get_student_name(self, obj):
        return obj.student.get_full_name() or obj.student.username

    def get_pending_count(self, obj):
        from .models import Question
        return sum(
            1 for a in obj.answers.all()
            if a.question.question_type in Question.SUBJECTIVE_TYPES and a.evaluated_at is None
        )


# ---------------------------------------------------------------------------
# Advanced Subjective Examination Submissions & Admin Workspace
# ---------------------------------------------------------------------------

class SubjectiveSubmissionPageSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import SubjectiveSubmissionPage
        model = SubjectiveSubmissionPage
        fields = ['id', 'page_number', 'image_file', 'file_size_bytes', 'created_at']


class SubjectiveQuestionScoreSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.text', read_only=True)

    class Meta:
        from .models import SubjectiveQuestionScore
        model = SubjectiveQuestionScore
        fields = ['id', 'question', 'question_text', 'question_number', 'marks_obtained', 'max_marks', 'feedback']


class AdminSubjectiveSubmissionListSerializer(serializers.ModelSerializer):
    student_id = serializers.IntegerField(source='attempt.student.id', read_only=True)
    student_name = serializers.SerializerMethodField()
    student_username = serializers.CharField(source='attempt.student.username', read_only=True)
    student_email = serializers.CharField(source='attempt.student.email', read_only=True)
    examination_id = serializers.IntegerField(source='attempt.examination.id', read_only=True)
    examination_title = serializers.CharField(source='attempt.examination.title', read_only=True)
    attempt_id = serializers.IntegerField(source='attempt.id', read_only=True)
    started_at = serializers.DateTimeField(source='attempt.started_at', read_only=True)
    submitted_at = serializers.DateTimeField(source='attempt.submitted_at', read_only=True)
    attempt_status = serializers.CharField(source='attempt.status', read_only=True)
    score = serializers.SerializerMethodField()
    total_marks = serializers.SerializerMethodField()
    percentage = serializers.SerializerMethodField()
    has_answer_pdf = serializers.SerializerMethodField()
    is_pdf = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    evaluator_name = serializers.SerializerMethodField()

    class Meta:
        from .models import SubjectiveSubmission
        model = SubjectiveSubmission
        fields = [
            'id', 'attempt_id', 'student_id', 'student_name', 'student_username', 'student_email',
            'examination_id', 'examination_title', 'status', 'attempt_status', 'started_at',
            'submitted_at', 'page_count', 'file_size_bytes', 'has_answer_pdf', 'is_pdf', 'file_name',
            'score', 'total_marks', 'percentage', 'ocr_status', 'evaluator', 'evaluator_name',
            'evaluated_at', 'is_published', 'published_at', 'created_at', 'updated_at'
        ]

    def get_student_name(self, obj):
        student = obj.attempt.student
        return student.get_full_name() or student.username

    def get_has_answer_pdf(self, obj):
        return bool(obj.answer_pdf)

    def get_is_pdf(self, obj):
        return bool(obj.answer_pdf)

    def get_file_name(self, obj):
        import os
        if obj.answer_pdf:
            return os.path.basename(obj.answer_pdf.name)
        elif obj.pages.exists():
            return f"{obj.page_count or obj.pages.count()} Image Page(s)"
        return "No File"

    def get_evaluator_name(self, obj):
        if obj.evaluator:
            return obj.evaluator.get_full_name() or obj.evaluator.username
        return None

    def get_score(self, obj):
        scores = list(obj.question_scores.all())
        if scores:
            return sum(qs.marks_obtained for qs in scores)
        return obj.attempt.score

    def get_total_marks(self, obj):
        scores = list(obj.question_scores.all())
        if scores:
            total = sum(qs.max_marks for qs in scores)
            if total > 0:
                return total
        return float(obj.attempt.examination.total_marks or 100)

    def get_percentage(self, obj):
        total = self.get_total_marks(obj)
        score = self.get_score(obj)
        return round((score / total) * 100, 2) if total > 0 else 0.0


class AdminSubjectiveSubmissionDetailSerializer(serializers.ModelSerializer):
    student_id = serializers.IntegerField(source='attempt.student.id', read_only=True)
    student_name = serializers.SerializerMethodField()
    student_username = serializers.CharField(source='attempt.student.username', read_only=True)
    student_email = serializers.CharField(source='attempt.student.email', read_only=True)
    examination_id = serializers.IntegerField(source='attempt.examination.id', read_only=True)
    examination_title = serializers.CharField(source='attempt.examination.title', read_only=True)
    attempt_id = serializers.IntegerField(source='attempt.id', read_only=True)
    started_at = serializers.DateTimeField(source='attempt.started_at', read_only=True)
    submitted_at = serializers.DateTimeField(source='attempt.submitted_at', read_only=True)
    time_taken_seconds = serializers.IntegerField(source='attempt.time_taken_seconds', read_only=True)
    attempt_status = serializers.CharField(source='attempt.status', read_only=True)
    score = serializers.SerializerMethodField()
    total_marks = serializers.SerializerMethodField()
    percentage = serializers.SerializerMethodField()
    has_answer_pdf = serializers.SerializerMethodField()
    is_pdf = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    evaluator_name = serializers.SerializerMethodField()
    pages = SubjectiveSubmissionPageSerializer(many=True, read_only=True)
    question_scores = serializers.SerializerMethodField()

    class Meta:
        from .models import SubjectiveSubmission
        model = SubjectiveSubmission
        fields = [
            'id', 'attempt_id', 'student_id', 'student_name', 'student_username', 'student_email',
            'examination_id', 'examination_title', 'status', 'attempt_status', 'started_at',
            'submitted_at', 'time_taken_seconds', 'page_count', 'file_size_bytes', 'has_answer_pdf',
            'is_pdf', 'file_name', 'raw_ocr_text', 'extracted_text', 'ocr_status', 'ocr_error',
            'score', 'total_marks', 'percentage', 'evaluator', 'evaluator_name', 'evaluator_feedback',
            'evaluated_at', 'is_published', 'published_at', 'pages', 'question_scores', 'created_at',
            'updated_at'
        ]

    def get_is_pdf(self, obj):
        return bool(obj.answer_pdf)

    def get_file_name(self, obj):
        import os
        if obj.answer_pdf:
            return os.path.basename(obj.answer_pdf.name)
        elif obj.pages.exists():
            return f"{obj.page_count or obj.pages.count()} Image Page(s)"
        return "No File"

    def get_student_name(self, obj):
        student = obj.attempt.student
        return student.get_full_name() or student.username

    def get_has_answer_pdf(self, obj):
        return bool(obj.answer_pdf)

    def get_evaluator_name(self, obj):
        if obj.evaluator:
            return obj.evaluator.get_full_name() or obj.evaluator.username
        return None

    def get_score(self, obj):
        scores = list(obj.question_scores.all())
        if scores:
            return sum(qs.marks_obtained for qs in scores)
        return obj.attempt.score

    def get_total_marks(self, obj):
        scores = list(obj.question_scores.all())
        if scores:
            total = sum(qs.max_marks for qs in scores)
            if total > 0:
                return total
        return float(obj.attempt.examination.total_marks or 100)

    def get_percentage(self, obj):
        total = self.get_total_marks(obj)
        score = self.get_score(obj)
        return round((score / total) * 100, 2) if total > 0 else 0.0

    def get_question_scores(self, obj):
        scores = obj.question_scores.all().order_by('question_number', 'id')
        return SubjectiveQuestionScoreSerializer(scores, many=True).data
