from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TeacherMockExamViewSet, AdminExaminationReviewViewSet,
    ExamViewSet, SubjectViewSet, TopicViewSet, QuestionViewSet,
    PracticeSessionViewSet, DashboardView, UserTopicProgressViewSet, BookmarkViewSet,
    SubjectivePracticeSetViewSet, SubjectiveModelExamViewSet, SubjectiveQuestionViewSet,
    SubjectiveAttemptViewSet, TeacherEvaluationViewSet, TeacherQuestionViewSet,
    TeacherQuestionSetViewSet, AdminQuestionReviewViewSet, AdminPracticeSetReviewViewSet,
    QuestionAvailabilityView,
)
from .student_exam_views import (
    StudentExaminationViewSet,
    StudentExaminationRequestViewSet,
    StudentExaminationAttemptViewSet,
    TeacherExaminationAttemptViewSet,
    LeaderboardViewSet,
    CalmSessionLogView
)
from .admin_views import (
    AdminExamCategoryViewSet, AdminExamViewSet, AdminPaperViewSet,
    AdminSubjectViewSet, AdminChapterViewSet, AdminTopicViewSet,
    AdminAcademicTreeAPIView
)
from .schedule_views import (
    AdminExamScheduleViewSet,
    StudentExamScheduleNextView,
    StudentUpcomingMockExamView
)
from .public_views import (
    PublicSyllabusTreeView,
    PublicExaminationListView,
    PublicSubjectListView,
    PublicQuestionSetListView,
    PublicExamPreferenceTreeView,
)

router = DefaultRouter()
router.register(r'exams', ExamViewSet)
router.register(r'subjects', SubjectViewSet)
router.register(r'topics', TopicViewSet)
router.register(r'questions', QuestionViewSet)
router.register(r'practice-sessions', PracticeSessionViewSet, basename='practice-session')
router.register(r'topic-progress', UserTopicProgressViewSet, basename='topic-progress')
router.register(r'bookmarks', BookmarkViewSet, basename='bookmark')

# Subjective routes
router.register(r'subjective-practice-sets', SubjectivePracticeSetViewSet, basename='subjective-practice-set')
router.register(r'subjective-model-exams', SubjectiveModelExamViewSet, basename='subjective-model-exam')
router.register(r'subjective-questions', SubjectiveQuestionViewSet, basename='subjective-question')
router.register(r'subjective-attempts', SubjectiveAttemptViewSet, basename='subjective-attempt')
router.register(r'evaluations', TeacherEvaluationViewSet, basename='teacher-evaluation')
from .teacher_import_views import TeacherQuestionImportViewSet

router.register(r'teacher/questions/import', TeacherQuestionImportViewSet, basename='teacher-question-import')
router.register(r'teacher/questions', TeacherQuestionViewSet, basename='teacher-question')
router.register(r'teacher/practice-sets', TeacherQuestionSetViewSet, basename='teacher-practice-set')
router.register(r'teacher/mock-exams', TeacherMockExamViewSet, basename='teacher-mock-exam')
router.register(r'admin/questions/review-queue', AdminQuestionReviewViewSet, basename='admin-question-review')
router.register(r'admin/practice-sets/review-queue', AdminPracticeSetReviewViewSet, basename='admin-practice-set-review')
router.register(r'admin/mock-exams/review-queue', AdminExaminationReviewViewSet, basename='admin-mock-exam-review')
router.register(r'teacher/examination-attempts', TeacherExaminationAttemptViewSet, basename='teacher-examination-attempt')

# Student Exam routes
router.register(r'student/exams', StudentExaminationViewSet, basename='student-exam')
router.register(r'student/exam-requests', StudentExaminationRequestViewSet, basename='student-exam-request')
router.register(r'student/exam-attempts', StudentExaminationAttemptViewSet, basename='student-exam-attempt')
router.register(r'student/leaderboard', LeaderboardViewSet, basename='student-leaderboard')

# Admin Academic routes
router.register(r'admin/academic/categories', AdminExamCategoryViewSet, basename='admin-category')
router.register(r'admin/academic/exams', AdminExamViewSet, basename='admin-exam')
router.register(r'admin/academic/papers', AdminPaperViewSet, basename='admin-paper')
router.register(r'admin/academic/subjects', AdminSubjectViewSet, basename='admin-subject')
router.register(r'admin/academic/chapters', AdminChapterViewSet, basename='admin-chapter')
router.register(r'admin/academic/topics', AdminTopicViewSet, basename='admin-topic')

# Admin Exam Schedules
router.register(r'admin/schedules', AdminExamScheduleViewSet, basename='admin-schedules')

urlpatterns = [
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    # Public (no auth) — Syllabus, Exams & Practice pages
    path('public/syllabus/', PublicSyllabusTreeView.as_view(), name='public-syllabus'),
    path('public/exam-preferences/', PublicExamPreferenceTreeView.as_view(), name='public-exam-preferences'),
    path('public/exams/', PublicExaminationListView.as_view(), name='public-exam-list'),
    path('public/subjects/', PublicSubjectListView.as_view(), name='public-subject-list'),
    path('public/practice-sets/', PublicQuestionSetListView.as_view(), name='public-practice-sets'),
    # Master Question Bank — availability check endpoint
    path('questions/availability/', QuestionAvailabilityView.as_view(), name='question-availability'),
    path('admin/academic/tree/', AdminAcademicTreeAPIView.as_view(), name='admin-academic-tree'),
    # Student Schedule & Countdown endpoints
    path('schedules/next/', StudentExamScheduleNextView.as_view(), name='student-exam-schedule-next'),
    path('student/exam-schedule/next/', StudentExamScheduleNextView.as_view(), name='student-exam-schedule-next-alt'),
    path('student/mock-exams/upcoming/', StudentUpcomingMockExamView.as_view(), name='student-mock-exams-upcoming'),
    path('student/calm-session-log/', CalmSessionLogView.as_view(), name='student-calm-session-log'),
    path('', include(router.urls)),
]

