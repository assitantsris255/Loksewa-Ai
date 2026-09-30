from rest_framework import viewsets, filters, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q

from administration.permissions import IsAdminUser
from core.notification_service import NotificationService
from .models import ExamSchedule, Examination
from .schedule_serializers import (
    AdminExamScheduleSerializer,
    StudentExamScheduleSerializer,
    StudentUpcomingMockExamSerializer
)

class AdminExamScheduleViewSet(viewsets.ModelViewSet):
    """
    CRUD ViewSet for Admins to manage Official Loksewa PSC exam schedules.
    """
    queryset = ExamSchedule.objects.select_related('exam_category', 'exam').all().order_by('-is_active', 'exam_date', 'exam_time', '-created_at')
    serializer_class = AdminExamScheduleSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['title', 'description', 'exam_category__name', 'exam__name']
    filterset_fields = ['is_published', 'is_active', 'exam_category', 'exam', 'exam_type']

    def get_queryset(self):
        qs = super().get_queryset()
        exam_type = self.request.query_params.get('exam_type')
        if exam_type:
            exam_type = exam_type.strip().lower()
            if exam_type != 'all':
                qs = qs.filter(Q(exam_type=exam_type) | Q(exam_type='all'))
        return qs

    def perform_create(self, serializer):
        schedule = serializer.save()
        if schedule.is_published:
            NotificationService.notify_admins_schedule_change(schedule, event_type="created")

    def perform_update(self, serializer):
        schedule = serializer.save()
        NotificationService.notify_admins_schedule_change(schedule, event_type="updated")

    @action(detail=True, methods=['post'], url_path='set-active')
    def set_active(self, request, pk=None):
        """Set this schedule as the single active Next Loksewa Exam."""
        schedule = self.get_object()
        if schedule.exam_date < timezone.now().date():
            return Response(
                {"detail": "Cannot set a past exam schedule as the active upcoming exam."},
                status=status.HTTP_400_BAD_REQUEST
            )
        schedule.is_active = True
        schedule.save()
        NotificationService.notify_admins_schedule_change(schedule, event_type="activated as Next Exam")
        return Response(AdminExamScheduleSerializer(schedule).data)

    @action(detail=True, methods=['post'], url_path='toggle-publish')
    def toggle_publish(self, request, pk=None):
        """Toggle publish/unpublish status."""
        schedule = self.get_object()
        schedule.is_published = not schedule.is_published
        schedule.save()
        event_type = "published" if schedule.is_published else "unpublished"
        NotificationService.notify_admins_schedule_change(schedule, event_type=event_type)
        return Response(AdminExamScheduleSerializer(schedule).data)


class StudentExamScheduleNextView(APIView):
    """
    Returns the authoritative Next Official Loksewa Exam schedule.
    Course-contextual for authenticated students: scopes to the student's active
    authorized course and never leaks other courses or fabricates fake dates.
    Falls back to global active schedule for public visitors.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        today = timezone.now().date()
        user = request.user if request.user.is_authenticated else None
        course_id_param = request.query_params.get('course_id')

        target_course = None

        if user and user.role == 'student':
            from courses.access import authorized_courses, get_student_course_context
            from courses.models import Course

            auth_courses = authorized_courses(user)

            if course_id_param:
                try:
                    c_id = int(course_id_param)
                except (ValueError, TypeError):
                    return Response({"detail": "Invalid course_id."}, status=status.HTTP_400_BAD_REQUEST)

                target_course = auth_courses.filter(id=c_id).first()
                if not target_course:
                    return Response(
                        {"detail": "You are not authorized to view the exam schedule for this course."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            else:
                ctx = get_student_course_context(user)
                active_c = ctx.get('active_course')
                if active_c:
                    target_course = Course.objects.filter(id=active_c['id'], status='published').first()
                else:
                    return Response({
                        "schedule": None,
                        "course_id": None,
                        "message": "No active course yet.",
                        "server_time": timezone.now().isoformat()
                    })

        elif course_id_param:
            # Public request with course_id
            from courses.models import Course
            try:
                target_course = Course.objects.filter(id=int(course_id_param), status='published').first()
            except (ValueError, TypeError):
                target_course = None

        # If a target course was determined, look for schedule matching its exam
        if target_course:
            schedule = None
            if target_course.exam_id:
                schedule = ExamSchedule.objects.filter(
                    exam_id=target_course.exam_id,
                    is_published=True,
                    exam_date__gte=today
                ).select_related('exam_category', 'exam').order_by('-is_active', 'exam_date', 'exam_time').first()

                if not schedule and target_course.exam and target_course.exam.parent_id:
                    schedule = ExamSchedule.objects.filter(
                        exam_id=target_course.exam.parent_id,
                        is_published=True,
                        exam_date__gte=today
                    ).select_related('exam_category', 'exam').order_by('-is_active', 'exam_date', 'exam_time').first()

            if not schedule:
                return Response({
                    "schedule": None,
                    "course_id": target_course.id,
                    "course_title": target_course.title,
                    "message": "No exam schedule configured for this course yet.",
                    "server_time": timezone.now().isoformat()
                })

            serializer = StudentExamScheduleSerializer(schedule)
            return Response({
                "schedule": serializer.data,
                "course_id": target_course.id,
                "course_title": target_course.title,
                "server_time": timezone.now().isoformat()
            })

        # Global fallback (unauthenticated public homepage)
        schedule = ExamSchedule.objects.filter(
            is_active=True,
            is_published=True,
            exam_date__gte=today
        ).select_related('exam_category', 'exam').first()

        if not schedule:
            schedule = ExamSchedule.objects.filter(
                is_published=True,
                exam_date__gte=today
            ).select_related('exam_category', 'exam').order_by('exam_date', 'exam_time').first()

        if not schedule:
            return Response({
                "schedule": None,
                "message": "No upcoming Loksewa exam scheduled.",
                "server_time": timezone.now().isoformat()
            })

        serializer = StudentExamScheduleSerializer(schedule)
        return Response({
            "schedule": serializer.data,
            "server_time": timezone.now().isoformat()
        })


class StudentUpcomingMockExamView(APIView):
    """
    Read-only endpoint returning the next upcoming or live Mock Exam
    eligible for the requesting student.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        now = timezone.now()
        user = request.user if request.user.is_authenticated else None

        if user and user.role == 'student':
            from courses.access import authorized_courses, get_student_course_context, get_authorized_examination_filter
            auth_courses = authorized_courses(user)
            if not auth_courses.exists():
                return Response({
                    "mock_exam": None,
                    "status": "NONE",
                    "message": "No active course enrollments.",
                    "server_time": now.isoformat()
                })

            req_course_id = request.query_params.get('course_id')
            target_course = None
            if req_course_id:
                try:
                    c_id = int(req_course_id)
                    target_course = auth_courses.filter(id=c_id).first()
                except (ValueError, TypeError):
                    target_course = None
            if not target_course:
                ctx = get_student_course_context(user)
                active_c = ctx.get('active_course')
                if active_c:
                    target_course = auth_courses.filter(id=active_c['id']).first()

            exam_q = get_authorized_examination_filter(user, target_course=target_course) if target_course else get_authorized_examination_filter(user)
            if exam_q is None:
                return Response({
                    "mock_exam": None,
                    "status": "NONE",
                    "message": "No upcoming mock examinations scheduled.",
                    "server_time": now.isoformat()
                })

            base_qs = Examination.objects.filter(status__in=['published', 'live']).filter(exam_q)
        elif user and user.role in ('teacher', 'admin', 'super-admin'):
            base_qs = Examination.objects.filter(status__in=['published', 'live'])
        else:
            # Anonymous public user - only show public/global non-custom exams
            base_qs = Examination.objects.filter(course__isnull=True, exam_type__in=['mock', 'full', 'position'], status__in=['published', 'live'])

        # Upcoming/Live Mock Exam countdown banner is ONLY for official scheduled mock exams, NEVER on-demand custom exams
        base_qs = base_qs.exclude(exam_type='custom').exclude(objective_category='custom')
        base_qs = base_qs.filter(exam_type__in=['mock', 'full', 'position'])

        # Find live exams first (where end_time is future or None)
        live_exam = base_qs.filter(
            Q(start_time__lte=now) | Q(start_time__isnull=True),
            Q(end_time__gt=now) | Q(end_time__isnull=True)
        ).select_related('category', 'exam').order_by('-start_time').first()

        if live_exam:
            serializer = StudentUpcomingMockExamSerializer(live_exam, context={'request': request})
            return Response({
                "mock_exam": serializer.data,
                "status": "LIVE",
                "server_time": now.isoformat()
            })

        # Otherwise find next upcoming exam
        upcoming_exam = base_qs.filter(
            start_time__gt=now
        ).select_related('category', 'exam').order_by('start_time').first()

        if upcoming_exam:
            serializer = StudentUpcomingMockExamSerializer(upcoming_exam, context={'request': request})
            return Response({
                "mock_exam": serializer.data,
                "status": "UPCOMING",
                "server_time": now.isoformat()
            })

        return Response({
            "mock_exam": None,
            "status": "NONE",
            "message": "No upcoming mock examinations scheduled.",
            "server_time": now.isoformat()
        })
