from django.db import models
from django.utils import timezone
from core.models import User
from django.conf import settings
from core.upload_validators import (
    validate_image_size_5mb, validate_image_extension,
    validate_document_size_20mb, validate_document_extension,
    validate_pdf_upload,
)

class ExamCategory(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Exam(models.Model):
    category = models.ForeignKey(ExamCategory, on_delete=models.CASCADE, related_name='exams')
    # Self-nesting lets one Exam row stand in for a "Level" (e.g. PSC's 4th/
    # 5th/7th Level) with its own child Exam rows underneath standing in for
    # "Service/Faculty" (e.g. Civil, Computer, Surveyor) - and Course.exam
    # already points at whichever Exam is most specific. This gives the
    # registration flow's PSC -> Level -> Service/Faculty -> Course hierarchy
    # for free, through the existing Exam admin CRUD, at arbitrary depth, for
    # any category - not just PSC - without any frontend code changes.
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='children'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('coming_soon', 'Coming Soon'),
        ('inactive', 'Inactive'),
    ]
    # Single admin-facing status for this Level/Preparation node (set from
    # the Syllabus Builder). is_active stays in sync via save() below so
    # every existing `Exam.objects.filter(is_active=True)` query - used
    # throughout the registration picker, study materials, public syllabus,
    # etc. - keeps excluding only 'inactive' nodes; 'coming_soon' nodes stay
    # visible everywhere those already show a Coming Soon badge.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.is_active = self.status != 'inactive'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Paper(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='papers')
    name = models.CharField(max_length=255)
    paper_number = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.exam.name})"

class Subject(models.Model):
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name='subjects', null=True)
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.paper.name if self.paper else 'No Paper'})"

class Chapter(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='chapters')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.subject.name})"

class Topic(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='topics')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.chapter.title}"

class UserTopicProgress(models.Model):
    STATUS_CHOICES = (
        ('not-started', 'Not Started'),
        ('in-progress', 'In Progress'),
        ('completed', 'Completed'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='topic_progress')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='user_progress')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not-started')
    accuracy = models.FloatField(null=True, blank=True)
    progress = models.IntegerField(default=0) # percentage
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'topic')

    def __str__(self):
        return f"{self.user.username} - {self.topic.name} ({self.status})"

class Question(models.Model):
    QUESTION_TYPES = (
        ('mcq', 'Multiple Choice'),
        ('true_false', 'True / False'),
        ('short_answer', 'Short Answer'),
        ('long_answer', 'Long Answer'),
        ('subjective', 'Subjective'),
    )
    # Which QUESTION_TYPES are auto-gradable via correct_option (objective)
    # vs require a human to read the answer and assign marks (subjective).
    # Single source of truth for that split - ExaminationAttempt scoring and
    # the subjective evaluation queue both branch on this instead of each
    # hardcoding its own list of type strings.
    OBJECTIVE_TYPES = ('mcq', 'true_false')
    SUBJECTIVE_TYPES = ('short_answer', 'long_answer', 'subjective')
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('pending_review', 'Pending Review'),
        ('approved', 'Approved'),
        ('changes_requested', 'Changes Requested'),
        ('rejected', 'Rejected'),
        ('archived', 'Archived'),
    )
    DIFFICULTY_CHOICES = (
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    )
    question_id = models.CharField(max_length=20, unique=True, blank=True, null=True, help_text="Permanent unique ID (e.g., Q-000001)")
    subject = models.ForeignKey('exams.Subject', on_delete=models.CASCADE, null=True, blank=True, related_name='questions')
    chapter = models.ForeignKey('exams.Chapter', on_delete=models.SET_NULL, null=True, blank=True, related_name='questions')
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name='questions')
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='mcq')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    text = models.TextField()
    
    # MCQ Fields
    option_a = models.CharField(max_length=255, blank=True, null=True)
    option_b = models.CharField(max_length=255, blank=True, null=True)
    option_c = models.CharField(max_length=255, blank=True, null=True)
    option_d = models.CharField(max_length=255, blank=True, null=True)
    correct_option = models.CharField(max_length=1, choices=(
        ('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')
    ), blank=True, null=True)
    
    # Subjective Fields
    model_answer = models.TextField(blank=True, help_text='Reference answer for evaluators')
    
    # Common properties
    marks = models.FloatField(default=1)
    negative_marks = models.FloatField(default=0)
    expected_time_minutes = models.IntegerField(default=1)
    explanation = models.TextField(blank=True)
    hint = models.TextField(blank=True, help_text="Optional hint shown to help the student answer")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium')
    # AI Fields
    ai_generate_options = models.BooleanField(default=False)
    ai_status = models.CharField(
        max_length=20, 
        choices=(('pending', 'Pending'), ('reviewed', 'Reviewed'), ('approved', 'Approved')), 
        default='pending'
    )
    
    # Moderation & Workflow Fields
    tags = models.CharField(max_length=255, blank=True, help_text="Comma-separated tags")
    # Structured, reusable tags for search/filter/discovery - distinct from the
    # free-text `tags` field above, which is left untouched. Backed by the
    # same core.Tag model the existing "Academic Management > Tags" admin
    # page already manages, so no duplicate tag system is introduced. This is
    # a search/filter concern only - it is NOT a reusable question group like
    # QuestionCollection, and must never be used as a Practice/Mock source on
    # its own the way a Collection is.
    tag_objects = models.ManyToManyField(
        'core.Tag', related_name='questions', blank=True,
        help_text="Structured tags for search, filtering and discovery.",
    )
    reference = models.CharField(max_length=255, blank=True, help_text="Source or reference material")
    reviewer_comment = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='reviewed_questions'
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='authored_questions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        # Auto-propagate academic parents if child is set
        if self.topic_id and not self.chapter_id:
            try:
                self.chapter_id = self.topic.chapter_id
            except Exception:
                pass
        if self.chapter_id and not self.subject_id:
            try:
                self.subject_id = self.chapter.subject_id
            except Exception:
                pass
        elif self.topic_id and not self.subject_id:
            try:
                self.subject_id = self.topic.chapter.subject_id
            except Exception:
                pass

        super().save(*args, **kwargs)
        if is_new and not self.question_id:
            self.question_id = f"Q-{self.pk:06d}"
            # Use update() to avoid calling save() again recursively
            Question.objects.filter(pk=self.pk).update(question_id=self.question_id)

    @property
    def usage_count(self):
        """Helper to get how many sets/exams reference this question."""
        sets_count = self.question_sets.count()
        exams_count = self.examinations_set.count()
        return sets_count + exams_count

    def __str__(self):
        return f"[{self.question_id or 'New'}] {self.text[:50]}"

class QuestionCollection(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=50, blank=True, help_text="Hex code or tailwind class")
    icon = models.CharField(max_length=50, blank=True, help_text="Lucide icon name")
    status = models.CharField(max_length=20, choices=(('active', 'Active'), ('inactive', 'Inactive')), default='active')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_collections')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    questions = models.ManyToManyField(Question, related_name='collections', blank=True)

    def __str__(self):
        return self.name

class CollectionRule(models.Model):
    collection = models.OneToOneField(QuestionCollection, on_delete=models.CASCADE, related_name='rule')
    keywords = models.JSONField(default=list, help_text="List of strings")
    apply_to_new = models.BooleanField(default=True)
    apply_to_csv = models.BooleanField(default=True)

    def __str__(self):
        return f"Rule for {self.collection.name}"

class AIClassificationSuggestion(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='ai_suggestions')
    collection = models.ForeignKey(QuestionCollection, on_delete=models.CASCADE)
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, 
        choices=(('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected')), 
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Suggestion: {self.collection.name} for {self.question.question_id}"

class QuestionSet(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('pending_review', 'Pending Review'),
        ('approved', 'Approved'), # Equivalent to published for now or just a moderation step
        ('published', 'Published'),
        ('changes_requested', 'Changes Requested'),
        ('rejected', 'Rejected'),
        ('archived', 'Archived'),
    )
    SET_TYPE_CHOICES = (
        ('full_mock', 'Full Mock Set'),
        ('subject', 'Subject Set'),
        ('chapter', 'Chapter Set'),
        ('topic', 'Topic Set'),
        ('position', 'Position-wise Set'),
        ('custom', 'Custom Set'),
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    set_type = models.CharField(max_length=20, choices=SET_TYPE_CHOICES, default='custom')
    category = models.ForeignKey(ExamCategory, on_delete=models.CASCADE, related_name='question_sets')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='question_sets', help_text="Position / Level")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='question_sets', null=True, blank=True)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='question_sets', null=True, blank=True)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='question_sets', null=True, blank=True)
    subject_distribution = models.JSONField(default=dict, blank=True, help_text="For Full Mock sets, format: {'subject_id': count}")
    
    total_questions = models.IntegerField()
    time_limit = models.IntegerField(default=60, help_text="Time limit in minutes")
    passing_marks = models.FloatField(default=0)
    total_marks = models.FloatField(default=100)
    marks_per_question = models.FloatField(default=1)
    
    negative_marking = models.BooleanField(default=False)
    negative_marking_value = models.FloatField(default=0.20, help_text="Amount deducted per wrong answer")
    
    randomize_questions = models.BooleanField(default=False)
    randomize_options = models.BooleanField(default=False)
    
    difficulty_distribution = models.JSONField(default=dict, help_text="e.g., {'easy': 20, 'medium': 20, 'hard': 10}")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    questions = models.ManyToManyField(Question, through='QuestionSetQuestion', related_name='question_sets')
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_question_sets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Moderation Workflow
    reviewer_comment = models.TextField(blank=True, null=True)
    reviewed_by = models.ForeignKey(User, related_name='reviewed_practice_sets', on_delete=models.SET_NULL, null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

class QuestionSetQuestion(models.Model):
    question_set = models.ForeignKey(QuestionSet, on_delete=models.CASCADE, related_name='question_set_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)
    marks = models.FloatField(default=1)

    class Meta:
        unique_together = ('question_set', 'question')
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.question_set.name} - Q{self.question_id}"

class PracticeSession(models.Model):
    MODE_CHOICES = (
        ('flexible', 'Flexible'),
        ('timed', 'Timed'),
        # Open-ended, no-pressure browsing of a topic's full question set —
        # no fixed count, no timer, no formal submit.
        ('study', 'Study'),
        # A system-assembled queue from QuestionMastery signals (due for
        # review, repeatedly incorrect, weak topics) rather than a topic pick.
        ('revision', 'Revision'),
        ('saved', 'Saved Questions'),
        # A curated 20-question set personalised per student for the calendar
        # day — built from weak topics, unseen questions, and exam syllabus.
        ('daily', 'Daily Practice'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='practice_sessions')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='flexible')
    shuffle_questions = models.BooleanField(default=False)
    difficulty = models.CharField(max_length=10, blank=True, null=True)
    total_questions = models.IntegerField()
    correct_count = models.IntegerField(default=0)
    incorrect_count = models.IntegerField(default=0)
    unanswered_count = models.IntegerField(default=0)
    score = models.FloatField(default=0)
    accuracy = models.FloatField(default=0)
    time_taken_seconds = models.IntegerField(default=0)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class QuestionAttempt(models.Model):
    session = models.ForeignKey(PracticeSession, on_delete=models.CASCADE, related_name='attempts')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.CharField(max_length=1, blank=True, null=True)
    is_correct = models.BooleanField(default=False)
    is_marked_for_review = models.BooleanField(default=False)
    time_taken_seconds = models.IntegerField(default=0)
    # Set when the question is displayed to the student, independent of
    # selected_option — lets Show-Answer-style viewing be distinguished from
    # actually attempting the question (selected_option is the answer signal).
    is_viewed = models.BooleanField(default=False)
    viewed_at = models.DateTimeField(null=True, blank=True)

class QuestionMastery(models.Model):
    """Per-student, per-question performance history used only by Revision Mode.

    Updated exclusively from real answers (a chosen option), never from a
    question merely being viewed or its answer being revealed — viewing is
    not evidence of knowing or not knowing a question. Bookmark/Saved
    Questions never write here either, so saving a question can't be
    mistaken for a weakness signal.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='question_mastery')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='mastery_records')
    times_answered = models.IntegerField(default=0)
    times_correct = models.IntegerField(default=0)
    times_incorrect = models.IntegerField(default=0)
    consecutive_correct = models.IntegerField(default=0)
    consecutive_incorrect = models.IntegerField(default=0)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    # Simple Leitner-style spaced repetition: a wrong answer resets the
    # interval to 1 day (due almost immediately); a right answer doubles it,
    # capped at 30 days.
    interval_days = models.IntegerField(default=1)
    next_review_at = models.DateTimeField(null=True, blank=True)
    # When this question was last answered WHILE IT WAS DUE for review (its
    # next_review_at fell on or before the end of that Nepal day). Answering
    # moves next_review_at forward, so "was it due?" cannot be worked out
    # afterwards - this records it at the moment it is true. It is what the
    # Study Plan counts as a completed revision; a first attempt, or a question
    # that was not yet due, never sets it.
    last_due_review_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'question')

    def record_answer(self, is_correct):
        import datetime
        from zoneinfo import ZoneInfo
        from django.utils import timezone
        now = timezone.now()
        nepal = ZoneInfo('Asia/Kathmandu')
        local_today = timezone.localtime(now, nepal).date()
        end_of_today = datetime.datetime.combine(local_today + datetime.timedelta(days=1), datetime.time.min, tzinfo=nepal)
        if self.times_answered > 0 and self.next_review_at is not None and self.next_review_at < end_of_today:
            self.last_due_review_at = now
        self.times_answered += 1
        if is_correct:
            self.times_correct += 1
            self.consecutive_correct += 1
            self.consecutive_incorrect = 0
            self.interval_days = min(self.interval_days * 2, 30)
        else:
            self.times_incorrect += 1
            self.consecutive_incorrect += 1
            self.consecutive_correct = 0
            self.interval_days = 1
        self.last_attempted_at = now
        self.next_review_at = now + timezone.timedelta(days=self.interval_days)
        self.save()

class Bookmark(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookmarks')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='bookmarks')
    created_at = models.DateTimeField(auto_now_add=True)
    custom_order = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'question')

# ============================================================
# SUBJECTIVE PRACTICE SYSTEM
# ============================================================

class SubjectivePracticeSet(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='subjective_practice_sets')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='subjective_practice_sets')
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name='subjective_practice_sets')
    questions = models.ManyToManyField(Question, related_name='practice_sets')
    estimated_time_minutes = models.IntegerField(default=60)
    difficulty = models.CharField(max_length=10, choices=Question.DIFFICULTY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class SubjectiveModelExam(models.Model):
    """
    [LEGACY - DEPRECATED]
    This model is being deprecated as part of the Mock Exam consolidation.
    """
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='subjective_model_exams')
    questions = models.ManyToManyField(Question, related_name='subjective_model_exams')
    duration_minutes = models.IntegerField(default=180)
    total_marks = models.FloatField(default=100)
    passing_marks = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class SubjectiveAttempt(models.Model):
    MODE_CHOICES = (
        ('practice', 'Practice Set'),
        ('topic', 'Topic Practice'),
        ('model_exam', 'Model Exam'),
    )
    STATUS_CHOICES = (
        ('in-progress', 'In Progress'),
        ('submitted', 'Submitted'),
    )
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subjective_attempts')
    practice_set = models.ForeignKey(SubjectivePracticeSet, on_delete=models.SET_NULL, null=True, blank=True, related_name='attempts')
    model_exam = models.ForeignKey(SubjectiveModelExam, on_delete=models.SET_NULL, null=True, blank=True, related_name='attempts')
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='practice')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in-progress')

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.student.username} - {self.mode} ({self.status})"

class SubjectiveAnswer(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under-review', 'Under Review'),
        ('evaluated', 'Evaluated'),
        ('returned', 'Returned'),
    )
    attempt = models.ForeignKey(SubjectiveAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.TextField(blank=True)
    file_url = models.URLField(blank=True, null=True, help_text='URL for uploaded PDF/image answer')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    last_saved_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    word_count = models.IntegerField(default=0)

    class Meta:
        unique_together = ('attempt', 'question')

    def __str__(self):
        return f"Answer for Q{self.question_id} by {self.attempt.student.username}"

class Evaluation(models.Model):
    answer = models.OneToOneField(SubjectiveAnswer, on_delete=models.CASCADE, related_name='evaluation')
    evaluator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='evaluations_given')
    marks_obtained = models.FloatField(default=0)
    feedback = models.TextField(blank=True)
    evaluated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Eval: {self.marks_obtained}/{self.answer.question.marks}"

class Annotation(models.Model):
    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name='annotations')
    selected_text = models.TextField(help_text='The highlighted portion of the student answer')
    comment = models.TextField()
    start_offset = models.IntegerField(default=0, help_text='Character offset start in answer_text')
    end_offset = models.IntegerField(default=0, help_text='Character offset end in answer_text')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Annotation: {self.comment[:40]}"

class VideoFeedback(models.Model):
    evaluation = models.OneToOneField(Evaluation, on_delete=models.CASCADE, related_name='video_feedback')
    youtube_url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Video for Eval#{self.evaluation_id}"

# ============================================================
# EXAM & MOCK TEST MANAGEMENT SYSTEM
# ============================================================

class Examination(models.Model):
    EXAM_TYPES = (
        ('mock', 'Mock Test'),
        ('practice', 'Practice Test'),
        ('full', 'Full-Length Exam'),
        ('position', 'Position-Based Exam'),
        ('subject', 'Subject Test'),
        ('custom', 'Custom Exam'),
        ('subjective', 'Subjective Exam'),
    )
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('pending_review', 'Pending Review'),
        ('approved', 'Approved'),
        ('published', 'Published'),
        ('changes_requested', 'Changes Requested'),
        ('rejected', 'Rejected'),
        ('archived', 'Archived'),
    )
    # The four finalized Objective Exam categories from the client
    # requirements doc. Deliberately separate from `exam_type` (a content
    # classification like mock/full/subjective) and from `category` (the
    # admin-defined ExamCategory taxonomy, e.g. "Loksewa"). Left blank for
    # exam_type='subjective' exams, which sit outside this scheme entirely.
    OBJECTIVE_CATEGORIES = (
        ('past_year', 'Past Year Paper'),
        ('model', 'Model Exam'),
        ('live', 'Live Exam'),
        ('topicwise', 'Topicwise Exam'),
    )
    objective_category = models.CharField(
        max_length=20, choices=OBJECTIVE_CATEGORIES, null=True, blank=True
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPES, default='mock')
    category = models.ForeignKey(ExamCategory, on_delete=models.CASCADE, related_name='examinations')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='examinations', help_text="Position / Level")
    course = models.ForeignKey('courses.Course', on_delete=models.SET_NULL, null=True, blank=True, related_name='examinations', help_text="Specific course this mock exam belongs to")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='examinations', null=True, blank=True)
    topic = models.ForeignKey('exams.Topic', on_delete=models.SET_NULL, null=True, blank=True, related_name='examinations')
    
    question_set = models.ForeignKey(QuestionSet, on_delete=models.SET_NULL, null=True, blank=True, related_name='examinations')
    subjective_question_set = models.ForeignKey(
        'exams.SubjectiveQuestionSet', on_delete=models.PROTECT, null=True, blank=True,
        related_name='examinations',
    )
    questions = models.ManyToManyField(Question, through='ExaminationQuestion', related_name='examinations_set')
    
    instructions = models.TextField(blank=True)
    thumbnail = models.ImageField(
        upload_to='exams/thumbnails/', null=True, blank=True,
        max_length=500,
        validators=[validate_image_size_5mb, validate_image_extension],
    )
    
    # Configuration (can inherit from QuestionSet or override)
    total_questions = models.IntegerField(default=0)
    time_limit = models.IntegerField(default=60, help_text="Time limit in minutes")
    total_marks = models.FloatField(default=100)
    passing_marks = models.FloatField(default=0)
    marks_per_question = models.FloatField(default=1)
    negative_marking = models.BooleanField(default=False)
    negative_marking_value = models.FloatField(default=0.20)
    
    # Attempt Settings
    max_attempts = models.IntegerField(default=1, help_text="0 for Unlimited")
    allow_resume = models.BooleanField(default=True)
    auto_submit = models.BooleanField(default=True)
    
    RESULT_VISIBILITY = (
        ('immediate', 'Immediately'),
        ('after_end', 'After Exam Ends'),
        ('manual', 'After Manual Review'),
    )
    result_visibility = models.CharField(max_length=20, choices=RESULT_VISIBILITY, default='immediate')
    show_correct_answers = models.BooleanField(default=False)
    
    # Question Behavior
    randomize_questions = models.BooleanField(default=False)
    randomize_options = models.BooleanField(default=False)
    
    # Scheduling
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_examinations')
    generation_key = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Subjective Examination Configuration
    question_paper_pdf = models.FileField(
        upload_to='subjective_exams/question_papers/', null=True, blank=True,
        max_length=500,
        validators=[validate_document_size_20mb, validate_document_extension],
    )
    question_paper_page_count = models.IntegerField(default=0, blank=True)
    question_paper_file_size = models.IntegerField(default=0, blank=True)
    answer_upload_enabled = models.BooleanField(default=True)
    upload_deadline_minutes = models.IntegerField(
        default=30, help_text="Minutes allowed to upload answer sheets after exam duration expires"
    )
    upload_start_time = models.DateTimeField(null=True, blank=True)
    upload_end_time = models.DateTimeField(null=True, blank=True)
    allowed_file_types = models.CharField(max_length=100, default='jpg,jpeg,png,webp,pdf')
    max_upload_size_mb = models.IntegerField(default=50)
    evaluation_type = models.CharField(
        max_length=20, default='admin',
        choices=(
            ('admin', 'Admin Evaluation'),
            ('manual', 'Manual Examiner Evaluation'),
            ('ai', 'AI Evaluation'),
            ('ai_assisted', 'AI-Assisted Evaluation'),
            ('hybrid', 'Hybrid Evaluation'),
        ),
    )

    # Moderation Workflow
    reviewer_comment = models.TextField(blank=True, null=True)
    reviewed_by = models.ForeignKey(User, related_name='reviewed_mock_exams', on_delete=models.SET_NULL, null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    @property
    def computed_status(self):
        """
        Calculates server-authoritative status:
        - 'DRAFT' (if status not in ['published', 'live'])
        - 'UPCOMING' (if status in ['published', 'live'] and start_time and timezone.now() < start_time)
        - 'LIVE' (if status in ['published', 'live'] and (not start_time or start_time <= timezone.now()) and (not end_time or timezone.now() <= end_time))
        - 'COMPLETED' (if status in ['published', 'live'] and end_time and timezone.now() > end_time)
        """
        if self.status not in ('published', 'live'):
            return 'DRAFT'
        now = timezone.now()
        if self.start_time and now < self.start_time:
            return 'UPCOMING'
        if self.end_time and now > self.end_time:
            return 'COMPLETED'
        return 'LIVE'

    @property
    def effective_category(self):
        """`objective_category`, except a Live Exam auto-promotes into the
        Model Exams listing 48 hours after its first scheduled start. This is
        a display-time computation (like `computed_status`) rather than a
        stored mutation, so it never depends on a scheduled job having run."""
        if self.objective_category == 'live' and self.start_time:
            if timezone.now() >= self.start_time + timezone.timedelta(hours=48):
                return 'model'
        return self.objective_category

    def __str__(self):
        return self.title


class SubjectiveQuestionSet(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('archived', 'Archived'),
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    pdf_file = models.FileField(
        upload_to='subjective_exams/question_sets/%Y/%m/',
        max_length=500,
        validators=[validate_document_size_20mb, validate_document_extension, validate_pdf_upload],
    )
    exam_category = models.ForeignKey(
        ExamCategory, on_delete=models.PROTECT, related_name='subjective_question_sets'
    )
    level = models.ForeignKey(Exam, on_delete=models.PROTECT, related_name='subjective_question_sets')
    course = models.ForeignKey(
        'courses.Course', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='subjective_question_sets',
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='subjective_question_sets',
    )
    duration_minutes = models.PositiveIntegerField(default=180)
    total_marks = models.FloatField(default=100)
    question_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='inactive')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_subjective_question_sets',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('status', 'exam_category', 'level')),
            models.Index(fields=('status', 'subject')),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.level_id and self.exam_category_id and self.level.category_id != self.exam_category_id:
            raise ValidationError({'level': 'The selected level must belong to the selected exam category.'})
        if self.subject_id and self.subject.paper.exam_id != self.level_id:
            raise ValidationError({'subject': 'The selected subject must belong to the selected level.'})
        if self.course_id and self.course.exam_id and self.course.exam_id != self.level_id:
            raise ValidationError({'course': 'The selected course must belong to the selected level.'})

    @property
    def usage_count(self):
        return self.examinations.count()

    @property
    def last_used_at(self):
        return self.examinations.order_by('-created_at').values_list('created_at', flat=True).first()

    def __str__(self):
        return self.title


class ExaminationRequest(models.Model):
    REQUEST_TYPES = (
        ('exam_access', 'Examination Access'),
        ('subjective_live', 'Subjective Live Exam'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='examination_requests')
    request_type = models.CharField(max_length=24, choices=REQUEST_TYPES, default='exam_access')
    examination = models.ForeignKey(
        Examination, on_delete=models.CASCADE, null=True, blank=True, related_name='student_requests'
    )
    academic_exam = models.ForeignKey(
        'exams.Exam', on_delete=models.CASCADE, null=True, blank=True, related_name='subjective_exam_requests'
    )
    course = models.ForeignKey(
        'courses.Course', on_delete=models.SET_NULL, null=True, blank=True, related_name='subjective_exam_requests'
    )
    subject = models.ForeignKey(
        'exams.Subject', on_delete=models.SET_NULL, null=True, blank=True, related_name='subjective_exam_requests'
    )
    topic = models.ForeignKey(
        'exams.Topic', on_delete=models.SET_NULL, null=True, blank=True, related_name='subjective_exam_requests'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_examination_requests'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('student', 'examination'),
                condition=models.Q(examination__isnull=False),
                name='unique_student_examination_request',
            ),
            models.UniqueConstraint(
                fields=('student', 'academic_exam'),
                condition=models.Q(request_type='subjective_live', status='pending'),
                name='unique_pending_subjective_request',
            ),
        ]
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.student} - {self.examination.title} ({self.status})'


class ExaminationQuestion(models.Model):
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name='examination_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)
    marks = models.FloatField(default=1)

    class Meta:
        unique_together = ('examination', 'question')
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.examination.title} - Q{self.question_id}"

class ExaminationEligibility(models.Model):
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name='eligibility_rules')
    target_category = models.ForeignKey(ExamCategory, on_delete=models.CASCADE, null=True, blank=True)
    target_position = models.ForeignKey(Exam, on_delete=models.CASCADE, null=True, blank=True)
    is_global = models.BooleanField(default=False, help_text="If True, all students can access")
    
    def __str__(self):
        return f"Eligibility for {self.examination.title}"

class ExaminationAttempt(models.Model):
    STATUS_CHOICES = (
        ('in-progress', 'In Progress'),
        ('upload_pending', 'Upload Pending'),
        ('submitted', 'Submitted'),
        ('evaluated', 'Evaluated'),
    )
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='examination_attempts')
    
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in-progress')
    
    score = models.FloatField(default=0)
    percentage = models.FloatField(default=0)
    passed = models.BooleanField(default=False)
    time_taken_seconds = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-started_at']
        
    def __str__(self):
        return f"{self.student.username} - {self.examination.title}"

class StudentAnswer(models.Model):
    attempt = models.ForeignKey(ExaminationAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.CharField(max_length=1, blank=True, null=True)
    answer_text = models.TextField(blank=True)
    is_correct = models.BooleanField(default=False)
    marks_awarded = models.FloatField(default=0)
    # Set once a teacher/admin has graded a subjective answer - distinguishes
    # "0 marks because nobody has graded this yet" from "0 marks, graded".
    # MCQ answers are auto-scored in attempt_timing.finalize_attempt and never
    # need this set - their correctness is derived, not manually judged.
    evaluated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('attempt', 'question')
        
    def __str__(self):
        return f"Answer to Q{self.question_id} by {self.attempt.student.username}"


# ============================================================
# SUBJECTIVE SUBMISSION & EVALUATION MODELS
# ============================================================

class SubjectiveSubmission(models.Model):
    SUBMISSION_STATUS_CHOICES = (
        ('upload_pending', 'Upload Pending'),
        ('processing', 'Processing'),
        ('submitted', 'Submitted'),
        ('processing_failed', 'Processing Failed'),
        ('evaluated', 'Evaluated'),
    )
    OCR_STATUS_CHOICES = (
        ('not_started', 'Not Started'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    attempt = models.OneToOneField(
        ExaminationAttempt, on_delete=models.CASCADE, related_name='subjective_submission'
    )
    status = models.CharField(max_length=25, choices=SUBMISSION_STATUS_CHOICES, default='upload_pending')
    answer_pdf = models.FileField(upload_to='subjective_exams/submissions/%Y/%m/', null=True, blank=True, max_length=500)
    page_count = models.IntegerField(default=0)
    file_size_bytes = models.IntegerField(default=0)

    # OCR / Handwriting Extraction fields
    raw_ocr_text = models.TextField(blank=True, help_text="Raw unedited handwriting extraction from OCR")
    extracted_text = models.TextField(blank=True, help_text="Admin-verified / edited transcription")
    ocr_status = models.CharField(max_length=20, choices=OCR_STATUS_CHOICES, default='not_started')
    ocr_error = models.TextField(blank=True)

    # Evaluation fields
    evaluator = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='evaluated_subjective_submissions'
    )
    evaluator_feedback = models.TextField(blank=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Subjective Submission for Attempt #{self.attempt_id} ({self.status})"


class SubjectiveSubmissionPage(models.Model):
    submission = models.ForeignKey(SubjectiveSubmission, on_delete=models.CASCADE, related_name='pages')
    page_number = models.IntegerField(default=1)
    image_file = models.FileField(upload_to='subjective_exams/pages/%Y/%m/', max_length=500)
    file_size_bytes = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['page_number', 'id']
        unique_together = ('submission', 'page_number')

    def __str__(self):
        return f"Submission #{self.submission_id} - Page {self.page_number}"


class SubjectiveQuestionScore(models.Model):
    submission = models.ForeignKey(SubjectiveSubmission, on_delete=models.CASCADE, related_name='question_scores')
    question = models.ForeignKey(Question, null=True, blank=True, on_delete=models.SET_NULL)
    question_number = models.IntegerField(default=1)
    marks_obtained = models.FloatField(default=0)
    max_marks = models.FloatField(default=10)
    feedback = models.TextField(blank=True)

    class Meta:
        ordering = ['question_number', 'id']

    def __str__(self):
        return f"Submission #{self.submission_id} - Q{self.question_number}: {self.marks_obtained}/{self.max_marks}"

class ExamSchedule(models.Model):
    """
    Authoritative model for official Loksewa PSC exam dates, announcements,
    application deadlines, and public countdowns.
    """
    title = models.CharField(max_length=255, help_text="e.g. Loksewa Section Officer 2083 First Paper")
    exam_category = models.ForeignKey(
        ExamCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='schedules'
    )
    exam = models.ForeignKey(
        Exam, on_delete=models.SET_NULL, null=True, blank=True, related_name='schedules',
        help_text="Specific Position / Level (optional)"
    )
    description = models.TextField(blank=True)
    EXAM_TYPE_CHOICES = (
        ('all', 'All Types'),
        ('topicwise', 'Topicwise Test'),
        ('objective', 'Objective Exam'),
        ('subjective', 'Subjective Exam'),
    )
    exam_type = models.CharField(
        max_length=20, choices=EXAM_TYPE_CHOICES, default='objective', blank=True,
        help_text="Primary classification: topicwise, objective, subjective, or all"
    )
    exam_date = models.DateField(help_text="Official Exam Date (YYYY-MM-DD)")
    exam_time = models.TimeField(null=True, blank=True, help_text="Exam start time (e.g. 08:00:00 or 11:00:00)")
    exam_datetime = models.DateTimeField(null=True, blank=True, help_text="Timezone-aware UTC datetime calculated from exam_date and exam_time")
    timezone = models.CharField(max_length=50, default="Asia/Kathmandu")
    application_deadline = models.DateField(null=True, blank=True)
    result_expected_date = models.DateField(null=True, blank=True)
    official_notice_url = models.URLField(blank=True)
    is_published = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, help_text="If True, this is considered the active Next Loksewa Exam")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_active', 'exam_date', 'exam_time', '-created_at']

    def save(self, *args, **kwargs):
        from datetime import datetime, time
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(self.timezone or "Asia/Kathmandu")
        except Exception:
            from datetime import timezone as dt_tz, timedelta as dt_td
            tz = dt_tz(dt_td(hours=5, minutes=45))
        
        # Calculate timezone-aware exam_datetime in Asia/Kathmandu
        if self.exam_date:
            t = self.exam_time or time(8, 0, 0)
            combined = datetime.combine(self.exam_date, t)
            if hasattr(tz, 'localize'):
                self.exam_datetime = tz.localize(combined)
            else:
                self.exam_datetime = combined.replace(tzinfo=tz)

        # Single active constraint: If marking as active, deactivate other schedules
        if self.is_active:
            ExamSchedule.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)

        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.title} ({self.exam_date})"


class CalmSessionLog(models.Model):
    """Tracks usage and skip rates of the pre-exam Calm Down Experience."""
    EVENT_CHOICES = (
        ('started', 'Started'),
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
        ('audio_enabled', 'Audio Enabled'),
    )
    
    student = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='calm_session_logs')
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    meta_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type} - {self.student.username if self.student else 'Anonymous'}"
