from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .registration_views import (
    AdminPendingVerificationsView,
    AdminResendRegistrationOTPView,
    AdminGenerateRecoveryCodeView,
)
from .self_service_views import AdminChangePasswordView
from .views import (
    AdminDashboardStatsView,
    AdminAnalyticsView,
    AdminAnalyticsExportView,
    AdminStudentsAnalyticsView,
    AdminUsersView,
    AdminUserDetailView,
    AdminUserAccessView,
    AdminAdministratorsView,
    AdminRolesView,
    AdminPermissionsView,
    AdminExamsOverviewView,
    AdminAITutorOverviewView,
    AdminAITutorProviderStatusView,
    AdminAITutorConversationsView,
    AdminAITutorConversationDetailView,
    AdminAITutorUsageView,
    AdminAITutorPromptsView,
    AdminMarketplaceOverviewView,
    AdminEvaluatorListView,
    AdminEvaluatorDetailView,
    AdminEvaluatorCreateView,
    AdminEvaluatorUpdateView,
    AdminEvaluatorsSubjectsView,
    AdminEvaluationAssignmentsView,
    AdminCourseApplicationView,
    AdminCourseApplicationDetailView,
    AdminEvaluationsView,
    AdminEvaluationDetailView,
    AdminStudyMaterialsView,
    AdminStudyMaterialDetailView,
    AdminCourseStatusView,
    AdminStudyMaterialsHierarchyView,
    AdminPreparationAcademicTreeView,
    AdminStudyPlansView,
    AdminStudyPlanDetailView,
    AdminAuditLogsView,
    AdminAuditLogDetailView,
    AdminAuditLogRetentionView,
    AdminAuditLogExportView,
    AdminAuditLogExportJobView,
    AdminNotificationsListView,
    AdminNotificationsCreateView,
    AdminNotificationsDeleteView,
    AdminNotificationDetailView,
    AdminNotificationSendView,
    AdminNotificationCancelView,
    AdminSupportTicketsView,
    AdminTicketDetailView,
    AdminTicketReplyView,
    AdminTicketUpdateStatusView,
    AdminSettingsView,
    AdminPositionsView,
    AdminPositionDetailView,
    AdminTagsView,
    AdminTagDetailView,
    AdminStorageHealthView,
)
from .syllabus_views import (
    ExamCategoryViewSet, ExamViewSet, PaperViewSet, SubjectViewSet, 
    ChapterViewSet, TopicViewSet, SyllabusStatsView, SyllabusTreeView
)

from .question_views import AdminQuestionViewSet
from .import_views import QuestionImportViewSet
from .question_set_views import QuestionSetViewSet
from .collection_views import QuestionCollectionViewSet
from .exam_views import (
    ExaminationViewSet,
    AdminSubjectiveSubmissionViewSet,
    AdminExaminationRequestViewSet,
    SubjectiveQuestionSetViewSet,
)
from .study_plan_views import AdminStudyPlanTemplateViewSet
from .leaderboard_views import AdminLeaderboardView
from study_plan import admin_api as study_plan_admin
from .feedback_views import AdminStudentFeedbackView
from .student_performance_views import (
    AdminExamAttemptReviewView, AdminStudentExamHistoryView,
    AdminStudentPerformanceView,
)
from .material_taxonomy_views import (
    AdminMaterialCategoryViewSet, AdminMaterialCollectionViewSet,
)


from .data_safety_views import (
    AdminDataSafetyOverviewView,
    AdminTrashViewSet,
    AdminDatabaseBackupViewSet,
    AdminRecoveryStatusView,
)

from exams.schedule_views import AdminExamScheduleViewSet
from core.testimonial_views import AdminTestimonialViewSet
from core.website_page_views import AdminWebsitePageViewSet

router = DefaultRouter()
router.register(r'data-safety/trash', AdminTrashViewSet, basename='admin-data-safety-trash')
router.register(r'data-safety/backups', AdminDatabaseBackupViewSet, basename='admin-data-safety-backups')
router.register(r'questions', AdminQuestionViewSet, basename='admin-questions')
router.register(r'questions/import', QuestionImportViewSet, basename='admin-question-import')
router.register(r'question-sets', QuestionSetViewSet, basename='admin-question-set')
router.register(r'collections', QuestionCollectionViewSet, basename='admin-collection')
router.register(r'exams', ExaminationViewSet, basename='admin-examination')
router.register(r'exam-requests', AdminExaminationRequestViewSet, basename='admin-exam-request')
router.register(r'subjective-question-sets', SubjectiveQuestionSetViewSet, basename='admin-subjective-question-set')
router.register(r'subjective-submissions', AdminSubjectiveSubmissionViewSet, basename='admin-subjective-submissions')
router.register(r'schedules', AdminExamScheduleViewSet, basename='admin-exam-schedules')
router.register(r'testimonials', AdminTestimonialViewSet, basename='admin-testimonials')
router.register(r'website-pages', AdminWebsitePageViewSet, basename='admin-website-pages')
router.register(r'study-plan-templates', AdminStudyPlanTemplateViewSet, basename='admin-study-plan-templates')
router.register(r'material-categories', AdminMaterialCategoryViewSet, basename='admin-material-categories')
router.register(r'material-collections', AdminMaterialCollectionViewSet, basename='admin-material-collections')
router.register(r'syllabus/categories', ExamCategoryViewSet, basename='syllabus-categories')
router.register(r'syllabus/exams', ExamViewSet, basename='syllabus-exams')
router.register(r'syllabus/papers', PaperViewSet, basename='syllabus-papers')
router.register(r'syllabus/subjects', SubjectViewSet, basename='syllabus-subjects')
router.register(r'syllabus/chapters', ChapterViewSet, basename='syllabus-chapters')
router.register(r'syllabus/topics', TopicViewSet, basename='syllabus-topics')
router.register(r'academic/categories', ExamCategoryViewSet, basename='academic-categories')
router.register(r'academic/exams', ExamViewSet, basename='academic-exams')
router.register(r'academic/papers', PaperViewSet, basename='academic-papers')
router.register(r'academic/subjects', SubjectViewSet, basename='academic-subjects')
router.register(r'academic/chapters', ChapterViewSet, basename='academic-chapters')
router.register(r'academic/topics', TopicViewSet, basename='academic-topics')

from .ai_views import AIGenerateOptionsView, AIApproveOptionsView, AIBulkGenerateContentView

urlpatterns = [
    path('dashboard/stats/', AdminDashboardStatsView.as_view(), name='admin-dashboard-stats'),
    path('data-safety/overview/', AdminDataSafetyOverviewView.as_view(), name='admin-data-safety-overview'),
    path('data-safety/recovery/', AdminRecoveryStatusView.as_view(), name='admin-data-safety-recovery'),

    path('analytics/', AdminAnalyticsView.as_view(), name='admin-analytics'),
    path('analytics/export/', AdminAnalyticsExportView.as_view(), name='admin-analytics-export'),
    path('analytics/students/', AdminStudentsAnalyticsView.as_view(), name='admin-analytics-students'),
    path('users/', AdminUsersView.as_view(), name='admin-users'),
    path('users/<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('users/<int:pk>/access/', AdminUserAccessView.as_view(), name='admin-user-access'),
    path('users/pending-verifications/', AdminPendingVerificationsView.as_view(), name='admin-users-pending-verifications'),
    path('users/<int:pk>/resend-otp/', AdminResendRegistrationOTPView.as_view(), name='admin-user-resend-otp'),
    path('users/<int:pk>/generate-recovery-code/', AdminGenerateRecoveryCodeView.as_view(), name='admin-user-generate-recovery-code'),
    path('admins/', AdminAdministratorsView.as_view(), name='admin-administrators'),
    path('roles/', AdminRolesView.as_view(), name='admin-roles'),
    path('permissions/', AdminPermissionsView.as_view(), name='admin-permissions'),
    path('exams-overview/', AdminExamsOverviewView.as_view(), name='admin-exams-overview'),
    path('ai-tutor/', AdminAITutorOverviewView.as_view(), name='admin-ai-tutor'),
    path('ai-tutor/provider-status/', AdminAITutorProviderStatusView.as_view(), name='admin-ai-tutor-provider-status'),
    path('ai-tutor/conversations/', AdminAITutorConversationsView.as_view(), name='admin-ai-tutor-conversations'),
    path('ai-tutor/conversations/<int:pk>/', AdminAITutorConversationDetailView.as_view(), name='admin-ai-tutor-conversation-detail'),
    path('ai-tutor/usage/', AdminAITutorUsageView.as_view(), name='admin-ai-tutor-usage'),
    path('ai-tutor/prompts/', AdminAITutorPromptsView.as_view(), name='admin-ai-tutor-prompts'),
    path('ai-tutor/generate-bulk-content/', AIBulkGenerateContentView.as_view(), name='admin-ai-bulk-generate'),
    path('marketplace/', AdminMarketplaceOverviewView.as_view(), name='admin-marketplace'),
    # Evaluator management
    path('evaluators/', AdminEvaluatorListView.as_view(), name='admin-evaluators'),
    path('evaluators/create/', AdminEvaluatorCreateView.as_view(), name='admin-evaluators-create'),
    path('evaluators/subjects/', AdminEvaluatorsSubjectsView.as_view(), name='admin-evaluators-subjects'),
    path('evaluators/<int:pk>/', AdminEvaluatorDetailView.as_view(), name='admin-evaluator-detail'),
    path('evaluators/<int:pk>/update/', AdminEvaluatorUpdateView.as_view(), name='admin-evaluator-update'),
    # Evaluation assignments
    path('evaluator-assignments/', AdminEvaluationAssignmentsView.as_view(), name='admin-evaluator-assignments'),
    # Evaluations list
    path('evaluations/', AdminEvaluationsView.as_view(), name='admin-evaluations'),
    path('evaluations/<int:pk>/', AdminEvaluationDetailView.as_view(), name='admin-evaluation-detail'),
    # Study materials
    path('study-materials/', AdminStudyMaterialsView.as_view(), name='admin-study-materials'),
    path('study-materials/hierarchy/', AdminStudyMaterialsHierarchyView.as_view(), name='admin-study-materials-hierarchy'),
    path('study-materials/academic-tree/', AdminPreparationAcademicTreeView.as_view(), name='admin-study-materials-academic-tree'),
    path('study-materials/<int:pk>/', AdminStudyMaterialDetailView.as_view(), name='admin-study-material-detail'),
    path('courses/<int:pk>/status/', AdminCourseStatusView.as_view(), name='admin-course-status'),
    # Study plans
    # Study Plan monitoring & analytics (computed from real activity; see study_plan/admin_api.py)
    path('study-plan/preparations/', study_plan_admin.PreparationsView.as_view(), name='admin-sp-preparations'),
    path('study-plan/overview/', study_plan_admin.OverviewView.as_view(), name='admin-sp-overview'),
    path('study-plan/students/', study_plan_admin.StudentsView.as_view(), name='admin-sp-students'),
    path('study-plan/students/<int:student_id>/', study_plan_admin.StudentDetailView.as_view(), name='admin-sp-student'),
    path('study-plan/students/<int:student_id>/<str:section>/', study_plan_admin.StudentSectionView.as_view(), name='admin-sp-student-section'),
    path('study-plan/topics/', study_plan_admin.TopicsView.as_view(), name='admin-sp-topics'),
    # Assigned study plan records (legacy manual plans)
    path('study-plans/', AdminStudyPlansView.as_view(), name='admin-study-plans'),
    path('study-plans/<int:pk>/', AdminStudyPlanDetailView.as_view(), name='admin-study-plan-detail'),
    # Ranking & Leaderboard
    path('gamification/leaderboard/', AdminLeaderboardView.as_view(), name='admin-leaderboard'),
    path('students/<int:student_id>/feedback/', AdminStudentFeedbackView.as_view(), name='admin-student-feedback'),
    # Student performance & detailed exam review
    path('students/<int:pk>/performance/', AdminStudentPerformanceView.as_view(),
         name='admin-student-performance'),
    path('students/<int:pk>/exam-history/', AdminStudentExamHistoryView.as_view(),
         name='admin-student-exam-history'),
    path('exam-attempts/<int:pk>/review/', AdminExamAttemptReviewView.as_view(),
         name='admin-exam-attempt-review'),
    # Audit logs
    path('audit-logs/', AdminAuditLogsView.as_view(), name='admin-audit-logs'),
    path('audit-logs/retention/', AdminAuditLogRetentionView.as_view(), name='admin-audit-logs-retention'),
    path('audit-logs/export/', AdminAuditLogExportView.as_view(), name='admin-audit-logs-export'),
    path('audit-logs/export-jobs/', AdminAuditLogExportJobView.as_view(), name='admin-audit-logs-export-jobs'),
    path('audit-logs/<str:event_id>/', AdminAuditLogDetailView.as_view(), name='admin-audit-log-detail'),
    # Notifications
    path('notifications/', AdminNotificationsListView.as_view(), name='admin-notifications-list'),
    path('notifications/create/', AdminNotificationsCreateView.as_view(), name='admin-notifications-create'),
    path('notifications/<int:pk>/', AdminNotificationDetailView.as_view(), name='admin-notification-detail'),
    path('notifications/<int:pk>/send/', AdminNotificationSendView.as_view(), name='admin-notification-send'),
    path('notifications/<int:pk>/cancel/', AdminNotificationCancelView.as_view(), name='admin-notification-cancel'),
    path('notifications/<int:pk>/delete/', AdminNotificationsDeleteView.as_view(), name='admin-notifications-delete'),
    # Support Tickets
    path('support/tickets/', AdminSupportTicketsView.as_view(), name='admin-support-tickets'),
    path('support/tickets/<int:pk>/', AdminTicketDetailView.as_view(), name='admin-ticket-detail'),
    path('support/tickets/<int:pk>/reply/', AdminTicketReplyView.as_view(), name='admin-ticket-reply'),
    path('support/tickets/<int:pk>/status/', AdminTicketUpdateStatusView.as_view(), name='admin-ticket-status'),
    # Settings
    path('settings/', AdminSettingsView.as_view(), name='admin-settings'),
    path('change-password/', AdminChangePasswordView.as_view(), name='admin-change-password'),
    # Storage health check
    path('storage/health/', AdminStorageHealthView.as_view(), name='admin-storage-health'),
    # Positions
    path('syllabus/positions/', AdminPositionsView.as_view(), name='admin-positions'),
    path('syllabus/positions/<int:pk>/', AdminPositionDetailView.as_view(), name='admin-position-detail'),
    # Tags
    path('syllabus/tags/', AdminTagsView.as_view(), name='admin-tags'),
    path('syllabus/tags/<int:pk>/', AdminTagDetailView.as_view(), name='admin-tag-detail'),
    # Course applications / enrollment management
    path('course-applications/', AdminCourseApplicationView.as_view(), name='admin-course-applications'),
    path('course-applications/<int:pk>/', AdminCourseApplicationDetailView.as_view(), name='admin-course-application-detail'),
    # Syllabus & Canonical Academic Tree
    path('syllabus/stats/', SyllabusStatsView.as_view(), name='syllabus-stats'),
    path('syllabus/tree/', SyllabusTreeView.as_view(), name='syllabus-tree'),
    path('academic/stats/', SyllabusStatsView.as_view(), name='academic-stats'),
    path('academic/tree/', SyllabusTreeView.as_view(), name='academic-tree'),
    # AI options
    path('questions/<int:pk>/generate-options/', AIGenerateOptionsView.as_view(), name='admin-generate-options'),
    path('questions/<int:pk>/approve-options/', AIApproveOptionsView.as_view(), name='admin-approve-options'),
    path('', include(router.urls)),
]
