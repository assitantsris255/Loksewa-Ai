import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncDate
from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.db import transaction
from django.core.paginator import Paginator
from datetime import timedelta, date
from core.models import User, Position, Tag, TeacherProfile
from exams.models import Exam, Question, Examination, PracticeSession, ExaminationAttempt
from notes.models import StudyMaterial
from marketplace.models import Product, PaymentSubmission, Purchase
from games.models import GameMatch, SurvivalGame
from ai_tutor.models import Conversation, Message, TutorUsage, PromptTemplate
from courses.models import Enrollment
from subscriptions.models import Subscription
from support.models import StudentProfile, NotificationPreference
from .models import AuditLog
from .permissions import IsAdminUser, IsEvaluatorUser

logger = logging.getLogger(__name__)


def _format_time_ago(dt):
    """Return a human-readable 'time ago' string."""
    now = timezone.now()
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


class AdminDashboardStatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.core.cache import cache
        cache_key = 'admin:dashboard:stats'
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)
        except Exception:
            pass

        # Users - one aggregate query instead of three separate counts
        user_counts = User.objects.aggregate(
            total_students=Count('id', filter=Q(role='student')),
            active_students=Count('id', filter=Q(role='student', is_active=True)),
            evaluators=Count('id', filter=Q(role='teacher')),
        )
        total_students = user_counts['total_students']
        active_students = user_counts['active_students']
        evaluators = user_counts['evaluators']

        # Academic
        published_exams = Exam.objects.filter(is_active=True).count()
        questions = Question.objects.count()
        study_materials = StudyMaterial.objects.filter(status='published').count()

        # Evaluations
        from exams.models import Evaluation, SubjectiveAnswer
        pending_evaluations = SubjectiveAnswer.objects.filter(status='submitted').count()

        # Support Tickets
        from support.models import SupportTicket
        pending_tickets = SupportTicket.objects.filter(status__in=['open', 'in_progress']).count()

        # Marketplace & MRR
        marketplace_listings = Product.objects.filter(is_published=True).count()
        order_requests = PaymentSubmission.objects.filter(status='PENDING').count()
        purchase_stats = Purchase.objects.aggregate(
            total_orders=Count('id'),
            revenue=Sum('amount_paid', filter=Q(status='ACTIVE')),
        )
        total_orders = purchase_stats['total_orders']
        revenue = float(purchase_stats['revenue'] or 0)
        
        # MRR: compute entirely in the DB using a conditional expression so
        # no Subscription rows are loaded into Python memory.
        from django.db.models import Case, When, FloatField, ExpressionWrapper, F
        from django.db.models.functions import Cast
        from django.db.models import DecimalField
        mrr_qs = (
            Subscription.objects
            .filter(status='ACTIVE', expiry_date__gt=timezone.now())
            .select_related('plan')
            .aggregate(
                mrr_days=Sum(
                    Case(
                        When(plan__duration_unit='MONTHS', plan__duration__gt=0,
                             then=ExpressionWrapper(
                                 Cast(F('plan__price'), FloatField()) / Cast(F('plan__duration'), FloatField()),
                                 output_field=FloatField())),
                        When(plan__duration_unit='YEAR', plan__duration__gt=0,
                             then=ExpressionWrapper(
                                 Cast(F('plan__price'), FloatField()) / (Cast(F('plan__duration'), FloatField()) * 12),
                                 output_field=FloatField())),
                        When(plan__duration_unit='DAYS', plan__duration__gt=0,
                             then=ExpressionWrapper(
                                 Cast(F('plan__price'), FloatField()) / (Cast(F('plan__duration'), FloatField()) / 30.0),
                                 output_field=FloatField())),
                        When(plan__duration_unit='WEEKS', plan__duration__gt=0,
                             then=ExpressionWrapper(
                                 Cast(F('plan__price'), FloatField()) / (Cast(F('plan__duration'), FloatField()) / 4.33),
                                 output_field=FloatField())),
                        default=0.0,
                        output_field=FloatField(),
                    )
                )
            )
        )
        mrr = float(mrr_qs['mrr_days'] or 0)

        # Games
        games_played = (
            GameMatch.objects.filter(status='COMPLETED').count() +
            SurvivalGame.objects.filter(status='COMPLETED').count()
        )

        # AI Tutor
        total_ai_sessions = Conversation.objects.count()
        today = timezone.now().date()
        ai_sessions_today = TutorUsage.objects.filter(date=today).aggregate(
            total=Sum('request_count')
        )['total'] or 0

        # Build real recent activity from DB
        recent_activity = []
        activity_id = 1

        # Recent registrations
        recent_users = User.objects.order_by('-date_joined')[:3]
        for u in recent_users:
            recent_activity.append({
                "id": activity_id,
                "type": "registration",
                "description": f"New student '{u.get_full_name() or u.username}' registered",
                "user": u.get_full_name() or u.username,
                "time": _format_time_ago(u.date_joined),
                "status": "success",
            })
            activity_id += 1

        # Recent exam attempts
        all_recent = ExaminationAttempt.objects.select_related('student', 'examination').order_by('-started_at')[:3]

        for a in all_recent:
            title = a.examination.title
            recent_activity.append({
                "id": activity_id,
                "type": "exam_attempt",
                "description": f"'{a.student.get_full_name() or a.student.username}' attempted '{title}'",
                "user": a.student.get_full_name() or a.student.username,
                "time": _format_time_ago(a.started_at),
                "status": a.status,
            })
            activity_id += 1

        # Recent marketplace orders
        recent_orders = Purchase.objects.select_related('student', 'product').order_by('-created_at')[:3]
        for o in recent_orders:
            recent_activity.append({
                "id": activity_id,
                "type": "order",
                "description": f"Purchase of '{o.product.title}' by {o.student.get_full_name() or o.student.username}",
                "user": o.student.get_full_name() or o.student.username,
                "time": _format_time_ago(o.created_at),
                "status": o.status.lower(),
            })
            activity_id += 1

        # Sort by most recent (best effort since time is formatted)
        recent_activity = recent_activity[:10]

        payload = {
            "users": {
                "totalStudents": total_students,
                "activeStudents": active_students,
                "evaluators": evaluators,
            },
            "academic": {
                "publishedExams": published_exams,
                "questions": questions,
                "studyMaterials": study_materials,
            },
            "evaluations": {
                "pending": pending_evaluations,
            },
            "support": {
                "pendingTickets": pending_tickets,
            },
            "marketplace": {
                "activeListings": marketplace_listings,
                "orderRequests": order_requests,
                "totalOrders": total_orders,
                "revenue": revenue,
                "mrr": mrr,
            },
            "aiTutor": {
                "totalSessions": total_ai_sessions,
                "sessionsToday": ai_sessions_today,
            },
            "games": {
                "totalPlayed": games_played,
            },
            "recentActivity": recent_activity,
        }
        try:
            cache.set(cache_key, payload, 120)  # 120s — was 30s
        except Exception:
            pass
        return Response(payload)


ANALYTICS_PERIOD_DAYS = {'7d': 7, '30d': 30, '90d': 90, '1y': 365}


def _analytics_chart_data(period):
    """Real daily time-series (registrations, exam attempts, AI sessions,
    practice sessions) for the given period key. Shared by the JSON view and
    the CSV export so they can never drift apart."""
    days = ANALYTICS_PERIOD_DAYS.get(period, 30)

    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days - 1)
    date_series = [start_date + timedelta(days=i) for i in range(days)]

    reg_qs = (
        User.objects.filter(
            role='student',
            date_joined__date__gte=start_date,
            date_joined__date__lte=end_date,
        )
        .extra(select={'day': 'DATE(date_joined)'})
        .values('day')
        .annotate(count=Count('id'))
    )
    reg_map = {str(r['day']): r['count'] for r in reg_qs}

    # Exam attempts per day
    attempts_qs = (
        ExaminationAttempt.objects.filter(
            started_at__date__gte=start_date,
            started_at__date__lte=end_date,
        )
        .extra(select={'day': 'DATE(started_at)'})
        .values('day')
        .annotate(count=Count('id'))
    )
    attempts_map = {str(a['day']): a['count'] for a in attempts_qs}

    ai_qs = (
        TutorUsage.objects.filter(date__gte=start_date, date__lte=end_date)
        .values('date')
        .annotate(count=Sum('request_count'))
    )
    ai_map = {str(a['date']): a['count'] for a in ai_qs}

    practice_qs = (
        PracticeSession.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            completed=True,
        )
        .extra(select={'day': 'DATE(created_at)'})
        .values('day')
        .annotate(count=Count('id'))
    )
    practice_map = {str(p['day']): p['count'] for p in practice_qs}

    chart_data = []
    for d in date_series:
        ds = str(d)
        chart_data.append({
            "date": ds,
            "registrations": reg_map.get(ds, 0),
            "examAttempts": attempts_map.get(ds, 0),
            "aiSessions": ai_map.get(ds, 0),
            "practiceSessions": practice_map.get(ds, 0),
        })
    return days, chart_data


class AdminAnalyticsView(APIView):
    """Time-series analytics for the admin analytics page."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.core.cache import cache
        period = request.query_params.get('period', '30d')
        cache_key = f'admin:analytics:{period}'
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)
        except Exception:
            pass

        days, chart_data = _analytics_chart_data(period)
        payload = {
            "period": period,
            "days": days,
            "chartData": chart_data,
            "totals": {
                "registrations": sum(r["registrations"] for r in chart_data),
                "examAttempts": sum(r["examAttempts"] for r in chart_data),
                "aiSessions": sum(r["aiSessions"] for r in chart_data),
                "practiceSessions": sum(r["practiceSessions"] for r in chart_data),
            }
        }
        try:
            cache.set(cache_key, payload, 90)  # 90s per period
        except Exception:
            pass
        return Response(payload)


class AdminAnalyticsExportView(APIView):
    """GET /api/admin/analytics/export/ - CSV of the same real time-series
    the Overview chart shows, for the given period."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        import csv

        period = request.query_params.get('period', '30d')
        _, chart_data = _analytics_chart_data(period)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="analytics-{period}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Date', 'Registrations', 'Exam Attempts', 'AI Sessions', 'Practice Sessions'])
        for row in chart_data:
            writer.writerow([
                row['date'], row['registrations'], row['examAttempts'],
                row['aiSessions'], row['practiceSessions'],
            ])
        return response


SCORE_BUCKETS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]


class AdminStudentsAnalyticsView(APIView):
    """GET /api/admin/analytics/students/

    Cohort-level student analytics: registration trend, score distribution,
    top performers, and real recent-activity engagement. Distinct from
    AdminStudentPerformanceView (per-student drill-down at
    /api/admin/students/<id>/performance/) - this is the aggregate view.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        period = request.query_params.get('period', '30d')
        days, chart_data = _analytics_chart_data(period)
        registration_trend = [{'date': r['date'], 'count': r['registrations']} for r in chart_data]

        students = User.objects.filter(role='student')
        total_students = students.count()

        now = timezone.now()
        active_7d = students.filter(last_login__gte=now - timedelta(days=7)).count()
        active_30d = students.filter(last_login__gte=now - timedelta(days=30)).count()
        never_logged_in = students.filter(last_login__isnull=True).count()

        completed = ExaminationAttempt.objects.filter(
            student__role='student', status__in=('submitted', 'evaluated')
        )

        score_distribution = []
        for low, high in SCORE_BUCKETS:
            label = f"{low}-100" if high > 100 else f"{low}-{high}"
            count = completed.filter(percentage__gte=low, percentage__lt=high).count()
            score_distribution.append({'range': label, 'count': count})

        top_performers = (
            completed.values('student_id', 'student__username', 'student__first_name', 'student__last_name')
            .annotate(exams_completed=Count('id'), avg_percentage=Avg('percentage'))
            .filter(exams_completed__gte=1)
            .order_by('-avg_percentage')[:10]
        )
        top_performers_data = [{
            'id': row['student_id'],
            'name': (f"{row['student__first_name']} {row['student__last_name']}".strip()
                     or row['student__username']),
            'username': row['student__username'],
            'examsCompleted': row['exams_completed'],
            'averagePercentage': round(row['avg_percentage'] or 0, 2),
        } for row in top_performers]

        return Response({
            'period': period,
            'days': days,
            'registrationTrend': registration_trend,
            'summary': {
                'totalStudents': total_students,
                'active7d': active_7d,
                'active30d': active_30d,
                'neverLoggedIn': never_logged_in,
            },
            'scoreDistribution': score_distribution,
            'topPerformers': top_performers_data,
        })


class AdminUsersView(APIView):
    """Paginated user list with filters."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        role = request.query_params.get('role', '')
        search = request.query_params.get('search', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        qs = User.objects.all().order_by('-date_joined')
        if role:
            qs = qs.filter(role=role)
        if search:
            qs = qs.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )

        total = qs.count()
        start = (page - 1) * page_size
        users = qs[start:start + page_size]

        data = []
        for u in users:
            data.append({
                "id": u.id,
                "name": u.get_full_name() or u.username,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "isActive": u.is_active,
                "dateJoined": u.date_joined.isoformat(),
                "avatar": u.avatar,
            })

        return Response({
            "users": data,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size,
        })

    def post(self, request):
        username = request.data.get('username')
        email = request.data.get('email')
        password = request.data.get('password')
        role = request.data.get('role', 'student')

        if not username or not email or not password:
            return Response({'error': 'Username, email, and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email__iexact=email).exists():
            return Response({'error': 'An account with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            django_validate_password(password)
        except DjangoValidationError as e:
            return Response({'error': ' '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        if role == 'student':
            return self._create_student(request, username, email, password)

        user = User.objects.create_user(username=username, email=email, password=password, role=role)

        # Only teacher accounts are worth flagging to the rest of the admin
        # team here - admin/super-admin creation is already covered by audit
        # logs elsewhere, and student accounts created this way are rare and
        # already covered by the registration flow for the normal signup path.
        if role == 'teacher':
            from core.notification_service import NotificationService
            NotificationService.notify_admins(
                notif_type='account',
                title='New Teacher Account Created',
                message=f"{request.user.get_full_name() or request.user.username} created a teacher account for '{username}' ({email}).",
                action_url='/admin-dashboard/users',
            )

        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "message": "User created successfully."
        }, status=status.HTTP_201_CREATED)

    def _create_student(self, request, username, email, password):
        """Create a student account with immediate admin verification.
        Supports both:
        1. Explicit Package Assignment + Admin-Granted Access:
           Directly activates a canonical Subscription and Enrollment(s)
           without requiring customer payment (no fake transactions).
        2. Optional Free / Basic Student Account:
           If no package is selected, preserves existing behavior."""
        full_name = (request.data.get('name') or '').strip()
        phone = (request.data.get('mobile') or request.data.get('phone') or '').strip()
        permanent_district = (request.data.get('permanent_district') or '').strip()
        permanent_local_level = (request.data.get('permanent_local_level') or '').strip()
        exam_category_id = request.data.get('exam_category_id')
        exam_position_id = request.data.get('exam_position_id')
        course_id = request.data.get('course_id')
        package_id = request.data.get('package_id')
        if hasattr(request.data, 'getlist'):
            raw_course_ids = request.data.getlist('course_ids') or request.data.getlist('course_ids[]') or request.data.get('course_ids')
        else:
            raw_course_ids = request.data.get('course_ids')
        grant_reason = (request.data.get('grant_reason') or 'Manually enrolled by Admin').strip()
        send_welcome_email = bool(request.data.get('send_welcome_email'))

        missing = []
        if not full_name: missing.append('name')
        if not phone: missing.append('mobile')
        if not permanent_district: missing.append('permanent_district')
        if not permanent_local_level: missing.append('permanent_local_level')
        if not exam_category_id: missing.append('exam_category_id')
        if missing:
            return Response(
                {'error': f"Please provide: {', '.join(missing)}.", 'missing_fields': missing},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from core.validators import is_valid_nepal_phone
        if not is_valid_nepal_phone(phone):
            return Response({'error': 'Please enter a valid 10-digit Nepali mobile number.'}, status=status.HTTP_400_BAD_REQUEST)

        from exams.models import ExamCategory, Exam
        try:
            exam_category = ExamCategory.objects.get(id=exam_category_id, is_active=True)
        except (ExamCategory.DoesNotExist, ValueError, TypeError):
            return Response({'error': 'Please select what the student is preparing for.'}, status=status.HTTP_400_BAD_REQUEST)

        exam_position = None
        if exam_position_id:
            try:
                exam_position = Exam.objects.get(id=exam_position_id, is_active=True, category=exam_category)
            except (Exam.DoesNotExist, ValueError, TypeError):
                return Response({'error': 'Invalid exam selection.'}, status=status.HTTP_400_BAD_REQUEST)

        from courses.models import Course, Enrollment, CourseApplication
        from subscriptions.models import SubscriptionPlan, Subscription, SubscriptionCourseSelection

        start_date = timezone.now()

        # Sanitize legacy course_ids if provided (supports list, QueryDict, JSON string, or comma-separated)
        course_ids = []
        if raw_course_ids is not None:
            if isinstance(raw_course_ids, str):
                import json
                try:
                    parsed = json.loads(raw_course_ids)
                    if isinstance(parsed, list):
                        raw_course_ids = parsed
                    else:
                        raw_course_ids = [parsed]
                except (json.JSONDecodeError, ValueError):
                    raw_course_ids = [c.strip() for c in raw_course_ids.split(',') if c.strip()]
            if isinstance(raw_course_ids, (list, tuple)):
                for item in raw_course_ids:
                    if isinstance(item, str) and (',' in item or item.startswith('[')):
                        import json
                        try:
                            sub_parsed = json.loads(item)
                            if isinstance(sub_parsed, list):
                                for s in sub_parsed:
                                    try: course_ids.append(int(s))
                                    except (ValueError, TypeError): pass
                                continue
                        except Exception:
                            for s in item.split(','):
                                try: course_ids.append(int(s.strip()))
                                except (ValueError, TypeError): pass
                            continue
                    try:
                        course_ids.append(int(item))
                    except (ValueError, TypeError):
                        pass
            else:
                try:
                    course_ids.append(int(raw_course_ids))
                except (ValueError, TypeError):
                    pass

        course_ids = list(dict.fromkeys(course_ids))

        # ── PACKAGE ASSIGNMENT NORMALIZATION & VALIDATION ──────────────────────
        # Accept both `packages`: [...] (new multi-package format)
        # and `package_id` / `course_ids` (legacy single-package format).
        raw_packages = request.data.get('packages')
        if isinstance(raw_packages, str):
            import json
            try:
                raw_packages = json.loads(raw_packages)
            except Exception:
                raw_packages = None

        package_specs = []
        if isinstance(raw_packages, list) and len(raw_packages) > 0:
            for item in raw_packages:
                if isinstance(item, dict):
                    pid = item.get('package_id') or item.get('plan_id')
                    cids = item.get('course_ids') or item.get('courses') or []
                    package_specs.append({'package_id': pid, 'course_ids': cids})
        elif package_id:
            package_specs.append({'package_id': package_id, 'course_ids': course_ids})

        # Validate duplicate package IDs
        seen_pkg_ids = set()
        for ps in package_specs:
            pid = ps.get('package_id')
            if not pid:
                return Response({'error': 'Each package assignment must specify a valid package ID.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                pid = int(pid)
                ps['package_id'] = pid
            except (ValueError, TypeError):
                return Response({'error': f'Invalid package ID: {pid}.'}, status=status.HTTP_400_BAD_REQUEST)

            if pid in seen_pkg_ids:
                return Response({'error': f'Duplicate package selection: package ID {pid} cannot be selected multiple times.'}, status=status.HTTP_400_BAD_REQUEST)
            seen_pkg_ids.add(pid)

        validated_packages = []
        for ps in package_specs:
            pid = ps['package_id']
            try:
                plan = SubscriptionPlan.objects.get(id=pid, status='ACTIVE')
            except (SubscriptionPlan.DoesNotExist, ValueError, TypeError):
                return Response({'error': f'Selected package {pid} does not exist or is inactive.'}, status=status.HTTP_400_BAD_REQUEST)

            # Sanitize course IDs for this specific package
            pkg_raw_cids = ps.get('course_ids') or []
            if isinstance(pkg_raw_cids, str):
                import json
                try:
                    pkg_raw_cids = json.loads(pkg_raw_cids)
                except Exception:
                    pkg_raw_cids = [c.strip() for c in pkg_raw_cids.split(',') if c.strip()]
            pkg_cids = []
            if isinstance(pkg_raw_cids, (list, tuple)):
                for c in pkg_raw_cids:
                    try: pkg_cids.append(int(c))
                    except (ValueError, TypeError): pass
            else:
                try: pkg_cids.append(int(pkg_raw_cids))
                except (ValueError, TypeError): pass
            pkg_cids = list(dict.fromkeys(pkg_cids))

            selected_pkg_courses = []
            if plan.package_type == 'SINGLE':
                single_course = None
                if plan.course:
                    single_course = plan.course
                elif pkg_cids:
                    if len(pkg_cids) != 1:
                        return Response({'error': f"Package '{plan.name}' requires selecting exactly 1 course."}, status=status.HTTP_400_BAD_REQUEST)
                    single_course = Course.objects.filter(id=pkg_cids[0], status='published').first()
                elif plan.eligible_courses.count() == 1:
                    single_course = plan.eligible_courses.first()
                elif course_id:
                    single_course = Course.objects.filter(id=course_id, status='published').first()

                if not single_course or single_course.status != 'published':
                    return Response({'error': f"Please select a valid published course for package '{plan.name}'."}, status=status.HTTP_400_BAD_REQUEST)

                if plan.eligible_courses.exists() and not plan.eligible_courses.filter(id=single_course.id).exists():
                    return Response({'error': f"Course '{single_course.title}' is not eligible for package '{plan.name}'."}, status=status.HTTP_400_BAD_REQUEST)

                selected_pkg_courses = [single_course]

            elif plan.package_type == 'MULTI':
                if not pkg_cids:
                    return Response({'error': f"Please select course(s) for package '{plan.name}'."}, status=status.HTTP_400_BAD_REQUEST)
                if len(pkg_cids) > plan.allowed_preparation_count:
                    return Response(
                        {'error': f"Package '{plan.name}' allows at most {plan.allowed_preparation_count} preparation(s)."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                eligible_ids = set(plan.eligible_courses.values_list('id', flat=True))
                if eligible_ids:
                    ineligible = [cid for cid in pkg_cids if cid not in eligible_ids]
                    if ineligible:
                        return Response({'error': f"Some selected courses are not eligible for package '{plan.name}'."}, status=status.HTTP_400_BAD_REQUEST)

                courses_found = list(Course.objects.filter(id__in=pkg_cids, status='published'))
                if len(courses_found) != len(pkg_cids):
                    return Response({'error': f"One or more selected courses for package '{plan.name}' are invalid or not published."}, status=status.HTTP_400_BAD_REQUEST)
                selected_pkg_courses = courses_found

            elif plan.package_type == 'BUNDLE':
                bundle_courses = list(plan.eligible_courses.filter(status='published'))
                if not bundle_courses:
                    return Response({'error': f"Bundle package '{plan.name}' has no published eligible courses."}, status=status.HTTP_400_BAD_REQUEST)
                selected_pkg_courses = bundle_courses

            elif plan.package_type == 'ALL_ACCESS':
                selected_pkg_courses = list(Course.objects.filter(status='published'))

            # Calculate individual expiry for this plan
            if plan.duration_unit == 'DAYS':
                delta = timedelta(days=plan.duration)
            elif plan.duration_unit == 'WEEKS':
                delta = timedelta(weeks=plan.duration)
            elif plan.duration_unit == 'MONTHS':
                delta = timedelta(days=30 * plan.duration)
            elif plan.duration_unit == 'YEAR':
                delta = timedelta(days=365 * plan.duration)
            else:
                delta = timedelta(days=plan.duration)
            pkg_expiry_date = start_date + delta

            validated_packages.append({
                'plan': plan,
                'courses': selected_pkg_courses,
                'expiry_date': pkg_expiry_date,
            })

        course = None
        if not validated_packages and course_id:
            try:
                course = Course.objects.get(id=course_id, status='published')
            except (Course.DoesNotExist, ValueError, TypeError):
                return Response({'error': 'Invalid course selection.'}, status=status.HTTP_400_BAD_REQUEST)

        first_name, _, last_name = full_name.partition(' ')

        # ── ATOMIC CREATION ──────────────────────────────────────────────────
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username, email=email, password=password, role='student',
                    first_name=first_name[:150], last_name=last_name[:150],
                )

                # Collect all distinct courses across all packages
                all_enrolled_courses = []
                seen_cids = set()
                for vp in validated_packages:
                    for c in vp['courses']:
                        if c.id not in seen_cids:
                            seen_cids.add(c.id)
                            all_enrolled_courses.append(c)

                primary_course = all_enrolled_courses[0] if all_enrolled_courses else None
                student_target_position = exam_position or (primary_course.exam if primary_course else None)

                # Longest expiry date for StudentProfile
                max_profile_expiry = max((vp['expiry_date'] for vp in validated_packages), default=None)

                StudentProfile.objects.create(
                    user=user, phone=phone,
                    permanent_district=permanent_district, permanent_local_level=permanent_local_level,
                    target_category=exam_category, target_position=student_target_position,
                    target_course=primary_course,
                    is_verified=True, verified_at=start_date,
                    access_origin='ADMIN_GRANTED',
                    admin_granted_by=request.user,
                    admin_granted_at=start_date,
                    admin_access_expiry=max_profile_expiry,
                    admin_access_note=grant_reason,
                )
                NotificationPreference.objects.create(user=user)

                from gamification.models import GamificationProfile
                GamificationProfile.objects.create(user=user)

                created_subscriptions = []
                for vp in validated_packages:
                    plan = vp['plan']
                    pkg_courses = vp['courses']
                    pkg_expiry = vp['expiry_date']

                    subscription = Subscription.objects.create(
                        student=user,
                        plan=plan,
                        status='ACTIVE',
                        source='ADMIN_GRANT',
                        admin_grant_reason=grant_reason,
                        granted_by=request.user,
                        start_date=start_date,
                        expiry_date=pkg_expiry,
                    )
                    created_subscriptions.append({
                        'subscription': subscription,
                        'plan': plan,
                        'courses': pkg_courses,
                        'expiry_date': pkg_expiry,
                    })

                    for course_item in pkg_courses:
                        SubscriptionCourseSelection.objects.create(
                            subscription=subscription,
                            course=course_item,
                        )
                        enrollment, created = Enrollment.objects.get_or_create(
                            student=user,
                            course=course_item,
                            defaults={
                                'status': 'active',
                                'expires_at': pkg_expiry,
                            }
                        )
                        if not created:
                            enrollment.status = 'active'
                            if pkg_expiry and (not enrollment.expires_at or pkg_expiry > enrollment.expires_at):
                                enrollment.expires_at = pkg_expiry
                            enrollment.save(update_fields=['status', 'expires_at'])

                if created_subscriptions:
                    first_sub = created_subscriptions[0]
                    AuditLog.objects.create(
                        actor=request.user,
                        action='ADMIN_STUDENT_GRANTED_PACKAGE',
                        entity_type='User',
                        entity_id=str(user.id),
                        details={
                            'email': email,
                            'username': username,
                            'created_by': request.user.username,
                            'grant_reason': grant_reason,
                            'packages_count': len(created_subscriptions),
                            'packages': [
                                {
                                    'package_id': cs['plan'].id,
                                    'package_name': cs['plan'].name,
                                    'package_type': cs['plan'].package_type,
                                    'subscription_id': cs['subscription'].id,
                                    'expiry_date': cs['expiry_date'].isoformat(),
                                    'courses': [{'id': c.id, 'title': c.title} for c in cs['courses']],
                                }
                                for cs in created_subscriptions
                            ],
                            'total_enrollments_count': len(all_enrolled_courses),
                            'enrolled_courses': [{'id': c.id, 'title': c.title} for c in all_enrolled_courses],
                            # Backward compatible keys:
                            'package_id': first_sub['plan'].id,
                            'package_name': first_sub['plan'].name,
                            'package_type': first_sub['plan'].package_type,
                            'subscription_id': first_sub['subscription'].id,
                            'expiry_date': first_sub['expiry_date'].isoformat(),
                            'courses': [{'id': c.id, 'title': c.title} for c in first_sub['courses']],
                            'enrollments_count': len(all_enrolled_courses),
                        },
                    )
                else:
                    if course_id and course:
                        CourseApplication.objects.create(student=user, course=course, status='pending')

                    AuditLog.objects.create(
                        actor=request.user,
                        action='ADMIN_STUDENT_CREATED',
                        entity_type='User',
                        entity_id=str(user.id),
                        details={'email': email, 'username': username, 'created_by': request.user.username},
                    )

        except Exception:
            logger.exception("Admin-created student setup failed for email=%s", email)
            return Response({'error': 'Failed to create student account due to an internal error.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if send_welcome_email:
            from core.email_service import send_account_created_email
            send_account_created_email(email, username)

        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "packageGranted": bool(created_subscriptions),
            "packageName": created_subscriptions[0]['plan'].name if created_subscriptions else None,
            "packagesCount": len(created_subscriptions),
            "packagesGranted": [
                {
                    "id": cs['plan'].id,
                    "name": cs['plan'].name,
                    "packageType": cs['plan'].package_type,
                    "subscriptionId": cs['subscription'].id,
                    "courses": [c.title for c in cs['courses']],
                    "expiryDate": cs['expiry_date'].isoformat(),
                }
                for cs in created_subscriptions
            ],
            "enrolledCourses": [c.title for c in all_enrolled_courses],
            "message": "Student account created successfully."
        }, status=status.HTTP_201_CREATED)


class AdminUserDetailView(APIView):
    """View, update, or suspend a specific user."""
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        try:
            user = User.objects.select_related('student_profile', 'teacher_profile').get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        data = {
            "id": user.id,
            "username": user.username,
            "firstName": user.first_name,
            "lastName": user.last_name,
            "name": user.get_full_name() or user.username,
            "email": user.email,
            "role": user.role,
            "isActive": user.is_active,
            "isStaff": user.is_staff,
            "is2FAEnabled": user.is_2fa_enabled,
            "avatar": user.avatar,
            "dateJoined": user.date_joined.isoformat(),
            "lastLogin": user.last_login.isoformat() if user.last_login else None,
        }

        if user.role == 'student':
            try:
                profile = user.student_profile
                data["studentProfile"] = {
                    "phone": profile.phone,
                    "bio": profile.bio,
                    "targetCategory": profile.target_category.name if profile.target_category else None,
                    "targetPosition": profile.target_position.name if profile.target_position else None,
                    "permanentDistrict": profile.permanent_district,
                    "permanentLocalLevel": profile.permanent_local_level,
                    "accessOrigin": profile.access_origin,
                    "adminAccessExpiry": profile.admin_access_expiry.isoformat() if profile.admin_access_expiry else None,
                    "adminAccessNote": profile.admin_access_note,
                    "adminGrantedBy": profile.admin_granted_by.username if profile.admin_granted_by else None,
                    "adminGrantedAt": profile.admin_granted_at.isoformat() if profile.admin_granted_at else None,
                    "isVerified": profile.is_verified,
                    "preferredStudyTime": profile.preferred_study_time,
                    "dailyStudyGoalMinutes": profile.daily_study_goal_minutes,
                    "difficultyPreference": profile.difficulty_preference,
                    "studyMode": profile.study_mode,
                    "language": profile.language,
                }
            except StudentProfile.DoesNotExist:
                data["studentProfile"] = None

            enrollments = Enrollment.objects.filter(student=user).select_related('course').order_by('-enrolled_at')
            data["enrollments"] = [
                {
                    "courseTitle": e.course.title,
                    "status": e.status,
                    "enrolledAt": e.enrolled_at.isoformat(),
                    "expiresAt": e.expires_at.isoformat() if e.expires_at else None,
                }
                for e in enrollments
            ]

            active_subs = list(Subscription.objects.filter(student=user, status='ACTIVE').select_related('plan', 'granted_by').order_by('-expiry_date'))
            data["subscriptions"] = [
                {
                    "id": s.id,
                    "planId": s.plan.id,
                    "planName": s.plan.name,
                    "packageType": s.plan.package_type,
                    "status": s.status,
                    "source": s.source,
                    "accessSource": "Admin Granted" if s.source == 'ADMIN_GRANT' else "Student Payment",
                    "adminGrantReason": s.admin_grant_reason,
                    "grantedBy": s.granted_by.username if s.granted_by else None,
                    "startDate": s.start_date.isoformat(),
                    "expiryDate": s.expiry_date.isoformat(),
                    "isActive": s.is_active,
                }
                for s in active_subs
            ]
            data["subscription"] = data["subscriptions"][0] if data["subscriptions"] else None

            exam_attempts = ExaminationAttempt.objects.filter(student=user, status='evaluated')
            exam_agg = exam_attempts.aggregate(avg_pct=Avg('percentage'), total=Count('id'), passed=Count('id', filter=Q(passed=True)))
            practice_sessions = PracticeSession.objects.filter(user=user, completed=True)
            practice_agg = practice_sessions.aggregate(avg_accuracy=Avg('accuracy'), total=Count('id'))

            data["examStats"] = {
                "totalAttempts": exam_agg['total'] or 0,
                "averagePercentage": round(exam_agg['avg_pct'], 1) if exam_agg['avg_pct'] is not None else None,
                "passedCount": exam_agg['passed'] or 0,
            }
            data["practiceStats"] = {
                "totalSessions": practice_agg['total'] or 0,
                "averageAccuracy": round(practice_agg['avg_accuracy'], 1) if practice_agg['avg_accuracy'] is not None else None,
            }
            data["purchaseCount"] = Purchase.objects.filter(student=user).count()

        elif user.role == 'teacher':
            try:
                profile = user.teacher_profile
                data["teacherProfile"] = {
                    "bio": profile.bio,
                    "specialization": profile.specialization,
                    "designation": profile.designation,
                    "experienceYears": profile.experience_years,
                    "phoneNumber": profile.phone_number,
                    "preferredDifficulty": profile.preferred_difficulty,
                    "preferredQuestionType": profile.preferred_question_type,
                }
            except TeacherProfile.DoesNotExist:
                data["teacherProfile"] = None

        return Response(data)

    def patch(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        is_active = request.data.get('is_active')
        was_active = user.is_active
        if is_active is not None:
            user.is_active = is_active

        role = request.data.get('role')
        if role:
            user.role = role

        user.save()

        # Deactivation is a meaningful account-status change worth an audit
        # trail for the rest of the admin team, regardless of which admin
        # performed it. Only fires on the True -> False transition, not on
        # every save of an already-inactive account.
        if was_active and not user.is_active:
            from core.notification_service import NotificationService
            NotificationService.notify_admins(
                notif_type='account',
                title='Account Deactivated',
                message=f"{request.user.get_full_name() or request.user.username} deactivated {user.role} account '{user.username}'.",
                action_url='/admin-dashboard/users',
                priority='important',
            )

        return Response({
            "id": user.id,
            "username": user.username,
            "isActive": user.is_active,
            "role": user.role,
            "message": "User updated successfully."
        })

    def delete(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        if user.id == request.user.id:
            return Response({'error': 'You cannot delete your own account.'}, status=status.HTTP_400_BAD_REQUEST)

        if user.role == 'super-admin' and request.user.role != 'super-admin':
            return Response({'error': 'Only a super-admin can delete a super-admin account.'}, status=status.HTTP_403_FORBIDDEN)

        username, email, role = user.username, user.email, user.role
        user.delete()

        AuditLog.objects.create(
            actor=request.user, action='DELETE_USER',
            entity_type='User', entity_id=str(pk),
            details={"username": username, "email": email, "role": role},
        )

        from core.notification_service import NotificationService
        NotificationService.notify_admins(
            notif_type='account',
            title='Account Deleted',
            message=f"{request.user.get_full_name() or request.user.username} permanently deleted {role} account '{username}'.",
            action_url='/admin-dashboard/users',
            priority='important',
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserAccessView(APIView):
    """Grant or revoke admin-granted access for a student."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        from support.models import StudentProfile
        from django.utils import timezone
        try:
            user = User.objects.get(pk=pk, role='student')
            profile = user.student_profile
        except (User.DoesNotExist, StudentProfile.DoesNotExist):
            return Response({'error': 'Student not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        expiry = request.data.get('expiry')
        note = request.data.get('note', '')

        parsed_expiry = None
        if expiry:
            try:
                parsed_expiry = timezone.datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            except ValueError:
                return Response({'error': 'Invalid expiry date format.'}, status=status.HTTP_400_BAD_REQUEST)

        profile.access_origin = 'ADMIN_GRANTED'
        profile.admin_access_expiry = parsed_expiry
        profile.admin_access_note = note
        profile.admin_granted_by = request.user
        profile.admin_granted_at = timezone.now()
        profile.save(update_fields=['access_origin', 'admin_access_expiry', 'admin_access_note', 'admin_granted_by', 'admin_granted_at', 'updated_at'])

        AuditLog.objects.create(
            actor=request.user, action='ADMIN_GRANTED_ACCESS',
            entity_type='User', entity_id=str(user.id),
            details={'expiry': expiry, 'note': note}
        )
        return Response({'message': 'Access granted successfully.'})

    def delete(self, request, pk):
        from support.models import StudentProfile
        try:
            user = User.objects.get(pk=pk, role='student')
            profile = user.student_profile
        except (User.DoesNotExist, StudentProfile.DoesNotExist):
            return Response({'error': 'Student not found.'}, status=status.HTTP_404_NOT_FOUND)

        profile.access_origin = 'SELF_REGISTERED'
        profile.admin_access_expiry = None
        profile.admin_access_note = ''
        profile.admin_granted_by = None
        profile.admin_granted_at = None
        profile.save(update_fields=['access_origin', 'admin_access_expiry', 'admin_access_note', 'admin_granted_by', 'admin_granted_at', 'updated_at'])

        AuditLog.objects.create(
            actor=request.user, action='ADMIN_REVOKED_ACCESS',
            entity_type='User', entity_id=str(user.id),
            details={}
        )
        return Response({'message': 'Access revoked successfully.'})


class AdminRolesView(APIView):
    """Get list of system roles and their usage statistics."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        # System roles and their usage
        roles_data = [
            {
                "id": "super-admin",
                "name": "Super Administrator",
                "description": "Full platform access with all permissions",
                "users": User.objects.filter(role='super-admin').count(),
                "color": "red",
                "type": "system"
            },
            {
                "id": "admin",
                "name": "Administrator",
                "description": "Can manage users, content, and settings",
                "users": User.objects.filter(role='admin').count(),
                "color": "blue",
                "type": "system"
            },
            {
                "id": "teacher",
                "name": "Teacher",
                "description": "Can create content and manage students",
                "users": User.objects.filter(role='teacher').count(),
                "color": "purple",
                "type": "system"
            },
            {
                "id": "student",
                "name": "Student",
                "description": "Can access learning materials and take exams",
                "users": User.objects.filter(role='student').count(),
                "color": "green",
                "type": "system"
            },
        ]

        return Response({
            "roles": roles_data,
            "total": len(roles_data),
            "totalUsers": User.objects.count(),
        })


class AdminAdministratorsView(APIView):
    """Get list of all administrators (admin and super-admin users)."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        search = request.query_params.get('search', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        # Filter for admin and super-admin users only
        qs = User.objects.filter(
            Q(role='admin') | Q(role='super-admin')
        ).order_by('-date_joined')

        if search:
            qs = qs.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )

        total = qs.count()
        start = (page - 1) * page_size
        admins = qs[start:start + page_size]

        data = []
        for admin in admins:
            data.append({
                "id": admin.id,
                "name": admin.get_full_name() or admin.username,
                "username": admin.username,
                "email": admin.email,
                "role": admin.role,
                "isActive": admin.is_active,
                "dateJoined": admin.date_joined.isoformat(),
                "avatar": admin.avatar,
            })

        return Response({
            "users": data,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size,
        })


class AdminExamsOverviewView(APIView):
    """Exams overview for admin dashboard."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.core.cache import cache
        cache_key = 'admin:exams:overview'
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)
        except Exception:
            pass

        exam_stats = Examination.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status__in=('published', 'live'))),
        )
        total_exams = exam_stats['total']
        active_exams = exam_stats['active']

        model_exams_qs = Examination.objects.filter(objective_category='model')
        model_exam_stats = model_exams_qs.aggregate(
            total=Count('id'),
            published=Count('id', filter=Q(status='published')),
            draft=Count('id', filter=Q(status='draft')),
        )
        total_model_exams = model_exam_stats['total']
        published_model_exams = model_exam_stats['published']
        draft_model_exams = model_exam_stats['draft']
        total_attempts = ExaminationAttempt.objects.filter(examination__objective_category='model').count()

        # annotate() the attempt count instead of one .count() per exam in
        # the loop below (was up to 5 extra queries, one per recent exam).
        recent_model_exams = model_exams_qs.select_related('exam').annotate(
            attempt_count=Count('attempts')
        ).order_by('-created_at')[:5]
        recent_data = []
        for me in recent_model_exams:
            recent_data.append({
                "id": me.id,
                "title": me.title,
                "exam": me.exam.name,
                "status": me.status,
                "totalQuestions": me.total_questions,
                "attempts": me.attempt_count,
                "createdAt": me.created_at.isoformat(),
            })

        payload = {
            "totalExams": total_exams,
            "activeExams": active_exams,
            "totalModelExams": total_model_exams,
            "publishedModelExams": published_model_exams,
            "draftModelExams": draft_model_exams,
            "totalAttempts": total_attempts,
            "recentExams": recent_data,
        }
        try:
            cache.set(cache_key, payload, 120)
        except Exception:
            pass
        return Response(payload)


class AdminAITutorOverviewView(APIView):
    """AI Tutor overview for admin dashboard."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.core.cache import cache
        cache_key = 'admin:ai_tutor:overview'
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)
        except Exception:
            pass

        total_sessions = Conversation.objects.count()
        today = timezone.now().date()

        # Usage trend for last 7 days - one grouped query instead of one
        # .aggregate() per day (was 7 identical-shaped queries), and
        # sessions_today is read from the same result instead of its own query.
        window_start = today - timedelta(days=6)
        daily_usage = {
            row['date']: (row['total'] or 0)
            for row in TutorUsage.objects.filter(date__gte=window_start, date__lte=today)
            .values('date').annotate(total=Sum('request_count'))
        }
        trend_data = [
            {"date": str(d), "sessions": daily_usage.get(d, 0)}
            for d in (window_start + timedelta(days=i) for i in range(7))
        ]
        sessions_today = daily_usage.get(today, 0)

        # Most used modes (subjects proxy)
        mode_counts = (
            Conversation.objects.values('mode')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        top_modes = [{"mode": m['mode'], "count": m['count']} for m in mode_counts]

        # Active students using AI tutor
        active_students = Conversation.objects.values('student').distinct().count()

        # Questions asked = messages sent by students (excludes AI responses)
        total_questions = Message.objects.filter(role='user').count()

        payload = {
            "totalSessions": total_sessions,
            "sessionsToday": sessions_today,
            "activeStudents": active_students,
            "totalQuestions": total_questions,
            "topModes": top_modes,
            "trend": trend_data,
        }
        try:
            cache.set(cache_key, payload, 120)
        except Exception:
            pass
        return Response(payload)


class AdminAITutorProviderStatusView(APIView):
    """Safe AI provider configuration status for the admin dashboard.

    Never returns the API key itself, and never makes a live call to the
    provider (that would consume quota/cost on every dashboard load).
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        import os
        configured = bool(os.environ.get('GEMINI_API_KEY', '').strip())
        return Response({
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "status": "configured" if configured else "not_configured",
        })


class AdminAITutorConversationsView(APIView):
    """Paginated, searchable list of AI Tutor conversations for admin review."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        search = request.query_params.get('search', '').strip()
        mode = request.query_params.get('mode', '').strip()
        date_from = parse_date(request.query_params.get('date_from', '') or '')
        date_to = parse_date(request.query_params.get('date_to', '') or '')
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 20)), 100)

        qs = Conversation.objects.select_related('student').annotate(
            message_count=Count('messages')
        )

        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(student__username__icontains=search) |
                Q(student__email__icontains=search) |
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search)
            )
        if mode:
            qs = qs.filter(mode=mode)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        qs = qs.order_by('-updated_at')

        total = qs.count()
        start = (page - 1) * page_size
        conversations = qs[start:start + page_size]

        data = []
        for c in conversations:
            data.append({
                "id": c.id,
                "title": c.title,
                "mode": c.mode,
                "student": {
                    "id": c.student.id,
                    "name": c.student.get_full_name() or c.student.username,
                    "email": c.student.email,
                },
                "messageCount": c.message_count,
                "createdAt": c.created_at.isoformat(),
                "updatedAt": c.updated_at.isoformat(),
            })

        return Response({
            "conversations": data,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size,
        })


class AdminAITutorConversationDetailView(APIView):
    """Full conversation transcript for admin review."""
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        try:
            conversation = Conversation.objects.select_related('student').get(pk=pk)
        except Conversation.DoesNotExist:
            return Response({"error": "Conversation not found"}, status=status.HTTP_404_NOT_FOUND)

        messages = conversation.messages.order_by('created_at')

        return Response({
            "id": conversation.id,
            "title": conversation.title,
            "mode": conversation.mode,
            "student": {
                "id": conversation.student.id,
                "name": conversation.student.get_full_name() or conversation.student.username,
                "email": conversation.student.email,
            },
            "createdAt": conversation.created_at.isoformat(),
            "updatedAt": conversation.updated_at.isoformat(),
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "createdAt": m.created_at.isoformat(),
                }
                for m in messages
            ],
        })


class AdminAITutorUsageView(APIView):
    """Real usage/token statistics, aggregated in the database."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        days = min(int(request.query_params.get('days', 30)), 90)
        today = timezone.now().date()
        start_date = today - timedelta(days=days - 1)

        daily = (
            TutorUsage.objects.filter(date__gte=start_date, date__lte=today)
            .values('date')
            .annotate(requests=Sum('request_count'), tokens=Sum('token_usage'))
            .order_by('date')
        )
        daily_by_date = {row['date']: row for row in daily}

        trend = []
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            row = daily_by_date.get(d)
            trend.append({
                "date": str(d),
                "requests": row['requests'] if row else 0,
                "tokens": row['tokens'] if row else 0,
            })

        totals = TutorUsage.objects.aggregate(
            totalRequests=Sum('request_count'),
            totalTokens=Sum('token_usage'),
        )

        top_students = (
            TutorUsage.objects.values('student__id', 'student__username', 'student__first_name', 'student__last_name')
            .annotate(requests=Sum('request_count'), tokens=Sum('token_usage'))
            .order_by('-requests')[:10]
        )
        top_students_data = [
            {
                "studentId": s['student__id'],
                "name": (f"{s['student__first_name']} {s['student__last_name']}".strip()
                         or s['student__username']),
                "requests": s['requests'] or 0,
                "tokens": s['tokens'] or 0,
            }
            for s in top_students
        ]

        return Response({
            "totalRequests": totals['totalRequests'] or 0,
            "totalTokens": totals['totalTokens'] or 0,
            "trend": trend,
            "topStudents": top_students_data,
        })


class AdminAITutorPromptsView(APIView):
    """Admin-editable AI Tutor system prompts.

    GET/PUT the exact text AITutorService.construct_system_prompt() reads
    at request time - editing here changes real AI Tutor behaviour, it is
    not a display-only settings screen.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        from core.models import AdminSettings

        settings_obj = AdminSettings.get_settings()
        templates = PromptTemplate.get_all_seeded()

        return Response({
            "basePrompt": settings_obj.ai_tutor_base_prompt,
            "modes": {
                mode: {
                    "promptText": template.prompt_text,
                    "updatedAt": template.updated_at.isoformat(),
                }
                for mode, template in templates.items()
            },
        })

    def put(self, request):
        from core.models import AdminSettings

        base_prompt = request.data.get('basePrompt')
        if base_prompt is not None:
            if not isinstance(base_prompt, str) or not base_prompt.strip():
                return Response(
                    {'error': 'basePrompt must be a non-empty string'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            settings_obj = AdminSettings.get_settings()
            settings_obj.ai_tutor_base_prompt = base_prompt
            settings_obj.updated_by = request.user
            settings_obj.save()

        modes = request.data.get('modes')
        if modes:
            valid_modes = dict(Conversation.MODE_CHOICES)
            for mode, prompt_text in modes.items():
                if mode not in valid_modes:
                    return Response(
                        {'error': f'Unknown mode: {mode}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if not isinstance(prompt_text, str) or not prompt_text.strip():
                    return Response(
                        {'error': f'modes.{mode} must be a non-empty string'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            for mode, prompt_text in modes.items():
                PromptTemplate.objects.update_or_create(
                    mode=mode,
                    defaults={'prompt_text': prompt_text, 'updated_by': request.user},
                )

        return Response({'message': 'Prompts updated successfully'})


class AdminMarketplaceOverviewView(APIView):
    """Marketplace overview for admin dashboard."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.core.cache import cache
        cache_key = 'admin:marketplace:overview'
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)
        except Exception:
            pass

        product_stats = Product.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_published=True)),
        )
        total_products = product_stats['total']
        active_products = product_stats['active']

        order_stats = PaymentSubmission.objects.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='PENDING')),
            completed=Count('id', filter=Q(status='APPROVED')),
            cancelled=Count('id', filter=Q(status='REJECTED')),
        )
        total_orders = order_stats['total']
        pending_orders = order_stats['pending']
        completed_orders = order_stats['completed']
        cancelled_orders = order_stats['cancelled']

        today = timezone.now().date()
        active_purchases = Purchase.objects.filter(status='ACTIVE')
        revenue_stats = active_purchases.aggregate(
            total=Sum('amount_paid'),
            today=Sum('amount_paid', filter=Q(created_at__date=today)),
        )
        revenue = float(revenue_stats['total'] or 0)
        revenue_today = float(revenue_stats['today'] or 0)

        # Real revenue trend for the last 7 days - one grouped query instead
        # of one .aggregate() per day (was 7 identical-shaped queries).
        window_start = today - timedelta(days=6)
        daily_totals = {
            row['day']: float(row['total'] or 0)
            for row in active_purchases
            .filter(created_at__date__gte=window_start, created_at__date__lte=today)
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(total=Sum('amount_paid'))
        }
        revenue_trend = [
            {"date": str(d), "revenue": daily_totals.get(d, 0.0)}
            for d in (window_start + timedelta(days=i) for i in range(7))
        ]

        # Real payment-method usage breakdown, from actual submissions.
        method_counts = (
            PaymentSubmission.objects.values('payment_method__display_name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        total_submissions = sum(m['count'] for m in method_counts) or 1
        payment_method_breakdown = [
            {
                "method": m['payment_method__display_name'] or 'Unknown',
                "count": m['count'],
                "percentage": round(m['count'] / total_submissions * 100, 1),
            }
            for m in method_counts
        ]

        recent_orders = PaymentSubmission.objects.select_related(
            'student', 'product'
        ).order_by('-submitted_at')[:5]

        recent_data = []
        for o in recent_orders:
            recent_data.append({
                "id": o.id,
                "product": o.product.title,
                "buyer": o.student.get_full_name() or o.student.username,
                "seller": "LoksewaAI",  # We don't have individual sellers anymore based on the models
                "price": float(o.submitted_amount),
                "status": o.status,
                "createdAt": o.submitted_at.isoformat(),
            })

        payload = {
            "totalProducts": total_products,
            "activeProducts": active_products,
            "totalOrders": total_orders,
            "pendingOrders": pending_orders,
            "completedOrders": completed_orders,
            "cancelledOrders": cancelled_orders,
            "revenue": revenue,
            "revenueToday": revenue_today,
            "revenueTrend": revenue_trend,
            "paymentMethodBreakdown": payment_method_breakdown,
            "recentOrders": recent_data,
        }
        try:
            cache.set(cache_key, payload, 120)
        except Exception:
            pass
        return Response(payload)


# ============================================================
# EVALUATOR MANAGEMENT VIEWS
# ============================================================

def _evaluator_stats(user):
    """Compute evaluation statistics for a single evaluator user."""
    from exams.models import Evaluation, SubjectiveAnswer
    from django.db.models import Avg

    total_evals = Evaluation.objects.filter(evaluator=user).count()
    avg_marks = Evaluation.objects.filter(evaluator=user).aggregate(
        avg=Avg('marks_obtained')
    )['avg']

    # Derive subjects from evaluated answers
    subject_names = list(
        Evaluation.objects.filter(evaluator=user)
        .select_related('answer__question__topic__unit__subject')
        .values_list('answer__question__topic__unit__subject__name', flat=True)
        .distinct()
    )

    # Pending = submitted answers not yet evaluated
    pending = SubjectiveAnswer.objects.filter(
        status='submitted'
    ).exclude(
        id__in=Evaluation.objects.values_list('answer_id', flat=True)
    ).count()

    # Recent evaluations by this evaluator
    recent_evals = (
        Evaluation.objects.filter(evaluator=user)
        .select_related('answer__question', 'answer__attempt__student')
        .order_by('-evaluated_at')[:5]
    )
    recent = []
    for e in recent_evals:
        q_text = e.answer.question.text[:80] if e.answer.question else ''
        student = e.answer.attempt.student
        recent.append({
            "id": e.id,
            "student": student.get_full_name() or student.username,
            "question": q_text,
            "marks": float(e.marks_obtained),
            "evaluatedAt": e.evaluated_at.isoformat(),
        })

    return {
        "totalEvaluations": total_evals,
        "pendingEvaluations": pending,
        "completedEvaluations": total_evals,
        "avgScore": round(float(avg_marks), 2) if avg_marks else None,
        "assignedSubjects": subject_names,
        "recentEvaluations": recent,
    }


class AdminEvaluatorListView(APIView):
    """Paginated list of evaluators with per-evaluator stats."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        search = request.query_params.get('search', '')
        status_filter = request.query_params.get('status', '')  # 'active' | 'inactive'
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        qs = User.objects.filter(role='teacher').order_by('-date_joined')

        if search:
            qs = qs.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        if status_filter == 'active':
            qs = qs.filter(is_active=True)
        elif status_filter == 'inactive':
            qs = qs.filter(is_active=False)

        total = qs.count()
        start = (page - 1) * page_size
        evaluators = qs[start:start + page_size]

        from exams.models import Evaluation, SubjectiveAnswer
        from django.db.models import Avg

        data = []
        for u in evaluators:
            total_evals = Evaluation.objects.filter(evaluator=u).count()
            avg_marks = Evaluation.objects.filter(evaluator=u).aggregate(
                avg=Avg('marks_obtained')
            )['avg']
            subjects = list(
                Evaluation.objects.filter(evaluator=u)
                .select_related('answer__question__topic__unit__subject')
                .values_list('answer__question__topic__unit__subject__name', flat=True)
                .distinct()
            )
            data.append({
                "id": u.id,
                "name": u.get_full_name() or u.username,
                "username": u.username,
                "email": u.email,
                "isActive": u.is_active,
                "dateJoined": u.date_joined.isoformat(),
                "avatar": u.avatar,
                "totalEvaluations": total_evals,
                "completedEvaluations": total_evals,
                "avgScore": round(float(avg_marks), 2) if avg_marks else None,
                "assignedSubjects": subjects,
            })

        return Response({
            "evaluators": data,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size,
        })


class AdminEvaluatorDetailView(APIView):
    """Full evaluator profile with stats and recent activity."""
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        try:
            u = User.objects.get(pk=pk, role='teacher')
        except User.DoesNotExist:
            return Response({'detail': 'Evaluator not found.'}, status=404)

        stats = _evaluator_stats(u)
        return Response({
            "id": u.id,
            "name": u.get_full_name() or u.username,
            "username": u.username,
            "email": u.email,
            "firstName": u.first_name,
            "lastName": u.last_name,
            "isActive": u.is_active,
            "dateJoined": u.date_joined.isoformat(),
            "avatar": u.avatar,
            **stats,
        })


class AdminEvaluatorCreateView(APIView):
    """Create a new evaluator user."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        first_name = request.data.get('firstName', '').strip()
        last_name = request.data.get('lastName', '').strip()
        email = request.data.get('email', '').strip()
        password = request.data.get('password', '').strip()

        errors = {}
        if not first_name:
            errors['firstName'] = 'First name is required.'
        if not email:
            errors['email'] = 'Email is required.'
        if not password:
            errors['password'] = 'Password is required.'
        else:
            try:
                django_validate_password(password)
            except DjangoValidationError as e:
                errors['password'] = ' '.join(e.messages)
        if User.objects.filter(email=email).exists():
            errors['email'] = 'A user with this email already exists.'
        if errors:
            return Response({'errors': errors}, status=400)

        username = email.split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role='teacher',
            is_active=True,
        )

        return Response({
            "id": user.id,
            "name": user.get_full_name() or user.username,
            "email": user.email,
            "isActive": user.is_active,
            "dateJoined": user.date_joined.isoformat(),
        }, status=201)


class AdminEvaluatorUpdateView(APIView):
    """Edit evaluator profile or toggle active status."""
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        try:
            u = User.objects.get(pk=pk, role='teacher')
        except User.DoesNotExist:
            return Response({'detail': 'Evaluator not found.'}, status=404)

        first_name = request.data.get('firstName')
        last_name = request.data.get('lastName')
        email = request.data.get('email')
        is_active = request.data.get('isActive')

        errors = {}
        if email is not None:
            if not email.strip():
                errors['email'] = 'Email cannot be empty.'
            elif User.objects.filter(email=email).exclude(pk=pk).exists():
                errors['email'] = 'Another user already has this email.'

        if errors:
            return Response({'errors': errors}, status=400)

        if first_name is not None:
            u.first_name = first_name
        if last_name is not None:
            u.last_name = last_name
        if email is not None:
            u.email = email
        if is_active is not None:
            u.is_active = bool(is_active)

        u.save()

        return Response({
            "id": u.id,
            "name": u.get_full_name() or u.username,
            "email": u.email,
            "firstName": u.first_name,
            "lastName": u.last_name,
            "isActive": u.is_active,
        })


class AdminEvaluatorsSubjectsView(APIView):
    """List all subjects available for the evaluator subject filter."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from exams.models import Subject
        subjects = Subject.objects.select_related('exam').all().order_by('name')
        data = [{"id": s.id, "name": s.name, "exam": s.exam.name} for s in subjects]
        return Response(data)


class AdminEvaluationAssignmentsView(APIView):
    """Paginated list of all subjective answers with evaluation status."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from exams.models import SubjectiveAnswer

        status_filter = request.query_params.get('status', '')  # 'submitted' | 'evaluated'
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        qs = SubjectiveAnswer.objects.select_related(
            'attempt__student',
            'question__topic__chapter__subject',
        ).order_by('-submitted_at')

        if status_filter:
            qs = qs.filter(status=status_filter)
        else:
            # Exclude drafts by default
            qs = qs.exclude(status='draft')

        total = qs.count()
        start = (page - 1) * page_size
        answers = qs[start:start + page_size]

        data = []
        for a in answers:
            student = a.attempt.student
            subject = None
            try:
                subject = a.question.topic.chapter.subject.name
            except Exception:
                pass

            evaluator_name = None
            try:
                evaluator_name = (
                    a.evaluation.evaluator.get_full_name()
                    or a.evaluation.evaluator.username
                ) if a.evaluation.evaluator else None
            except Exception:
                pass

            data.append({
                "id": a.id,
                "student": student.get_full_name() or student.username,
                "studentEmail": student.email,
                "subject": subject or "—",
                "question": a.question.text[:100] if a.question else "—",
                "submittedAt": a.submitted_at.isoformat() if a.submitted_at else None,
                "status": a.status,
                "evaluator": evaluator_name,
                "wordCount": a.word_count,
            })

        return Response({
            "assignments": data,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size,
        })


# ============================================================
# ADMIN COURSE APPLICATION MANAGEMENT
# ============================================================

class AdminCourseApplicationView(APIView):
    """
    GET /api/admin/course-applications/

    Returns all course applications with full enrollment/payment context.
    Admin can see: student, applied course, payment status, enrollment status.

    Query params:
      status  = pending | approved | rejected | cancelled
      page    = int (default 1)
      per_page = int (default 20)
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        from courses.models import CourseApplication, Enrollment
        from subscriptions.models import SubscriptionPayment

        status_filter = request.query_params.get('status')
        page = int(request.query_params.get('page', 1))
        per_page = int(request.query_params.get('per_page', 20))

        qs = CourseApplication.objects.select_related(
            'student', 'course', 'subscription_payment', 'subscription_payment__plan',
            'marketplace_payment', 'marketplace_payment__product',
            'reviewed_by'
        ).order_by('-applied_at')

        if status_filter:
            qs = qs.filter(status=status_filter)

        total = qs.count()
        start = (page - 1) * per_page
        applications = qs[start:start + per_page]

        data = []
        for app in applications:
            # Enrollment status for this student+course
            enrollment = Enrollment.objects.filter(
                student=app.student, course=app.course
            ).first()

            payment = app.subscription_payment

            data.append({
                'id': app.id,
                'student': {
                    'id': app.student.id,
                    'name': app.student.get_full_name() or app.student.username,
                    'username': app.student.username,
                    'email': app.student.email,
                },
                'course': {
                    'id': app.course.id,
                    'title': app.course.title,
                },
                'application_status': app.status,
                'applied_at': app.applied_at,
                'reviewed_at': app.reviewed_at,
                'reviewed_by': app.reviewed_by.get_full_name() if app.reviewed_by else None,
                'note': app.note,
                'payment': {
                    'id': app.subscription_payment.id,
                    'status': app.subscription_payment.status,
                    'amount': str(app.subscription_payment.amount),
                    'plan_name': app.subscription_payment.plan.name,
                    'submitted_at': app.subscription_payment.submitted_at,
                    'type': 'subscription'
                } if app.subscription_payment else ({
                    'id': app.marketplace_payment.id,
                    'status': app.marketplace_payment.status,
                    'amount': str(app.marketplace_payment.submitted_amount),
                    'plan_name': app.marketplace_payment.product.title,
                    'submitted_at': app.marketplace_payment.submitted_at,
                    'type': 'marketplace'
                } if app.marketplace_payment else None),
                'enrollment': {
                    'id': enrollment.id,
                    'status': enrollment.status,
                    'enrolled_at': enrollment.enrolled_at,
                    'expires_at': enrollment.expires_at,
                } if enrollment else None,
            })

        return Response({
            'results': data,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page,
        })

    def post(self, request):
        """
        POST /api/admin/course-applications/
        Manually enroll a student in a course (admin action — no payment required).
        Body: { student_id, course_id, note }
        """
        from courses.models import CourseApplication, Enrollment, Course
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()

        student_id = request.data.get('student_id')
        course_id = request.data.get('course_id')
        note = request.data.get('note', 'Manually enrolled by admin.')

        if not student_id or not course_id:
            return Response({'error': 'student_id and course_id are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = UserModel.objects.get(id=student_id, role='student')
        except UserModel.DoesNotExist:
            return Response({'error': 'Student not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)

        from django.utils import timezone as tz
        now = tz.now()

        app, _ = CourseApplication.objects.update_or_create(
            student=student,
            course=course,
            defaults={
                'status': 'approved',
                'note': note,
                'reviewed_at': now,
                'reviewed_by': request.user,
            }
        )

        enrollment, created = Enrollment.objects.get_or_create(
            student=student,
            course=course,
            defaults={'status': 'active'}
        )
        if not created:
            enrollment.status = 'active'
            enrollment.save(update_fields=['status'])

        return Response({
            'application_id': app.id,
            'enrollment_id': enrollment.id,
            'created': created,
            'message': f'{student.username} enrolled in {course.title}.',
        }, status=status.HTTP_201_CREATED)


class AdminCourseApplicationDetailView(APIView):
    """
    PATCH /api/admin/course-applications/<id>/
    Body: { status: 'approved' | 'rejected', note?: str }

    Approves or rejects a single CourseApplication directly. This covers
    applications that have no linked SubscriptionPayment (e.g. free
    courses applied to via POST /api/courses/apply/) — payment-linked
    applications are still approved/rejected through
    SubscriptionPaymentViewSet.approve/reject, which also handles the
    subscription + invoice side and keeps this record in sync.
    """
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        from django.db import transaction
        from courses.models import CourseApplication, Enrollment

        try:
            app = CourseApplication.objects.select_related('student', 'course').get(pk=pk)
        except CourseApplication.DoesNotExist:
            return Response({'error': 'Application not found.'}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        if new_status not in ('approved', 'rejected'):
            return Response(
                {'error': "status must be 'approved' or 'rejected'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if app.status not in ('pending',):
            return Response(
                {'error': f'Application is already {app.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        note = request.data.get('note', '')
        now = timezone.now()

        with transaction.atomic():
            app.status = new_status
            app.note = note
            app.reviewed_at = now
            app.reviewed_by = request.user
            app.save(update_fields=['status', 'note', 'reviewed_at', 'reviewed_by'])

            if new_status == 'approved':
                enrollment, created = Enrollment.objects.get_or_create(
                    student=app.student,
                    course=app.course,
                    defaults={'status': 'active'},
                )
                if not created and enrollment.status != 'active':
                    enrollment.status = 'active'
                    enrollment.save(update_fields=['status'])

        return Response({
            'application_id': app.id,
            'status': app.status,
            'reviewed_at': app.reviewed_at,
        })


# ============================================================
# EVALUATIONS MANAGEMENT VIEW
# ============================================================

def _evaluation_queryset():
    """Shared base queryset for the admin evaluation list/detail endpoints.
    select_related covers every field the serialized responses touch (the
    student, the question, and - via the evaluation reverse OneToOne - the
    evaluator) so paginating a page of results never issues a per-row query,
    and pulls in the subject/exam chain each answer's attempt belongs to
    (practice_set or the legacy model_exam) for search/filter/display."""
    from exams.models import SubjectiveAnswer

    return SubjectiveAnswer.objects.select_related(
        'attempt__student',
        'question__topic',
        'evaluation__evaluator',
        'attempt__practice_set__exam',
        'attempt__practice_set__subject',
        'attempt__model_exam__exam',
    )


def _exam_subject_context(answer):
    """The exam/subject an answer belongs to - practice_set carries both,
    the legacy model_exam only carries the exam."""
    attempt = answer.attempt
    if attempt.practice_set:
        return {
            'exam': attempt.practice_set.exam.name if attempt.practice_set.exam else None,
            'subject': attempt.practice_set.subject.name if attempt.practice_set.subject else None,
            'paper': attempt.practice_set.title,
        }
    if attempt.model_exam:
        return {
            'exam': attempt.model_exam.exam.name if attempt.model_exam.exam else None,
            'subject': None,
            'paper': attempt.model_exam.title,
        }
    return {'exam': None, 'subject': None, 'paper': None}


class AdminEvaluationsView(APIView):
    """List submissions needing evaluation (subjective answers) with
    pagination and filtering. Any authenticated evaluator (teacher, admin,
    or super-admin) can access this - matches the same role set the rest of
    the evaluation architecture (TeacherEvaluationViewSet) already grants
    via IsEvaluatorUser, not admin-only."""
    permission_classes = [IsEvaluatorUser]

    def get(self, request):
        status_filter = request.query_params.get('status', 'submitted')  # 'submitted', 'under-review', 'evaluated', 'returned', 'all'
        search = request.query_params.get('search', '')
        exam_id = request.query_params.get('exam', '')
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))

        qs = _evaluation_queryset().order_by('-submitted_at')

        if status_filter != 'all':
            qs = qs.filter(status=status_filter)

        if search:
            qs = qs.filter(
                Q(attempt__student__username__icontains=search) |
                Q(attempt__student__email__icontains=search) |
                Q(attempt__student__first_name__icontains=search) |
                Q(attempt__student__last_name__icontains=search) |
                Q(question__text__icontains=search)
            )

        if exam_id:
            qs = qs.filter(
                Q(attempt__practice_set__exam_id=exam_id) | Q(attempt__model_exam__exam_id=exam_id)
            )

        total = qs.count()
        start = (page - 1) * page_size
        answers = list(qs[start:start + page_size])

        data = []
        for answer in answers:
            # select_related('evaluation__evaluator') above means this
            # never issues a query either way.
            evaluation = answer.evaluation if hasattr(answer, 'evaluation') else None

            context = _exam_subject_context(answer)
            data.append({
                "id": answer.id,
                "student": answer.attempt.student.get_full_name() or answer.attempt.student.username,
                "studentId": answer.attempt.student.id,
                "email": answer.attempt.student.email,
                "question": answer.question.text[:100] if answer.question else '',
                "questionId": answer.question.id if answer.question else None,
                "marks": float(answer.question.marks) if answer.question else 0,
                "status": answer.status,
                "submittedAt": answer.submitted_at.isoformat() if answer.submitted_at else None,
                "wordCount": answer.word_count,
                "evaluator": (evaluation.evaluator.get_full_name() or evaluation.evaluator.username) if evaluation and evaluation.evaluator else None,
                "marksObtained": float(evaluation.marks_obtained) if evaluation else None,
                "evaluatedAt": evaluation.evaluated_at.isoformat() if evaluation else None,
                "exam": context['exam'],
                "subject": context['subject'],
                "paper": context['paper'],
            })

        return Response({
            "evaluations": data,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size,
        })


class AdminEvaluationDetailView(APIView):
    """Full detail for one subjective answer, plus the save/finalize action
    an evaluator uses to grade it. Reuses the same SubjectiveAnswer/
    Evaluation/Annotation models TeacherEvaluationViewSet (exams/views.py)
    already grades against - this is a separate admin-namespaced view layer
    over the same data, matching how AdminQuestionViewSet/TeacherQuestionViewSet
    both already operate on the same Question model."""
    permission_classes = [IsEvaluatorUser]

    def _get_answer(self, pk):
        from exams.models import SubjectiveAnswer
        try:
            return _evaluation_queryset().get(pk=pk)
        except SubjectiveAnswer.DoesNotExist:
            return None

    def _serialize(self, answer):
        from exams.serializers import SubjectiveQuestionWithModelAnswerSerializer, EvaluationSerializer

        evaluation = answer.evaluation if hasattr(answer, 'evaluation') else None

        context = _exam_subject_context(answer)
        return {
            "id": answer.id,
            "student": {
                "id": answer.attempt.student.id,
                "name": answer.attempt.student.get_full_name() or answer.attempt.student.username,
                "username": answer.attempt.student.username,
                "email": answer.attempt.student.email,
            },
            "exam": context['exam'],
            "subject": context['subject'],
            "paper": context['paper'],
            "attemptDate": answer.attempt.submitted_at.isoformat() if answer.attempt.submitted_at else None,
            "question": SubjectiveQuestionWithModelAnswerSerializer(answer.question).data if answer.question else None,
            "answerText": answer.answer_text,
            "fileUrl": answer.file_url,
            "status": answer.status,
            "submittedAt": answer.submitted_at.isoformat() if answer.submitted_at else None,
            "wordCount": answer.word_count,
            "evaluation": EvaluationSerializer(evaluation).data if evaluation else None,
        }

    def get(self, request, pk):
        answer = self._get_answer(pk)
        if answer is None:
            return Response({"detail": "Submission not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self._serialize(answer))

    def patch(self, request, pk):
        from exams.models import Evaluation

        answer = self._get_answer(pk)
        if answer is None:
            return Response({"detail": "Submission not found."}, status=status.HTTP_404_NOT_FOUND)
        if answer.question is None:
            return Response({"detail": "This submission has no linked question to grade against."}, status=status.HTTP_400_BAD_REQUEST)

        raw_marks = request.data.get('marks_obtained', None)
        if raw_marks is None:
            return Response({"marks_obtained": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            marks = float(raw_marks)
        except (TypeError, ValueError):
            return Response({"marks_obtained": ["Must be a number."]}, status=status.HTTP_400_BAD_REQUEST)

        max_marks = float(answer.question.marks)
        if marks < 0:
            return Response({"marks_obtained": ["Marks cannot be negative."]}, status=status.HTTP_400_BAD_REQUEST)
        if marks > max_marks:
            return Response({"marks_obtained": [f"Marks cannot exceed the maximum of {max_marks}."]}, status=status.HTTP_400_BAD_REQUEST)

        feedback = request.data.get('feedback', '')
        finalize = bool(request.data.get('finalize', False))

        with transaction.atomic():
            evaluation, _created = Evaluation.objects.update_or_create(
                answer=answer,
                defaults={
                    'evaluator': request.user,
                    'marks_obtained': marks,
                    'feedback': feedback,
                },
            )
            # 'under-review' for a saved-but-not-finalized evaluation,
            # 'evaluated' once the evaluator finalizes it - both are
            # existing SubjectiveAnswer.STATUS_CHOICES values. Re-finalizing
            # an already-evaluated answer is allowed, matching
            # TeacherEvaluationViewSet.evaluate()'s existing update_or_create
            # behaviour (the backend already supports re-evaluation, so this
            # does not block it).
            answer.status = 'evaluated' if finalize else 'under-review'
            answer.save(update_fields=['status'])

            if finalize:
                from core.notification_service import NotificationService
                transaction.on_commit(lambda: NotificationService.notify_subjective_evaluated(evaluation))

        answer.refresh_from_db()
        return Response(self._serialize(answer))


# ============================================================
# STUDY MATERIALS MANAGEMENT VIEW
# ============================================================

class AdminStudyMaterialsView(APIView):
    """List study materials with pagination and filtering."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from notes.models import StudyMaterial

        status_filter = request.query_params.get('status', 'all')  # 'draft', 'pending_review', 'published', 'all'
        material_type = request.query_params.get('type', '')
        content_category = request.query_params.get('content_category', '')
        note_type = request.query_params.get('note_type', '')
        exam_id = request.query_params.get('exam') or request.query_params.get('exam_id')
        level_id = request.query_params.get('level_id')
        category_id = request.query_params.get('category_id')
        subject_id = request.query_params.get('subject') or request.query_params.get('subject_id')
        chapter_id = request.query_params.get('chapter') or request.query_params.get('chapter_id')
        topic_id = request.query_params.get('topic') or request.query_params.get('topic_id')
        search = request.query_params.get('search', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))

        # Admin-controlled order first (Syllabus Builder reordering), newest
        # first as a tiebreak among equal/unset orders.
        qs = StudyMaterial.objects.select_related(
            'teacher', 'subject', 'chapter', 'topic', 'exam', 'exam__parent', 'exam__category', 'course'
        ).order_by('order', '-created_at')

        if status_filter and status_filter != 'all':
            qs = qs.filter(status=status_filter)

        if content_category:
            qs = qs.filter(content_category=content_category)

        if note_type:
            qs = qs.filter(note_type=note_type)

        if exam_id:
            qs = qs.filter(exam_id=exam_id)
        elif level_id:
            qs = qs.filter(exam__parent_id=level_id)
        elif category_id:
            qs = qs.filter(exam__category_id=category_id)

        if subject_id:
            qs = qs.filter(subject_id=subject_id)

        if chapter_id:
            qs = qs.filter(chapter_id=chapter_id)

        if topic_id:
            qs = qs.filter(topic_id=topic_id)

        if material_type:
            qs = qs.filter(material_type=material_type)

        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(teacher__username__icontains=search) |
                Q(subject__name__icontains=search) |
                Q(exam__name__icontains=search)
            )

        total = qs.count()
        start = (page - 1) * page_size
        materials = qs[start:start + page_size]

        import os
        data = []
        for material in materials:
            file_url = None
            file_name = None
            if material.file:
                try:
                    file_url = request.build_absolute_uri(material.file.url)
                    file_name = os.path.basename(material.file.name)
                except Exception:
                    file_url = material.file.url if hasattr(material.file, 'url') else None
                    file_name = str(material.file)

            data.append({
                "id": material.id,
                "title": material.title,
                "slug": material.slug,
                "description": material.description or '',
                "content": material.content or '',
                "teacher": material.teacher.get_full_name() or material.teacher.username if material.teacher else 'Unknown',
                "examId": material.exam_id,
                "examName": material.exam.name if material.exam else 'N/A',
                "levelId": material.exam.parent_id if material.exam and material.exam.parent else None,
                "levelName": material.exam.parent.name if material.exam and material.exam.parent else None,
                "categoryId": material.exam.category_id if material.exam else None,
                "categoryName": material.exam.category.name if material.exam and material.exam.category else None,
                "courseId": material.course_id,
                "courseTitle": material.course.title if material.course else None,
                "subjectId": material.subject_id,
                "subjectName": material.subject.name if material.subject else None,
                "chapterId": material.chapter_id,
                "chapterName": material.chapter.title if material.chapter else None,
                "topicId": material.topic_id,
                "topicName": material.topic.name if material.topic else None,
                "contentCategory": material.content_category,
                "noteType": material.note_type,
                "materialType": material.material_type,
                "difficulty": material.difficulty,
                "status": material.status,
                "accessType": material.access_type,
                "fileUrl": file_url,
                "fileName": file_name,
                "externalUrl": material.external_url,
                "estimatedReadingTime": material.estimated_reading_time,
                "availableToAiTutor": material.available_to_ai_tutor,
                "order": material.order,
                "createdAt": material.created_at.isoformat(),
                "updatedAt": material.updated_at.isoformat(),
            })

        return Response({
            "materials": data,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size if page_size > 0 else 1,
        })

    def post(self, request):
        """Create a study material.
        Accepts JSON or multipart (when an actual file is attached).
        """
        from notes.models import StudyMaterial
        from exams.models import Exam, Subject, Chapter, Topic
        from courses.models import Course

        title = (request.data.get('title') or '').strip()
        exam_id = request.data.get('exam') or request.data.get('exam_id')

        if not title:
            return Response({"error": "Title is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not exam_id:
            return Response({"error": "Exam/Preparation is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            exam = Exam.objects.get(pk=exam_id)
        except (Exam.DoesNotExist, ValueError, TypeError):
            return Response({"error": "That exam does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        content_category = (request.data.get('content_category') or 'subjective_topicwise').strip().lower()
        if content_category not in dict(StudyMaterial.CONTENT_CATEGORY_CHOICES):
            return Response({"error": f"Unsupported content_category: {content_category}"}, status=status.HTTP_400_BAD_REQUEST)

        note_type = (request.data.get('note_type') or 'standard').strip().lower()
        if note_type not in dict(StudyMaterial.NOTE_TYPE_CHOICES):
            return Response({"error": f"Unsupported note_type: {note_type}"}, status=status.HTTP_400_BAD_REQUEST)

        subject = None
        subject_id = request.data.get('subject') or request.data.get('subject_id')
        if subject_id:
            try:
                subject = Subject.objects.get(pk=subject_id)
            except (Subject.DoesNotExist, ValueError, TypeError):
                return Response({"error": "That subject does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        chapter = None
        chapter_id = request.data.get('chapter') or request.data.get('chapter_id')
        if chapter_id:
            try:
                chapter = Chapter.objects.get(pk=chapter_id)
            except (Chapter.DoesNotExist, ValueError, TypeError):
                return Response({"error": "That chapter does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        topic = None
        topic_id = request.data.get('topic') or request.data.get('topic_id')
        if topic_id:
            try:
                topic = Topic.objects.get(pk=topic_id)
            except (Topic.DoesNotExist, ValueError, TypeError):
                return Response({"error": "That topic does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate parent hierarchy integrity:
        if topic and chapter and topic.chapter_id != chapter.id:
            return Response(
                {"error": f"Topic '{topic.name}' does not belong to chapter '{chapter.title}'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if topic and not chapter:
            chapter = topic.chapter

        if chapter and subject and chapter.subject_id != subject.id:
            return Response(
                {"error": f"Chapter '{chapter.title}' does not belong to subject '{subject.name}'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if chapter and not subject:
            subject = chapter.subject

        if subject and subject.paper and subject.paper.exam_id != exam.id:
            return Response(
                {"error": f"Subject '{subject.name}' does not belong to preparation '{exam.name}'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        course = None
        course_id = request.data.get('course') or request.data.get('course_id')
        if course_id:
            try:
                course = Course.objects.get(pk=course_id)
            except (Course.DoesNotExist, ValueError, TypeError):
                pass
        if not course:
            course = Course.objects.filter(exam=exam).first()

        material_type = (request.data.get('material_type') or 'pdf').strip().lower()
        if material_type not in dict(StudyMaterial.MATERIAL_TYPES):
            material_type = 'pdf'

        difficulty = (request.data.get('difficulty') or 'beginner').strip().lower()
        if difficulty not in dict(StudyMaterial.DIFFICULTY_CHOICES):
            difficulty = 'beginner'

        access_type = (request.data.get('access_type') or 'free').strip().lower()
        if access_type not in dict(StudyMaterial.ACCESS_TYPES):
            access_type = 'free'

        material_status = (request.data.get('status') or 'published').strip().lower()
        if material_status not in dict(StudyMaterial.STATUS_CHOICES):
            material_status = 'published'

        try:
            order = int(request.data.get('order') or 0)
        except (TypeError, ValueError):
            order = 0

        upload = request.FILES.get('file')
        content = request.data.get('content') or ''
        external_url = (request.data.get('external_url') or '').strip()

        if not upload and not external_url and not content.strip():
            return Response(
                {"error": "Please attach a PDF file or provide content."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if upload:
            material_type = 'pdf'

        material = StudyMaterial.objects.create(
            title=title,
            teacher=request.user,
            exam=exam,
            course=course,
            subject=subject,
            chapter=chapter,
            topic=topic,
            content_category=content_category,
            note_type=note_type,
            description=request.data.get('description') or '',
            content=content,
            material_type=material_type,
            difficulty=difficulty,
            access_type=access_type,
            status=material_status,
            external_url=external_url or None,
            estimated_reading_time=int(request.data.get('estimated_reading_time') or 10),
            order=order,
        )
        if upload:
            material.file = upload
            material.save(update_fields=['file'])

        AuditLog.objects.create(
            actor=request.user, action='CREATE_STUDY_MATERIAL',
            entity_type='StudyMaterial', entity_id=str(material.id),
            details={"title": material.title, "status": material.status, "category": content_category},
        )

        file_url = request.build_absolute_uri(material.file.url) if material.file else None

        return Response({
            "id": material.id,
            "title": material.title,
            "slug": material.slug,
            "status": material.status,
            "contentCategory": material.content_category,
            "noteType": material.note_type,
            "materialType": material.material_type,
            "examId": exam.id,
            "examName": exam.name,
            "subjectId": subject.id if subject else None,
            "subjectName": subject.name if subject else None,
            "chapterId": chapter.id if chapter else None,
            "chapterName": chapter.title if chapter else None,
            "topicId": topic.id if topic else None,
            "topicName": topic.name if topic else None,
            "fileUrl": file_url,
            "order": material.order,
        }, status=status.HTTP_201_CREATED)


class AdminStudyMaterialDetailView(APIView):
    """Retrieve, update or delete a single study material."""
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        from notes.models import StudyMaterial
        return StudyMaterial.objects.select_related(
            'teacher', 'subject', 'chapter', 'topic', 'exam', 'exam__parent', 'exam__category', 'course'
        ).filter(pk=pk).first()

    def get(self, request, pk):
        material = self._get(pk)
        if not material:
            return Response({"error": "Study material not found."}, status=status.HTTP_404_NOT_FOUND)

        import os
        file_url = None
        file_name = None
        if material.file:
            try:
                file_url = request.build_absolute_uri(material.file.url)
                file_name = os.path.basename(material.file.name)
            except Exception:
                file_url = material.file.url if hasattr(material.file, 'url') else None
                file_name = str(material.file)

        return Response({
            "id": material.id,
            "title": material.title,
            "slug": material.slug,
            "description": material.description,
            "content": material.content,
            "teacher": (material.teacher.get_full_name() or material.teacher.username) if material.teacher else None,
            "exam": material.exam.name if material.exam else None,
            "examId": material.exam_id,
            "levelId": material.exam.parent_id if material.exam and material.exam.parent else None,
            "levelName": material.exam.parent.name if material.exam and material.exam.parent else None,
            "categoryId": material.exam.category_id if material.exam else None,
            "categoryName": material.exam.category.name if material.exam and material.exam.category else None,
            "subject": material.subject.name if material.subject else None,
            "subjectId": material.subject_id,
            "chapter": material.chapter.title if material.chapter else None,
            "chapterId": material.chapter_id,
            "topic": material.topic.name if material.topic else None,
            "topicId": material.topic_id,
            "courseId": material.course_id,
            "courseTitle": material.course.title if material.course else None,
            "contentCategory": material.content_category,
            "noteType": material.note_type,
            "materialType": material.material_type,
            "difficulty": material.difficulty,
            "accessType": material.access_type,
            "status": material.status,
            "reviewNote": material.review_note,
            "externalUrl": material.external_url,
            "fileUrl": file_url,
            "fileName": file_name,
            "estimatedReadingTime": material.estimated_reading_time,
            "availableToAiTutor": material.available_to_ai_tutor,
            "order": material.order,
            "createdAt": material.created_at.isoformat(),
            "updatedAt": material.updated_at.isoformat(),
        })

    def patch(self, request, pk):
        from notes.models import StudyMaterial
        from exams.models import Subject, Chapter, Topic

        material = self._get(pk)
        if not material:
            return Response({"error": "Study material not found."}, status=status.HTTP_404_NOT_FOUND)

        simple_fields = ['title', 'description', 'content', 'review_note']
        for field in simple_fields:
            if field in request.data:
                setattr(material, field, request.data[field] or '')

        if 'content_category' in request.data:
            cat = str(request.data['content_category']).strip().lower()
            if cat in dict(StudyMaterial.CONTENT_CATEGORY_CHOICES):
                material.content_category = cat

        if 'note_type' in request.data:
            nt = str(request.data['note_type']).strip().lower()
            if nt in dict(StudyMaterial.NOTE_TYPE_CHOICES):
                material.note_type = nt

        choice_fields = {
            'material_type': StudyMaterial.MATERIAL_TYPES,
            'difficulty': StudyMaterial.DIFFICULTY_CHOICES,
            'access_type': StudyMaterial.ACCESS_TYPES,
            'status': StudyMaterial.STATUS_CHOICES,
        }
        for field, choices in choice_fields.items():
            if field in request.data:
                value = str(request.data[field]).strip().lower()
                if value in dict(choices):
                    setattr(material, field, value)

        if 'subject' in request.data or 'subject_id' in request.data:
            sid = request.data.get('subject') if 'subject' in request.data else request.data.get('subject_id')
            if sid:
                material.subject = Subject.objects.filter(pk=sid).first()
            else:
                material.subject = None

        if 'chapter' in request.data or 'chapter_id' in request.data:
            cid = request.data.get('chapter') if 'chapter' in request.data else request.data.get('chapter_id')
            if cid:
                material.chapter = Chapter.objects.filter(pk=cid).first()
            else:
                material.chapter = None

        if 'topic' in request.data or 'topic_id' in request.data:
            tid = request.data.get('topic') if 'topic' in request.data else request.data.get('topic_id')
            if tid:
                material.topic = Topic.objects.filter(pk=tid).first()
            else:
                material.topic = None

        # Validate parent hierarchy integrity:
        if material.topic and material.chapter and material.topic.chapter_id != material.chapter.id:
            return Response(
                {"error": f"Topic '{material.topic.name}' does not belong to chapter '{material.chapter.title}'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if material.topic and not material.chapter:
            material.chapter = material.topic.chapter

        if material.chapter and material.subject and material.chapter.subject_id != material.subject.id:
            return Response(
                {"error": f"Chapter '{material.chapter.title}' does not belong to subject '{material.subject.name}'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if material.chapter and not material.subject:
            material.subject = material.chapter.subject

        if material.subject and material.subject.paper and material.exam and material.subject.paper.exam_id != material.exam.id:
            return Response(
                {"error": f"Subject '{material.subject.name}' does not belong to preparation '{material.exam.name}'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if 'estimated_reading_time' in request.data:
            try:
                material.estimated_reading_time = int(request.data['estimated_reading_time'])
            except (TypeError, ValueError):
                pass

        if 'external_url' in request.data:
            material.external_url = (request.data['external_url'] or '').strip() or None

        if 'order' in request.data:
            try:
                material.order = int(request.data['order'])
            except (TypeError, ValueError):
                pass

        if request.FILES.get('file'):
            material.file = request.FILES['file']
            material.material_type = 'pdf'

        if 'available_to_ai_tutor' in request.data:
            value = request.data['available_to_ai_tutor']
            if isinstance(value, bool):
                material.available_to_ai_tutor = value

        material.save()

        AuditLog.objects.create(
            actor=request.user, action='UPDATE_STUDY_MATERIAL',
            entity_type='StudyMaterial', entity_id=str(material.id),
            details={"title": material.title, "status": material.status},
        )
        file_url = request.build_absolute_uri(material.file.url) if material.file else None
        return Response({
            "success": True,
            "id": material.id,
            "title": material.title,
            "status": material.status,
            "fileUrl": file_url,
            "order": material.order,
        })

    def delete(self, request, pk):
        material = self._get(pk)
        if not material:
            return Response({"error": "Study material not found."}, status=status.HTTP_404_NOT_FOUND)

        from administration.safe_delete_service import SafeDeleteService
        reason = request.data.get('reason', '') if isinstance(request.data, dict) else ''
        trash_item = SafeDeleteService.soft_delete(material, request.user, reason=reason)
        return Response({
            'success': True,
            'message': f"Study material '{trash_item.title}' has been moved to Trash.",
            'trash_item_id': trash_item.id,
        }, status=status.HTTP_200_OK)


class AdminStudyMaterialsHierarchyView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.db.models import Count, Q
        from exams.models import ExamCategory, Exam
        from notes.models import StudyMaterial
        from courses.models import Course

        categories = ExamCategory.objects.filter(is_active=True).order_by('order', 'id')

        all_exams = Exam.objects.filter(category__in=categories, is_active=True)
        exam_ids = all_exams.values_list('id', flat=True)

        counts = StudyMaterial.objects.filter(exam_id__in=exam_ids).values('exam_id', 'content_category').annotate(count=Count('id'))
        count_map = {}
        for item in counts:
            eid = item['exam_id']
            if eid not in count_map:
                count_map[eid] = {"syllabus": 0, "subjective_topicwise": 0, "objective_topicwise": 0, "revision_notes": 0, "total": 0}
            cat = item['content_category']
            if cat in count_map[eid]:
                count_map[eid][cat] = item['count']
            if cat != 'syllabus':
                count_map[eid]["total"] += item['count']

        courses = Course.objects.filter(exam_id__in=exam_ids, status__in=['published', 'coming_soon']).order_by('id')
        course_map = {}
        for c in courses:
            if c.exam_id not in course_map:
                course_map[c.exam_id] = c

        tree = []
        for cat in categories:
            root_exams = all_exams.filter(category=cat, parent__isnull=True).order_by('order', 'id')
            level_data = []
            for root_exam in root_exams:
                children = all_exams.filter(parent=root_exam).order_by('order', 'id')
                if children.exists():
                    prep_data = []
                    # A Level can also carry materials uploaded straight onto it
                    # (e.g. a general syllabus PDF that applies regardless of
                    # Preparation) rather than onto one of its children - the
                    # Syllabus Builder's "Upload PDF" action allows that on any
                    # exam node. Surface that as its own browsable "preparation"
                    # here too, or those materials would be saved successfully
                    # but never appear anywhere in this admin page.
                    own_counts = count_map.get(root_exam.id)
                    if own_counts and own_counts["total"] > 0:
                        c_self = course_map.get(root_exam.id)
                        prep_data.append({
                            "id": root_exam.id, "name": f"{root_exam.name} (General)", "order": -1,
                            "courseId": c_self.id if c_self else None, "courseTitle": c_self.title if c_self else None,
                            "courseStatus": c_self.status if c_self else None, "isComingSoon": (c_self.status == 'coming_soon') if c_self else False,
                            "counts": own_counts,
                        })
                    for child in children:
                        c = course_map.get(child.id)
                        prep_data.append({
                            "id": child.id, "name": child.name, "order": child.order,
                            "courseId": c.id if c else None, "courseTitle": c.title if c else None,
                            "courseStatus": c.status if c else None, "isComingSoon": (c.status == 'coming_soon') if c else False,
                            "counts": count_map.get(child.id, {"syllabus": 0, "subjective_topicwise": 0, "objective_topicwise": 0, "revision_notes": 0, "total": 0})
                        })
                    level_data.append({"id": root_exam.id, "name": root_exam.name, "order": root_exam.order, "preparations": prep_data})
                else:
                    c = course_map.get(root_exam.id)
                    level_data.append({
                        "id": root_exam.id, "name": cat.name, "order": root_exam.order,
                        "preparations": [{
                            "id": root_exam.id, "name": root_exam.name, "order": root_exam.order,
                            "courseId": c.id if c else None, "courseTitle": c.title if c else None,
                            "courseStatus": c.status if c else None, "isComingSoon": (c.status == 'coming_soon') if c else False,
                            "counts": count_map.get(root_exam.id, {"syllabus": 0, "subjective_topicwise": 0, "objective_topicwise": 0, "revision_notes": 0, "total": 0})
                        }]
                    })
            tree.append({"id": cat.id, "name": cat.name, "order": cat.order, "levels": level_data})
        return Response(tree)


class AdminCourseStatusView(APIView):
    """PATCH /api/admin/courses/<id>/status/ - flips a Course between
    coming_soon/published/archived. Mirrors the CourseAdmin
    mark_coming_soon/mark_published/mark_archived Django-admin actions so
    there's one source of truth for what each status transition does."""
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        from courses.models import Course

        new_status = request.data.get('status')
        valid_statuses = {'draft', 'published', 'coming_soon', 'archived'}
        if new_status not in valid_statuses:
            return Response(
                {"error": f"status must be one of {sorted(valid_statuses)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            course = Course.objects.get(pk=pk)
        except Course.DoesNotExist:
            return Response({"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND)

        old_status = course.status
        course.status = new_status
        if new_status in ('coming_soon', 'archived'):
            course.is_open_for_enrollment = False
        course.save(update_fields=['status', 'is_open_for_enrollment', 'updated_at'])

        AuditLog.objects.create(
            actor=request.user, action='COURSE_STATUS_CHANGED',
            entity_type='Course', entity_id=str(course.id),
            details={"title": course.title, "from": old_status, "to": new_status},
        )
        return Response({"id": course.id, "status": course.status})


class AdminPreparationAcademicTreeView(APIView):
    """GET /api/admin/study-materials/academic-tree/?exam_id=<id>
    Returns canonical master academic tree (subjects, chapters, topics)
    for a selected preparation, enriched with real database usage counts
    (notes, questions, exams) and active/archived statuses in O(1) queries.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        from collections import defaultdict, Counter
        from exams.models import Subject, Chapter, Topic, Question, Examination
        from notes.models import StudyMaterial

        exam_id = request.query_params.get('exam_id') or request.query_params.get('exam')
        if not exam_id:
            return Response({"error": "exam_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        subjects = Subject.objects.filter(
            paper__exam_id=exam_id
        ).select_related('paper').prefetch_related('chapters__topics').order_by('order', 'id')

        # Fallback if subjects were created without paper association for this exam
        if not subjects.exists():
            subjects = Subject.objects.filter(
                Q(paper__exam_id=exam_id) | Q(paper__isnull=True)
            ).select_related('paper').prefetch_related('chapters__topics').order_by('order', 'id')

        chaps = [c for s in subjects for c in s.chapters.all()]
        tops = [t for c in chaps for t in c.topics.all()]
        top_ids = [t.id for t in tops]
        chap_ids = [c.id for c in chaps]
        sub_ids = [s.id for s in subjects]

        # Topic -> Chapter, and Chapter -> Subject mappings
        topic_to_chap = {t.id: c.id for c in chaps for t in c.topics.all()}
        chap_to_sub = {c.id: s.id for s in subjects for c in s.chapters.all()}

        # 1. Study Materials counts (O(1) query) — exclude syllabus category
        notes_qs = StudyMaterial.objects.filter(
            exam_id=exam_id
        ).exclude(content_category='syllabus').values('id', 'subject_id', 'chapter_id', 'topic_id')
        top_notes_count = Counter()
        chap_notes_ids = defaultdict(set)
        sub_notes_ids = defaultdict(set)
        for n in notes_qs:
            nid = n['id']
            tid = n['topic_id']
            cid = n['chapter_id'] or (topic_to_chap.get(tid) if tid else None)
            sid = n['subject_id'] or (chap_to_sub.get(cid) if cid else None)
            if tid:
                top_notes_count[tid] += 1
            if cid:
                chap_notes_ids[cid].add(nid)
            if sid:
                sub_notes_ids[sid].add(nid)

        # 2. Question Bank counts (O(1) query)
        q_qs = Question.objects.filter(topic_id__in=top_ids).values('id', 'topic_id', 'topic__chapter_id', 'topic__chapter__subject_id')
        top_q_count = Counter()
        chap_q_count = Counter()
        sub_q_count = Counter()
        for q in q_qs:
            tid = q['topic_id']
            cid = q['topic__chapter_id']
            sid = q['topic__chapter__subject_id']
            if tid:
                top_q_count[tid] += 1
            if cid:
                chap_q_count[cid] += 1
            if sid:
                sub_q_count[sid] += 1

        # 3. Examination counts (O(1) query)
        exam_qs = Examination.objects.filter(
            Q(exam_id=exam_id) | Q(subject_id__in=sub_ids) | Q(questions__topic_id__in=top_ids)
        ).values('id', 'subject_id', 'questions__topic_id', 'questions__topic__chapter_id').distinct()
        
        top_exam_ids = defaultdict(set)
        chap_exam_ids = defaultdict(set)
        sub_exam_ids = defaultdict(set)
        for ex in exam_qs:
            eid = ex['id']
            sid = ex['subject_id']
            tid = ex['questions__topic_id']
            cid = ex['questions__topic__chapter_id'] or (topic_to_chap.get(tid) if tid else None)
            if not sid and cid:
                sid = chap_to_sub.get(cid)
            if tid:
                top_exam_ids[tid].add(eid)
            if cid:
                chap_exam_ids[cid].add(eid)
            if sid:
                sub_exam_ids[sid].add(eid)

        data = []
        for s in subjects:
            chap_data = []
            for c in sorted(s.chapters.all(), key=lambda o: (o.order, o.id)):
                topic_data = []
                for t in sorted(c.topics.all(), key=lambda o: (o.order, o.id)):
                    topic_data.append({
                        "id": t.id,
                        "name": t.name,
                        "description": t.description or '',
                        "order": t.order,
                        "is_active": t.is_active,
                        "chapter_id": c.id,
                        "chapter_name": c.title,
                        "subject_id": s.id,
                        "subject_name": s.name,
                        "notes_count": top_notes_count[t.id],
                        "questions_count": top_q_count[t.id],
                        "exams_count": len(top_exam_ids[t.id]),
                    })
                chap_data.append({
                    "id": c.id,
                    "title": c.title,
                    "name": c.title,
                    "description": c.description or '',
                    "order": c.order,
                    "is_active": c.is_active,
                    "subject_id": s.id,
                    "subject_name": s.name,
                    "topics_count": len(topic_data),
                    "notes_count": len(chap_notes_ids[c.id]),
                    "questions_count": chap_q_count[c.id],
                    "exams_count": len(chap_exam_ids[c.id]),
                    "topics": topic_data,
                })
            data.append({
                "id": s.id,
                "name": s.name,
                "code": s.code or '',
                "description": s.description or '',
                "order": s.order,
                "is_active": s.is_active,
                "paper_id": s.paper_id,
                "paper_name": s.paper.name if s.paper else None,
                "chapters_count": len(chap_data),
                "topics_count": sum(c['topics_count'] for c in chap_data),
                "notes_count": len(sub_notes_ids[s.id]),
                "questions_count": sub_q_count[s.id],
                "exams_count": len(sub_exam_ids[s.id]),
                "chapters": chap_data,
            })

        return Response(data)


# ============================================================
# STUDY PLANS MANAGEMENT VIEW
# ============================================================

class AdminStudyPlansView(APIView):
    """List study plans with pagination and filtering."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from study_plan.models import StudyPlan

        search = request.query_params.get('search', '')
        level_filter = request.query_params.get('level', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        # Start with all study plans ordered by creation date
        qs = StudyPlan.objects.select_related(
            'student', 'exam', 'template'
        ).order_by('-created_at')

        if level_filter:
            qs = qs.filter(level=level_filter)

        if search:
            qs = qs.filter(
                Q(student__username__icontains=search) |
                Q(student__email__icontains=search) |
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search) |
                Q(exam__name__icontains=search)
            )

        total = qs.count()
        start = (page - 1) * page_size
        study_plans = qs[start:start + page_size]

        data = []
        for plan in study_plans:
            data.append({
                "id": plan.id,
                "student": plan.student.get_full_name() or plan.student.username,
                "studentId": plan.student.id,
                "email": plan.student.email,
                "exam": plan.exam.name if plan.exam else 'N/A',
                "examId": plan.exam.id if plan.exam else None,
                "template": plan.template.name if plan.template else None,
                "targetDate": (plan.target_date.isoformat() if plan.target_date else None),
                "dailyMinutes": plan.daily_minutes,
                "level": plan.level,
                "isPaused": plan.is_paused,
                "studyDays": plan.study_days,
                "preferredTime": plan.preferred_time,
                "createdAt": plan.created_at.isoformat(),
                "updatedAt": plan.updated_at.isoformat(),
            })

        return Response({
            "plans": data,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size,
        })

    def post(self, request):
        """Create study plans for one or more students and generate their tasks.

        Accepts either `student` (a single id) or `students` (a list). Students
        who already hold a plan are reported as skipped rather than failing the
        whole batch, so assigning to "all students" stays useful as the roster
        grows.
        """
        from study_plan.models import StudyPlan, StudyPlanTemplate
        from study_plan.services import generate_study_plan_tasks

        raw_students = request.data.get('students')
        if raw_students is None:
            single = request.data.get('student')
            raw_students = [single] if single else []
        if not isinstance(raw_students, list):
            return Response({"error": "students must be a list of student ids."},
                            status=status.HTTP_400_BAD_REQUEST)

        exam_id = request.data.get('exam')
        target_date = request.data.get('target_date')

        missing = [f for f, v in (
            ('students', raw_students), ('exam', exam_id), ('target_date', target_date)
        ) if not v]
        if missing:
            return Response(
                {"error": f"Missing required field(s): {', '.join(missing)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            exam = Exam.objects.get(pk=exam_id)
        except (Exam.DoesNotExist, ValueError, TypeError):
            return Response({"error": "That exam does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        template = None
        template_id = request.data.get('template')
        if template_id:
            try:
                template = StudyPlanTemplate.objects.get(pk=template_id)
            except (StudyPlanTemplate.DoesNotExist, ValueError, TypeError):
                return Response({"error": "That template does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        parsed_date = parse_date(str(target_date))
        if not parsed_date:
            return Response({"error": "target_date must be in YYYY-MM-DD format."}, status=status.HTTP_400_BAD_REQUEST)
        if parsed_date <= timezone.now().date():
            return Response({"error": "target_date must be in the future."}, status=status.HTTP_400_BAD_REQUEST)

        level = (request.data.get('level') or 'BEGINNER').upper()
        if level not in dict(StudyPlan.LEVEL_CHOICES):
            return Response({"error": f"Unsupported level: {level}"}, status=status.HTTP_400_BAD_REQUEST)

        preferred_time = request.data.get('preferred_time') or None
        if preferred_time:
            preferred_time = preferred_time.upper()
            if preferred_time not in dict(StudyPlan.TIME_CHOICES):
                return Response({"error": f"Unsupported preferred_time: {preferred_time}"}, status=status.HTTP_400_BAD_REQUEST)

        study_days = request.data.get('study_days') or []
        if not isinstance(study_days, list):
            return Response({"error": "study_days must be a list of day names."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            daily_minutes = int(request.data.get('daily_minutes', 120))
        except (TypeError, ValueError):
            return Response({"error": "daily_minutes must be a number."}, status=status.HTTP_400_BAD_REQUEST)
        if daily_minutes < 1:
            return Response({"error": "daily_minutes must be greater than 0."}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve every requested student up front, then walk the list in the
        # order it was given so the report lines up with what the admin picked.
        found = {u.pk: u for u in User.objects.filter(pk__in=[
            s for s in raw_students if str(s).isdigit()
        ])}
        already_planned = set(
            StudyPlan.objects.filter(student_id__in=found.keys())
            .values_list('student_id', flat=True)
        )

        created, skipped, warnings = [], [], []

        for raw_id in raw_students:
            student = found.get(int(raw_id)) if str(raw_id).isdigit() else None
            if not student:
                skipped.append({"student": str(raw_id), "reason": "Student not found."})
                continue

            # StudyPlan.student is a OneToOneField, so a student can only ever
            # hold one plan.
            if student.pk in already_planned:
                skipped.append({
                    "student": student.get_full_name() or student.username,
                    "reason": "Already has a study plan.",
                })
                continue

            plan = StudyPlan.objects.create(
                student=student,
                exam=exam,
                template=template,
                target_date=parsed_date,
                daily_minutes=daily_minutes,
                study_days=study_days,
                preferred_time=preferred_time,
                level=level,
            )

            # Fill the calendar straight away so the plan is usable on creation.
            task_count = 0
            try:
                generate_study_plan_tasks(plan)
                task_count = plan.tasks.count()
            except Exception as exc:  # A generation failure must not lose the plan.
                warnings.append(
                    f"{student.get_full_name() or student.username}: tasks could not be generated ({exc})."
                )

            created.append({
                "id": plan.id,
                "student": plan.student.get_full_name() or plan.student.username,
                "task_count": task_count,
            })

        payload = {
            "created": created,
            "skipped": skipped,
            "created_count": len(created),
            "skipped_count": len(skipped),
            "task_count": sum(c["task_count"] for c in created),
            "exam": exam.name,
            "targetDate": parsed_date.isoformat(),
        }
        if warnings:
            payload["warning"] = " ".join(warnings)

        if not created:
            # Nothing was created, so tell the caller why rather than reporting
            # a hollow success.
            reasons = "; ".join(f"{s['student']} — {s['reason']}" for s in skipped)
            payload["error"] = reasons or "No study plans could be created."
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)

        return Response(payload, status=status.HTTP_201_CREATED)


class AdminStudyPlanDetailView(APIView):
    """Retrieve, update or delete a single study plan."""
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        from study_plan.models import StudyPlan
        return StudyPlan.objects.select_related('student', 'exam', 'template').filter(pk=pk).first()

    def get(self, request, pk):
        plan = self._get(pk)
        if not plan:
            return Response({"error": "Study plan not found."}, status=status.HTTP_404_NOT_FOUND)

        tasks = plan.tasks.order_by('date', 'id')
        return Response({
            "id": plan.id,
            "student": plan.student.get_full_name() or plan.student.username,
            "studentId": plan.student.id,
            "email": plan.student.email,
            "exam": plan.exam.name if plan.exam else None,
            "examId": plan.exam_id,
            "template": plan.template.name if plan.template else None,
            "templateId": plan.template_id,
            "targetDate": (plan.target_date.isoformat() if plan.target_date else None),
            "dailyMinutes": plan.daily_minutes,
            "studyDays": plan.study_days,
            "preferredTime": plan.preferred_time,
            "level": plan.level,
            "isPaused": plan.is_paused,
            "taskCount": tasks.count(),
            "completedTasks": tasks.filter(status='COMPLETED').count(),
            "tasks": [{
                "id": t.id,
                "date": t.date.isoformat(),
                "title": t.title,
                "taskType": t.task_type,
                "durationMinutes": t.duration_minutes,
                "status": t.status,
            } for t in tasks[:200]],
        })

    def patch(self, request, pk):
        from study_plan.models import StudyPlan

        plan = self._get(pk)
        if not plan:
            return Response({"error": "Study plan not found."}, status=status.HTTP_404_NOT_FOUND)

        if 'target_date' in request.data:
            parsed = parse_date(str(request.data['target_date']))
            if not parsed:
                return Response({"error": "target_date must be in YYYY-MM-DD format."}, status=status.HTTP_400_BAD_REQUEST)
            plan.target_date = parsed

        if 'daily_minutes' in request.data:
            try:
                plan.daily_minutes = int(request.data['daily_minutes'])
            except (TypeError, ValueError):
                return Response({"error": "daily_minutes must be a number."}, status=status.HTTP_400_BAD_REQUEST)

        if 'level' in request.data:
            level = str(request.data['level']).upper()
            if level not in dict(StudyPlan.LEVEL_CHOICES):
                return Response({"error": f"Unsupported level: {level}"}, status=status.HTTP_400_BAD_REQUEST)
            plan.level = level

        if 'preferred_time' in request.data:
            value = request.data['preferred_time']
            if value:
                value = str(value).upper()
                if value not in dict(StudyPlan.TIME_CHOICES):
                    return Response({"error": f"Unsupported preferred_time: {value}"}, status=status.HTTP_400_BAD_REQUEST)
            plan.preferred_time = value or None

        if 'study_days' in request.data:
            if not isinstance(request.data['study_days'], list):
                return Response({"error": "study_days must be a list of day names."}, status=status.HTTP_400_BAD_REQUEST)
            plan.study_days = request.data['study_days']

        if 'is_paused' in request.data:
            plan.is_paused = bool(request.data['is_paused'])

        plan.save()
        return Response({"success": True, "id": plan.id})

    def delete(self, request, pk):
        plan = self._get(pk)
        if not plan:
            return Response({"error": "Study plan not found."}, status=status.HTTP_404_NOT_FOUND)
        plan.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================
# AUDIT LOGS MANAGEMENT VIEW
# ============================================================

def _audit_log_severity(action):
    """Best-effort severity from an AuditLog.action verb (e.g. BULK_DELETE,
    STUDENT_FEEDBACK_SENT). Destructive/rejecting actions are flagged so an
    admin scanning the log can spot them without reading every row."""
    action_upper = (action or '').upper()
    if any(k in action_upper for k in ('DELETE', 'REJECT', 'CANCEL', 'REMOVE', 'REVOKE')):
        return 'warning'
    return 'info'


AUDIT_CATEGORIES = ('user', 'content', 'evaluation', 'admin')


def _collect_audit_events():
    """Real events from every source the Audit Logs page covers. Each has a
    stable 'id' of the form '<source>:<pk>' (resolved back to its real record
    by AdminAuditLogDetailView) and a 'category' in AUDIT_CATEGORIES.

    Folds in three activity streams (registrations, content creation,
    evaluations) that are real system activity yet were never written to
    AuditLog - AuditLog only ever contains actions an admin/staff endpoint
    explicitly logs (bulk actions, notification sends, feedback, exam
    question generation, etc.), not ordinary usage.
    """
    from exams.models import Question, Evaluation

    events = []

    for user in User.objects.all().order_by('-date_joined')[:100]:
        events.append({
            'id': f'user:{user.id}',
            'category': 'user',
            'timestamp': user.date_joined,
            'action': 'user_registration',
            'actionLabel': 'User Registration',
            'user': user.get_full_name() or user.username,
            'email': user.email,
            'details': f'{user.get_full_name() or user.username} ({user.role}) registered',
            'severity': 'info',
        })

    for q in Question.objects.select_related('created_by').order_by('-created_at')[:50]:
        creator = (q.created_by.get_full_name() or q.created_by.username) if q.created_by else 'Unknown'
        events.append({
            'id': f'question:{q.id}',
            'category': 'content',
            'timestamp': q.created_at,
            'action': 'content_created',
            'actionLabel': 'Content Created',
            'user': creator,
            'email': q.created_by.email if q.created_by else 'N/A',
            'details': f'Question "{q.text[:50]}..." created by {creator}',
            'severity': 'info',
        })

    evaluations = Evaluation.objects.select_related(
        'evaluator', 'answer__attempt__student'
    ).order_by('-evaluated_at')[:50]
    for ev in evaluations:
        student = ev.answer.attempt.student
        evaluator = (ev.evaluator.get_full_name() or ev.evaluator.username) if ev.evaluator else 'Unknown'
        events.append({
            'id': f'evaluation:{ev.id}',
            'category': 'evaluation',
            'timestamp': ev.evaluated_at,
            'action': 'evaluation_submitted',
            'actionLabel': 'Evaluation Submitted',
            'user': evaluator,
            'email': ev.evaluator.email if ev.evaluator else 'N/A',
            'details': f'Answer by {student.get_full_name() or student.username} evaluated with {ev.marks_obtained} marks',
            'severity': 'info',
        })

    for log in AuditLog.objects.select_related('actor').order_by('-timestamp')[:200]:
        actor_name = (log.actor.get_full_name() or log.actor.username) if log.actor else 'System'
        label = log.action.replace('_', ' ').title()
        entity = f'{log.entity_type} {log.entity_id}'.strip() if log.entity_id else log.entity_type
        events.append({
            'id': f'auditlog:{log.id}',
            'category': 'admin',
            'timestamp': log.timestamp,
            'action': log.action.lower(),
            'actionLabel': label,
            'user': actor_name,
            'email': log.actor.email if log.actor else 'N/A',
            'details': f'{label} on {entity}',
            'severity': _audit_log_severity(log.action),
        })

    events.sort(key=lambda e: e['timestamp'], reverse=True)
    return events


def _filter_by_search(events, search):
    if not search:
        return events
    s = search.lower()
    return [e for e in events if (
        s in e['user'].lower() or s in e['email'].lower() or s in e['details'].lower()
    )]


class AdminAuditLogsView(APIView):
    """Aggregate audit logs from system activities, including the structured
    AuditLog table other admin views write to (bulk actions, notification
    sends, feedback sends, exam question generation, ...)."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        category_filter = request.query_params.get('action', '')  # 'user' | 'content' | 'evaluation' | 'admin' | 'all' | ''
        search = request.query_params.get('search', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        all_events = _filter_by_search(_collect_audit_events(), search)

        # Category totals always reflect the search term but never the
        # category filter itself, so the overview cards stay stable
        # reference counts while a category is selected below them.
        category_totals = {c: 0 for c in AUDIT_CATEGORIES}
        for e in all_events:
            category_totals[e['category']] += 1

        if category_filter and category_filter != 'all':
            events = [e for e in all_events if e['category'] == category_filter]
        else:
            events = all_events

        total = len(events)
        start = (page - 1) * page_size
        paginated_events = events[start:start + page_size]

        data = [{
            "id": event['id'],
            "timestamp": event['timestamp'].isoformat(),
            "action": event['action'],
            "actionLabel": event['actionLabel'],
            "user": event['user'],
            "email": event['email'],
            "details": event['details'],
            "severity": event['severity'],
        } for event in paginated_events]

        return Response({
            "logs": data,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size,
            "categoryTotals": {
                "user": category_totals['user'],
                "content": category_totals['content'],
                "evaluation": category_totals['evaluation'],
                "admin": category_totals['admin'],
            },
        })


class AdminAuditLogDetailView(APIView):
    """GET /api/admin/audit-logs/<event_id>/ - resolves a composite
    '<source>:<pk>' id (see _collect_audit_events) back to its real record."""
    permission_classes = [IsAdminUser]

    def get(self, request, event_id):
        from exams.models import Question, Evaluation

        try:
            source, pk = event_id.split(':', 1)
        except ValueError:
            return Response({'error': 'Invalid event id.'}, status=status.HTTP_404_NOT_FOUND)

        if source == 'auditlog':
            try:
                log = AuditLog.objects.select_related('actor').get(pk=pk)
            except (AuditLog.DoesNotExist, ValueError):
                return Response({'error': 'Event not found.'}, status=status.HTTP_404_NOT_FOUND)
            return Response({
                'id': event_id,
                'source': 'admin_action',
                'actionLabel': log.action.replace('_', ' ').title(),
                'timestamp': log.timestamp.isoformat(),
                'actorName': (log.actor.get_full_name() or log.actor.username) if log.actor else None,
                'actorEmail': log.actor.email if log.actor else None,
                'entityType': log.entity_type,
                'entityId': log.entity_id,
                'details': log.details,
                'severity': _audit_log_severity(log.action),
            })

        if source == 'user':
            try:
                u = User.objects.get(pk=pk)
            except (User.DoesNotExist, ValueError):
                return Response({'error': 'Event not found.'}, status=status.HTTP_404_NOT_FOUND)
            return Response({
                'id': event_id,
                'source': 'user_registration',
                'actionLabel': 'User Registration',
                'timestamp': u.date_joined.isoformat(),
                'actorName': u.get_full_name() or u.username,
                'actorEmail': u.email,
                'entityType': 'User',
                'entityId': str(u.id),
                'details': {'username': u.username, 'role': u.role, 'isActive': u.is_active},
                'severity': 'info',
            })

        if source == 'question':
            try:
                q = Question.objects.select_related('created_by').get(pk=pk)
            except (Question.DoesNotExist, ValueError):
                return Response({'error': 'Event not found.'}, status=status.HTTP_404_NOT_FOUND)
            creator = (q.created_by.get_full_name() or q.created_by.username) if q.created_by else None
            return Response({
                'id': event_id,
                'source': 'content_created',
                'actionLabel': 'Content Created',
                'timestamp': q.created_at.isoformat(),
                'actorName': creator,
                'actorEmail': q.created_by.email if q.created_by else None,
                'entityType': 'Question',
                'entityId': str(q.id),
                'details': {'text': q.text, 'questionType': q.question_type, 'status': q.status},
                'severity': 'info',
            })

        if source == 'evaluation':
            try:
                ev = Evaluation.objects.select_related('evaluator', 'answer__attempt__student').get(pk=pk)
            except (Evaluation.DoesNotExist, ValueError):
                return Response({'error': 'Event not found.'}, status=status.HTTP_404_NOT_FOUND)
            student = ev.answer.attempt.student
            evaluator = (ev.evaluator.get_full_name() or ev.evaluator.username) if ev.evaluator else None
            return Response({
                'id': event_id,
                'source': 'evaluation_submitted',
                'actionLabel': 'Evaluation Submitted',
                'timestamp': ev.evaluated_at.isoformat(),
                'actorName': evaluator,
                'actorEmail': ev.evaluator.email if ev.evaluator else None,
                'entityType': 'Evaluation',
                'entityId': str(ev.id),
                'details': {
                    'student': student.get_full_name() or student.username,
                    'marksObtained': ev.marks_obtained,
                    'feedback': ev.feedback,
                },
                'severity': 'info',
            })

        return Response({'error': 'Unknown event type.'}, status=status.HTTP_404_NOT_FOUND)


class AdminAuditLogRetentionView(APIView):
    """GET/POST /api/admin/audit-logs/retention/

    Retention is applied immediately on save (matching the UI's own warning
    copy), not by a background job. It only ever prunes AuditLog rows - the
    underlying business records behind the other event sources (users,
    questions, evaluations) are never touched by this."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from core.models import AdminSettings
        settings_obj = AdminSettings.get_settings()
        return Response({'retentionDays': settings_obj.audit_log_retention_days})

    def post(self, request):
        from core.models import AdminSettings

        try:
            retention_days = int(request.data.get('retentionDays'))
        except (TypeError, ValueError):
            return Response({'error': 'retentionDays must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
        if retention_days < 1:
            return Response({'error': 'retentionDays must be at least 1.'}, status=status.HTTP_400_BAD_REQUEST)

        settings_obj = AdminSettings.get_settings()
        settings_obj.audit_log_retention_days = retention_days
        settings_obj.updated_by = request.user
        settings_obj.save(update_fields=['audit_log_retention_days', 'updated_by', 'updated_at'])

        cutoff = timezone.now() - timedelta(days=retention_days)
        deleted_count, _ = AuditLog.objects.filter(timestamp__lt=cutoff).delete()

        AuditLog.objects.create(
            actor=request.user, action='AUDIT_RETENTION_POLICY_CHANGED', entity_type='AdminSettings',
            entity_id=None, details={'retention_days': retention_days, 'purged_count': deleted_count},
        )

        return Response({'retentionDays': retention_days, 'purgedCount': deleted_count})


class AdminAuditLogExportView(APIView):
    """GET /api/admin/audit-logs/export/ - CSV of the same real events the
    list view shows, honoring the same search/category filters."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        import csv

        category_filter = request.query_params.get('action', '')
        search = request.query_params.get('search', '')

        events = _filter_by_search(_collect_audit_events(), search)
        if category_filter and category_filter != 'all':
            events = [e for e in events if e['category'] == category_filter]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="audit-logs.csv"'
        writer = csv.writer(response)
        writer.writerow(['Timestamp', 'Action', 'User', 'Email', 'Details', 'Severity'])
        for e in events:
            writer.writerow([
                e['timestamp'].isoformat(), e['actionLabel'], e['user'], e['email'], e['details'], e['severity'],
            ])
        return response


class AdminAuditLogExportJobView(APIView):
    """POST /api/admin/audit-logs/export-jobs/ - queues a background export
    instead of building the CSV in-request (AdminAuditLogExportView above).
    Same filters, same output - the difference is audit logs grow without
    bound, so this returns a job id immediately and the file gets generated
    by a Celery worker (or `manage.py run_export_job <id>` locally).

    GET on the same URL lists this admin's recent export jobs so the
    frontend can poll status and offer the download link once ready.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        from .models import ExportJob
        from .tasks import generate_export_job_task

        filters = {
            'action': request.data.get('action', ''),
            'search': request.data.get('search', ''),
        }
        job = ExportJob.objects.create(
            export_type='audit_logs', filters=filters, requested_by=request.user,
        )

        try:
            generate_export_job_task.delay(job.id)
        except Exception:
            # No broker reachable (e.g. local dev without Redis running) -
            # the job row still exists so `manage.py run_export_job <id>`
            # (or a worker coming back later, if something re-queues it)
            # can still produce it. Never fail the request just because the
            # queue is unreachable right now.
            logger.exception("Could not enqueue export job %s - broker unreachable.", job.id)

        return Response({
            'id': job.id,
            'status': job.status,
            'exportType': job.export_type,
            'createdAt': job.created_at.isoformat(),
        }, status=status.HTTP_202_ACCEPTED)

    def get(self, request):
        from .models import ExportJob

        jobs = ExportJob.objects.filter(requested_by=request.user).order_by('-created_at')[:20]
        return Response([{
            'id': j.id,
            'exportType': j.export_type,
            'status': j.status,
            'rowCount': j.row_count,
            'errorMessage': j.error_message,
            'downloadUrl': j.file.url if j.file else None,
            'createdAt': j.created_at.isoformat(),
            'completedAt': j.completed_at.isoformat() if j.completed_at else None,
        } for j in jobs])


class AdminNotificationsListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from core.models import AdminNotification

        # Get filter parameters
        status_filter = request.query_params.get('status', '')
        type_filter = request.query_params.get('type', '')
        search = request.query_params.get('search', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        audience_filter = request.query_params.get('audience', '')
        date_from = request.query_params.get('date_from', '')
        date_to = request.query_params.get('date_to', '')

        # Read counts come from the delivery rows, annotated so the list stays
        # a single query no matter how many campaigns are shown.
        query = AdminNotification.objects.select_related('created_by').annotate(
            delivered_count=Count('deliveries', distinct=True),
            read_total=Count('deliveries', filter=Q(deliveries__is_read=True), distinct=True),
        )

        if status_filter:
            query = query.filter(status=status_filter)
        if type_filter:
            query = query.filter(type=type_filter)
        if audience_filter:
            query = query.filter(target_role=audience_filter)
        if date_from:
            query = query.filter(created_at__date__gte=date_from)
        if date_to:
            query = query.filter(created_at__date__lte=date_to)
        if search:
            query = query.filter(Q(title__icontains=search) | Q(content__icontains=search))

        total = query.count()
        start = (page - 1) * page_size
        notifications = query[start:start + page_size]

        data = []
        for notif in notifications:
            data.append({
                'id': notif.id,
                'title': notif.title,
                'content': notif.content,
                'type': notif.type,
                'targetRole': notif.target_role,
                'status': notif.status,
                'recipientCount': notif.delivered_count,
                'readCount': notif.read_total,
                'unreadCount': max(0, notif.delivered_count - notif.read_total),
                'scheduledFor': notif.scheduled_for.isoformat() if notif.scheduled_for else None,
                'sentAt': notif.sent_at.isoformat() if notif.sent_at else None,
                'createdBy': notif.created_by.get_full_name() or notif.created_by.username if notif.created_by else 'N/A',
                'createdAt': notif.created_at.isoformat(),
                'updatedAt': notif.updated_at.isoformat(),
            })

        # Status counts span every campaign, not just this page — deriving them
        # from the page would understate them as soon as pagination kicks in.
        status_counts = dict(
            AdminNotification.objects.values_list('status')
            .annotate(n=Count('id')).values_list('status', 'n')
        )

        return Response({
            'notifications': data,
            'total': total,
            'page': page,
            'pageSize': page_size,
            'totalPages': (total + page_size - 1) // page_size,
            'summary': {
                'total': AdminNotification.objects.count(),
                'sent': status_counts.get('sent', 0),
                'draft': status_counts.get('draft', 0),
                'scheduled': status_counts.get('scheduled', 0),
                'failed': status_counts.get('failed', 0),
            },
        })


class AdminNotificationsCreateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        """Create an admin notification and, for send-now, deliver it.

        delivery = 'now'      → fan out to recipients, status becomes 'sent'
        delivery = 'schedule' → stored with scheduled_for, status 'scheduled'
        delivery = 'draft'    → stored only
        """
        from core.models import AdminNotification
        from core.notification_service import (
            AUDIENCE_CHOICES, NotificationBroadcastError,
            broadcast_admin_notification, resolve_audience,
        )

        title = (request.data.get('title') or '').strip()
        content = (request.data.get('content') or '').strip()
        notif_type = (request.data.get('type') or 'announcement').strip().lower()
        audience = (request.data.get('targetRole') or 'all').strip().lower()
        delivery = (request.data.get('delivery') or 'draft').strip().lower()
        scheduled_for = request.data.get('scheduledFor')
        course_id = request.data.get('courseId')
        user_ids = request.data.get('userIds') or []

        errors = {}
        if not title:
            errors['title'] = 'Title is required.'
        if not content:
            errors['content'] = 'Message is required.'
        if notif_type not in dict(AdminNotification.TYPE_CHOICES):
            errors['type'] = f'Unsupported type: {notif_type}'
        if audience not in dict(AUDIENCE_CHOICES):
            errors['targetRole'] = f'Unsupported audience: {audience}'
        if delivery not in ('now', 'schedule', 'draft'):
            errors['delivery'] = f'Unsupported delivery: {delivery}'
        if delivery == 'schedule':
            if not scheduled_for:
                errors['scheduledFor'] = 'Pick a date and time to schedule for.'
            else:
                parsed = parse_datetime(str(scheduled_for))
                if not parsed:
                    errors['scheduledFor'] = 'scheduledFor must be an ISO-8601 datetime.'
                elif parsed <= timezone.now():
                    errors['scheduledFor'] = 'The scheduled time must be in the future.'
        if user_ids and not isinstance(user_ids, list):
            errors['userIds'] = 'userIds must be a list.'

        if errors:
            return Response({'error': 'Validation failed.', 'details': errors},
                            status=status.HTTP_400_BAD_REQUEST)

        # Confirm the audience resolves before writing anything.
        try:
            recipients = resolve_audience(audience, course_id=course_id, user_ids=user_ids)
            recipient_preview = recipients.count()
        except NotificationBroadcastError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if delivery == 'now' and recipient_preview == 0:
            return Response(
                {'error': 'That audience currently has no active recipients.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            notification = AdminNotification.objects.create(
                title=title,
                content=content,
                type=notif_type,
                target_role=audience,
                scheduled_for=parse_datetime(str(scheduled_for)) if scheduled_for else None,
                created_by=request.user,
                status='scheduled' if delivery == 'schedule' else 'draft',
            )

            delivered = 0
            if delivery == 'now':
                delivered = broadcast_admin_notification(
                    notification, course_id=course_id, user_ids=user_ids
                )

        AuditLog.objects.create(
            actor=request.user, action='CREATE_NOTIFICATION',
            entity_type='AdminNotification', entity_id=str(notification.id),
            details={'title': title, 'audience': audience, 'delivery': delivery,
                     'delivered': delivered},
        )

        return Response({
            'id': notification.id,
            'title': notification.title,
            'content': notification.content,
            'type': notification.type,
            'targetRole': notification.target_role,
            'status': notification.status,
            'scheduledFor': notification.scheduled_for.isoformat() if notification.scheduled_for else None,
            'recipientCount': notification.recipient_count,
            # 'created' and 'delivered' are reported separately on purpose — a
            # draft or scheduled notification has been stored, not delivered.
            'created': True,
            'delivered': delivered,
            'audiencePreview': recipient_preview,
        }, status=status.HTTP_201_CREATED)


class AdminNotificationsDeleteView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        from core.models import AdminNotification

        notification = AdminNotification.objects.filter(id=pk).first()
        if not notification:
            return Response({'error': 'Notification not found'},
                            status=status.HTTP_404_NOT_FOUND)

        # A sent notification is a historical record: students already have it
        # in their feed, so deleting the campaign would misrepresent what
        # happened. Drafts and scheduled ones are still safe to remove.
        if notification.status == 'sent':
            return Response(
                {'error': 'A sent notification cannot be deleted. Students have already received it.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        title = notification.title
        notification.delete()
        AuditLog.objects.create(
            actor=request.user, action='DELETE_NOTIFICATION',
            entity_type='AdminNotification', entity_id=str(pk),
            details={'title': title},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminNotificationDetailView(APIView):
    """GET /api/admin/notifications/{id}/ — campaign detail with real read stats."""
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        from core.models import AdminNotification
        from core.notification_service import delivery_stats

        notification = AdminNotification.objects.select_related('created_by').filter(pk=pk).first()
        if not notification:
            return Response({'error': 'Notification not found'},
                            status=status.HTTP_404_NOT_FOUND)

        stats = delivery_stats(notification)
        return Response({
            'id': notification.id,
            'title': notification.title,
            'content': notification.content,
            'type': notification.type,
            'targetRole': notification.target_role,
            'status': notification.status,
            'scheduledFor': notification.scheduled_for.isoformat() if notification.scheduled_for else None,
            'sentAt': notification.sent_at.isoformat() if notification.sent_at else None,
            'createdBy': (
                notification.created_by.get_full_name() or notification.created_by.username
            ) if notification.created_by else None,
            'createdAt': notification.created_at.isoformat(),
            'updatedAt': notification.updated_at.isoformat(),
            **stats,
        })


class AdminNotificationSendView(APIView):
    """POST /api/admin/notifications/{id}/send/ — deliver a draft or scheduled campaign."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        from core.models import AdminNotification
        from core.notification_service import (
            NotificationBroadcastError, broadcast_admin_notification,
        )

        notification = AdminNotification.objects.filter(pk=pk).first()
        if not notification:
            return Response({'error': 'Notification not found'},
                            status=status.HTTP_404_NOT_FOUND)
        if notification.status == 'sent':
            return Response({'error': 'This notification has already been sent.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            delivered = broadcast_admin_notification(
                notification,
                course_id=request.data.get('courseId'),
                user_ids=request.data.get('userIds') or [],
            )
        except NotificationBroadcastError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        AuditLog.objects.create(
            actor=request.user, action='SEND_NOTIFICATION',
            entity_type='AdminNotification', entity_id=str(notification.id),
            details={'title': notification.title, 'delivered': delivered},
        )
        return Response({
            'id': notification.id,
            'status': notification.status,
            'delivered': delivered,
            'recipientCount': notification.recipient_count,
            'sentAt': notification.sent_at.isoformat() if notification.sent_at else None,
        })


class AdminNotificationCancelView(APIView):
    """POST /api/admin/notifications/{id}/cancel/ — revert a scheduled campaign to draft."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        from core.models import AdminNotification

        notification = AdminNotification.objects.filter(pk=pk).first()
        if not notification:
            return Response({'error': 'Notification not found'},
                            status=status.HTTP_404_NOT_FOUND)
        if notification.status != 'scheduled':
            return Response(
                {'error': 'Only a scheduled notification can be cancelled.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notification.status = 'draft'
        notification.scheduled_for = None
        notification.save(update_fields=['status', 'scheduled_for', 'updated_at'])
        return Response({'id': notification.id, 'status': notification.status})


class AdminSupportTicketsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from support.models import SupportTicket
        from django.db.models import Q

        # Get filter parameters
        status_filter = request.query_params.get('status', '')
        priority_filter = request.query_params.get('priority', '')
        category_filter = request.query_params.get('category', '')
        search = request.query_params.get('search', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        base_query = SupportTicket.objects.select_related('student').all()

        # Calculate global summary metrics before filtering
        summary = {
            'total': base_query.count(),
            'open': base_query.filter(status='open').count(),
            'in_progress': base_query.filter(status='in_progress').count(),
            'resolved': base_query.filter(status='resolved').count(),
            'closed': base_query.filter(status='closed').count(),
            'high_priority': base_query.filter(priority__in=['high', 'urgent']).count(),
        }

        # Build query
        query = base_query

        if status_filter:
            query = query.filter(status=status_filter)
        if priority_filter:
            query = query.filter(priority=priority_filter)
        if category_filter:
            query = query.filter(category=category_filter)
        if search:
            query = query.filter(
                Q(ticket_number__icontains=search) |
                Q(student__email__icontains=search) |
                Q(subject__icontains=search)
            )

        total = query.count()
        start = (page - 1) * page_size
        tickets = query.order_by('-updated_at')[start:start + page_size]

        data = []
        for ticket in tickets:
            message_count = ticket.messages.count()
            data.append({
                'id': ticket.id,
                'ticketNumber': ticket.ticket_number,
                'subject': ticket.subject,
                'studentName': ticket.student.get_full_name() or ticket.student.username,
                'studentEmail': ticket.student.email,
                'category': ticket.category,
                'priority': ticket.priority,
                'status': ticket.status,
                'messageCount': message_count,
                'lastUpdated': ticket.updated_at.isoformat(),
                'createdAt': ticket.created_at.isoformat(),
            })

        return Response({
            'tickets': data,
            'summary': summary,
            'total': total,
            'page': page,
            'pageSize': page_size,
            'totalPages': (total + page_size - 1) // page_size,
        })


class AdminTicketDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        from support.models import SupportTicket, SupportMessage

        try:
            ticket = SupportTicket.objects.select_related('student').get(id=pk)
            messages = SupportMessage.objects.select_related('sender').filter(
                ticket=ticket
            ).order_by('created_at')

            messages_data = []
            for msg in messages:
                messages_data.append({
                    'id': msg.id,
                    'sender': msg.sender.get_full_name() or msg.sender.username,
                    'senderEmail': msg.sender.email,
                    'isStaffReply': msg.is_staff_reply,
                    'message': msg.message,
                    'createdAt': msg.created_at.isoformat(),
                })

            return Response({
                'ticket': {
                    'id': ticket.id,
                    'ticketNumber': ticket.ticket_number,
                    'subject': ticket.subject,
                    'studentName': ticket.student.get_full_name() or ticket.student.username,
                    'studentEmail': ticket.student.email,
                    'category': ticket.category,
                    'priority': ticket.priority,
                    'status': ticket.status,
                    'relatedExam': ticket.related_exam or '',
                    'relatedQuestion': ticket.related_question or '',
                    'relatedPage': ticket.related_page or '',
                    'createdAt': ticket.created_at.isoformat(),
                    'updatedAt': ticket.updated_at.isoformat(),
                    'closedAt': ticket.closed_at.isoformat() if ticket.closed_at else None,
                },
                'messages': messages_data,
            })
        except SupportTicket.DoesNotExist:
            return Response(
                {'error': 'Ticket not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class AdminTicketReplyView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        from support.models import SupportTicket, SupportMessage

        try:
            ticket = SupportTicket.objects.get(id=pk)
            message_text = request.data.get('message', '').strip()

            if not message_text:
                return Response(
                    {'error': 'Message cannot be empty'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            message = SupportMessage.objects.create(
                ticket=ticket,
                sender=request.user,
                message=message_text,
                is_staff_reply=True,
            )

            return Response({
                'id': message.id,
                'message': message.message,
                'createdAt': message.created_at.isoformat(),
                'message': 'Reply added successfully',
            }, status=status.HTTP_201_CREATED)

        except SupportTicket.DoesNotExist:
            return Response(
                {'error': 'Ticket not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class AdminTicketUpdateStatusView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        from support.models import SupportTicket

        try:
            ticket = SupportTicket.objects.get(id=pk)
            new_status = request.data.get('status')
            new_priority = request.data.get('priority')
            updated = False

            if new_status:
                if new_status not in dict(SupportTicket.STATUS_CHOICES):
                    return Response(
                        {'error': 'Invalid status'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                ticket.status = new_status
                updated = True
                if new_status == 'closed' and not ticket.closed_at:
                    ticket.closed_at = timezone.now()

            if new_priority:
                if new_priority not in dict(SupportTicket.PRIORITY_CHOICES):
                    return Response(
                        {'error': 'Invalid priority'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                ticket.priority = new_priority
                updated = True

            if updated:
                ticket.save()

            return Response({
                'id': ticket.id,
                'status': ticket.status,
                'priority': ticket.priority,
                'message': 'Ticket updated successfully',
            })

        except SupportTicket.DoesNotExist:
            return Response(
                {'error': 'Ticket not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class AdminPermissionsView(APIView):
    """Get all roles with their permissions (RBAC)."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        # Define permission structure for each role
        permissions_structure = {
            'super-admin': {
                'id': 'super-admin',
                'name': 'Super Administrator',
                'description': 'Full platform access with all permissions',
                'isCustom': False,
                'permissionCount': 0,  # Will calculate below
                'permissions': [
                    # Users Management
                    {'id': 'users_create', 'name': 'Create User', 'category': 'Users Management', 'description': 'Create new users'},
                    {'id': 'users_edit', 'name': 'Edit User', 'category': 'Users Management', 'description': 'Edit user information'},
                    {'id': 'users_delete', 'name': 'Delete User', 'category': 'Users Management', 'description': 'Delete user accounts'},
                    {'id': 'users_view', 'name': 'View Users', 'category': 'Users Management', 'description': 'View all users'},
                    {'id': 'users_export', 'name': 'Export Users', 'category': 'Users Management', 'description': 'Export user data'},
                    # Academic Management
                    {'id': 'academic_create_exam', 'name': 'Create Exam', 'category': 'Academic Management', 'description': 'Create new exams'},
                    {'id': 'academic_edit_exam', 'name': 'Edit Exam', 'category': 'Academic Management', 'description': 'Edit exam details'},
                    {'id': 'academic_publish_exam', 'name': 'Publish Exam', 'category': 'Academic Management', 'description': 'Publish exams for students'},
                    {'id': 'academic_delete_exam', 'name': 'Delete Exam', 'category': 'Academic Management', 'description': 'Delete exams'},
                    {'id': 'academic_manage_questions', 'name': 'Manage Questions', 'category': 'Academic Management', 'description': 'Create, edit, delete questions'},
                    # Evaluations
                    {'id': 'eval_view', 'name': 'View Evaluations', 'category': 'Evaluations', 'description': 'View all evaluations'},
                    {'id': 'eval_assign', 'name': 'Assign Evaluator', 'category': 'Evaluations', 'description': 'Assign evaluators to submissions'},
                    {'id': 'eval_approve', 'name': 'Approve Evaluation', 'category': 'Evaluations', 'description': 'Approve evaluation results'},
                    {'id': 'eval_reject', 'name': 'Reject Evaluation', 'category': 'Evaluations', 'description': 'Reject evaluation results'},
                    # Marketplace
                    {'id': 'market_view_products', 'name': 'View Products', 'category': 'Marketplace', 'description': 'View all marketplace products'},
                    {'id': 'market_approve_product', 'name': 'Approve Product', 'category': 'Marketplace', 'description': 'Approve products for listing'},
                    {'id': 'market_remove_product', 'name': 'Remove Product', 'category': 'Marketplace', 'description': 'Remove products from marketplace'},
                    {'id': 'market_view_orders', 'name': 'View Orders', 'category': 'Marketplace', 'description': 'View all orders'},
                    {'id': 'market_process_payment', 'name': 'Process Payment', 'category': 'Marketplace', 'description': 'Process payments and refunds'},
                    # Analytics
                    {'id': 'analytics_view', 'name': 'View Analytics', 'category': 'Analytics', 'description': 'View platform analytics'},
                    {'id': 'analytics_export', 'name': 'Export Reports', 'category': 'Analytics', 'description': 'Export analytics reports'},
                    {'id': 'analytics_audit_logs', 'name': 'View Audit Logs', 'category': 'Analytics', 'description': 'View system audit logs'},
                    # Settings
                    {'id': 'settings_view', 'name': 'View Settings', 'category': 'Settings', 'description': 'View system settings'},
                    {'id': 'settings_modify', 'name': 'Modify Settings', 'category': 'Settings', 'description': 'Modify system settings'},
                    {'id': 'settings_manage_notif', 'name': 'Manage Notifications', 'category': 'Settings', 'description': 'Manage system notifications'},
                    # Administrators
                    {'id': 'admin_create', 'name': 'Create Admin', 'category': 'Administrators', 'description': 'Create new admin users'},
                    {'id': 'admin_edit', 'name': 'Edit Admin', 'category': 'Administrators', 'description': 'Edit admin information'},
                    {'id': 'admin_delete', 'name': 'Delete Admin', 'category': 'Administrators', 'description': 'Delete admin accounts'},
                    {'id': 'admin_assign_roles', 'name': 'Assign Roles', 'category': 'Administrators', 'description': 'Assign roles to users'},
                    # Support
                    {'id': 'support_view_tickets', 'name': 'View Tickets', 'category': 'Support', 'description': 'View support tickets'},
                    {'id': 'support_assign_ticket', 'name': 'Assign Ticket', 'category': 'Support', 'description': 'Assign tickets to staff'},
                    {'id': 'support_close_ticket', 'name': 'Close Ticket', 'category': 'Support', 'description': 'Close support tickets'},
                    {'id': 'support_respond', 'name': 'Respond to Ticket', 'category': 'Support', 'description': 'Respond to ticket messages'},
                ]
            },
            'admin': {
                'id': 'admin',
                'name': 'Administrator',
                'description': 'Can manage users, content, and settings',
                'isCustom': False,
                'permissionCount': 0,  # Will calculate below
                'permissions': [
                    # Users Management
                    {'id': 'users_create', 'name': 'Create User', 'category': 'Users Management', 'description': 'Create new users'},
                    {'id': 'users_edit', 'name': 'Edit User', 'category': 'Users Management', 'description': 'Edit user information'},
                    {'id': 'users_delete', 'name': 'Delete User', 'category': 'Users Management', 'description': 'Delete user accounts'},
                    {'id': 'users_view', 'name': 'View Users', 'category': 'Users Management', 'description': 'View all users'},
                    # Academic Management
                    {'id': 'academic_create_exam', 'name': 'Create Exam', 'category': 'Academic Management', 'description': 'Create new exams'},
                    {'id': 'academic_edit_exam', 'name': 'Edit Exam', 'category': 'Academic Management', 'description': 'Edit exam details'},
                    {'id': 'academic_manage_questions', 'name': 'Manage Questions', 'category': 'Academic Management', 'description': 'Create, edit, delete questions'},
                    # Evaluations
                    {'id': 'eval_view', 'name': 'View Evaluations', 'category': 'Evaluations', 'description': 'View all evaluations'},
                    {'id': 'eval_assign', 'name': 'Assign Evaluator', 'category': 'Evaluations', 'description': 'Assign evaluators to submissions'},
                    # Marketplace
                    {'id': 'market_view_products', 'name': 'View Products', 'category': 'Marketplace', 'description': 'View all marketplace products'},
                    {'id': 'market_approve_product', 'name': 'Approve Product', 'category': 'Marketplace', 'description': 'Approve products for listing'},
                    {'id': 'market_view_orders', 'name': 'View Orders', 'category': 'Marketplace', 'description': 'View all orders'},
                    # Analytics
                    {'id': 'analytics_view', 'name': 'View Analytics', 'category': 'Analytics', 'description': 'View platform analytics'},
                    # Settings
                    {'id': 'settings_view', 'name': 'View Settings', 'category': 'Settings', 'description': 'View system settings'},
                    # Support
                    {'id': 'support_view_tickets', 'name': 'View Tickets', 'category': 'Support', 'description': 'View support tickets'},
                    {'id': 'support_respond', 'name': 'Respond to Ticket', 'category': 'Support', 'description': 'Respond to ticket messages'},
                ]
            },
            'teacher': {
                'id': 'teacher',
                'name': 'Teacher',
                'description': 'Can create content and manage students',
                'isCustom': False,
                'permissionCount': 0,  # Will calculate below
                'permissions': [
                    # Academic Management
                    {'id': 'academic_create_exam', 'name': 'Create Exam', 'category': 'Academic Management', 'description': 'Create new exams'},
                    {'id': 'academic_edit_exam', 'name': 'Edit Exam', 'category': 'Academic Management', 'description': 'Edit exam details'},
                    {'id': 'academic_manage_questions', 'name': 'Manage Questions', 'category': 'Academic Management', 'description': 'Create, edit, delete questions'},
                    # Evaluations
                    {'id': 'eval_view', 'name': 'View Evaluations', 'category': 'Evaluations', 'description': 'View all evaluations'},
                ]
            },
            'student': {
                'id': 'student',
                'name': 'Student',
                'description': 'Can access learning materials and take exams',
                'isCustom': False,
                'permissionCount': 0,  # Will calculate below
                'permissions': [
                    # Academic Management (view only)
                    {'id': 'academic_view_exam', 'name': 'View Exam', 'category': 'Academic Management', 'description': 'View available exams'},
                    {'id': 'academic_take_exam', 'name': 'Take Exam', 'category': 'Academic Management', 'description': 'Take exams'},
                ]
            }
        }

        # Calculate permission counts
        for role_key in permissions_structure:
            permissions_structure[role_key]['permissionCount'] = len(permissions_structure[role_key]['permissions'])

        # Get all permission categories
        categories = set()
        for role_key in permissions_structure:
            for perm in permissions_structure[role_key]['permissions']:
                categories.add(perm['category'])

        roles = list(permissions_structure.values())

        return Response({
            'roles': roles,
            'totalRoles': len(roles),
            'totalPermissions': sum(r['permissionCount'] for r in roles),
            'categories': sorted(list(categories)),
        })


class AdminSettingsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from core.models import AdminSettings

        try:
            settings = AdminSettings.get_settings()

            return Response({
                'settings': {
                    'platform': {
                        'name': settings.platform_name,
                        'logoUrl': settings.platform_logo_url,
                        'description': settings.platform_description,
                        'timezone': settings.timezone,
                        'language': settings.language,
                    },
                    'email': {
                        'smtpHost': settings.email_smtp_host,
                        'smtpPort': settings.email_smtp_port,
                        'smtpUser': settings.email_smtp_user,
                        'fromAddress': settings.email_from_address,
                        'fromName': settings.email_from_name,
                    },
                    'notifications': {
                        'enabled': settings.notifications_enabled,
                        'enableEmail': settings.enable_email_notifications,
                        'enableInApp': settings.enable_in_app_notifications,
                        'enablePush': settings.enable_push_notifications,
                    },
                    'security': {
                        'passwordMinLength': settings.password_min_length,
                        'passwordRequireUppercase': settings.password_require_uppercase,
                        'passwordRequireNumbers': settings.password_require_numbers,
                        'passwordRequireSpecialChars': settings.password_require_special_chars,
                        'sessionTimeoutMinutes': settings.session_timeout_minutes,
                        'enableTwoFactorAuth': settings.enable_two_factor_auth,
                        'maxLoginAttempts': settings.max_login_attempts,
                    },
                    'features': {
                        'enableAiTutor': settings.enable_ai_tutor,
                        'enableMarketplace': settings.enable_marketplace,
                        'enableGamification': settings.enable_gamification,
                        'enableStudyPlans': settings.enable_study_plans,
                        'enforceSubscriptionAccess': settings.enforce_subscription_access,
                    },
                    'aiTutor': {
                        'dailyMessageLimit': settings.ai_tutor_daily_message_limit,
                    },
                },
                'updatedAt': settings.updated_at.isoformat(),
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def put(self, request):
        from core.models import AdminSettings

        try:
            settings = AdminSettings.get_settings()

            # Platform settings
            if 'platform' in request.data:
                platform = request.data['platform']
                settings.platform_name = platform.get('name', settings.platform_name)
                settings.platform_logo_url = platform.get('logoUrl', settings.platform_logo_url)
                settings.platform_description = platform.get('description', settings.platform_description)
                settings.timezone = platform.get('timezone', settings.timezone)
                settings.language = platform.get('language', settings.language)

            # Email settings
            if 'email' in request.data:
                email = request.data['email']
                settings.email_smtp_host = email.get('smtpHost', settings.email_smtp_host)
                settings.email_smtp_port = email.get('smtpPort', settings.email_smtp_port)
                settings.email_smtp_user = email.get('smtpUser', settings.email_smtp_user)
                settings.email_from_address = email.get('fromAddress', settings.email_from_address)
                settings.email_from_name = email.get('fromName', settings.email_from_name)

            # Notification settings
            if 'notifications' in request.data:
                notif = request.data['notifications']
                settings.notifications_enabled = notif.get('enabled', settings.notifications_enabled)
                settings.enable_email_notifications = notif.get('enableEmail', settings.enable_email_notifications)
                settings.enable_in_app_notifications = notif.get('enableInApp', settings.enable_in_app_notifications)
                settings.enable_push_notifications = notif.get('enablePush', settings.enable_push_notifications)

            # Security settings
            if 'security' in request.data:
                security = request.data['security']
                settings.password_min_length = security.get('passwordMinLength', settings.password_min_length)
                settings.password_require_uppercase = security.get('passwordRequireUppercase', settings.password_require_uppercase)
                settings.password_require_numbers = security.get('passwordRequireNumbers', settings.password_require_numbers)
                settings.password_require_special_chars = security.get('passwordRequireSpecialChars', settings.password_require_special_chars)
                settings.session_timeout_minutes = security.get('sessionTimeoutMinutes', settings.session_timeout_minutes)
                settings.enable_two_factor_auth = security.get('enableTwoFactorAuth', settings.enable_two_factor_auth)
                settings.max_login_attempts = security.get('maxLoginAttempts', settings.max_login_attempts)

            # Feature flags
            if 'features' in request.data:
                features = request.data['features']
                settings.enable_ai_tutor = features.get('enableAiTutor', settings.enable_ai_tutor)
                settings.enable_marketplace = features.get('enableMarketplace', settings.enable_marketplace)
                settings.enable_gamification = features.get('enableGamification', settings.enable_gamification)
                settings.enable_study_plans = features.get('enableStudyPlans', settings.enable_study_plans)
                settings.enforce_subscription_access = features.get('enforceSubscriptionAccess', settings.enforce_subscription_access)

            # AI Tutor configuration
            if 'aiTutor' in request.data:
                ai_tutor = request.data['aiTutor']
                if 'dailyMessageLimit' in ai_tutor:
                    limit = ai_tutor['dailyMessageLimit']
                    if not isinstance(limit, int) or limit < 1:
                        return Response(
                            {'error': 'aiTutor.dailyMessageLimit must be a positive integer'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    settings.ai_tutor_daily_message_limit = limit

            settings.updated_by = request.user
            settings.save()

            return Response({
                'message': 'Settings updated successfully',
                'updatedAt': settings.updated_at.isoformat(),
            })

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class AdminPositionsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            positions = Position.objects.all().values(
                'id', 'name', 'code', 'description', 'category', 'order', 'is_active', 'created_at', 'updated_at'
            ).order_by('order', 'name')

            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
            search = request.query_params.get('search', '')

            if search:
                positions = positions.filter(
                    Q(name__icontains=search) | Q(code__icontains=search) | Q(category__icontains=search)
                )

            paginator = Paginator(list(positions), page_size)
            page_obj = paginator.get_page(page)

            return Response({
                'results': list(page_obj.object_list),
                'count': paginator.count,
                'page': page,
                'page_size': page_size,
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def post(self, request):
        try:
            name = request.data.get('name', '').strip()
            if not name:
                return Response({'error': 'Name is required'}, status=status.HTTP_400_BAD_REQUEST)

            position = Position.objects.create(
                name=name,
                code=request.data.get('code', '').strip(),
                category=request.data.get('category', '').strip(),
                order=int(request.data.get('order', 0)),
                is_active=bool(request.data.get('is_active', True))
            )

            return Response({
                'id': position.id,
                'name': position.name,
                'code': position.code,
                'category': position.category,
                'order': position.order,
                'is_active': position.is_active,
                'created_at': position.created_at,
                'updated_at': position.updated_at,
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class AdminPositionDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        try:
            position = Position.objects.get(pk=pk)
            return Response({
                'id': position.id,
                'name': position.name,
                'code': position.code,
                'description': position.description,
                'category': position.category,
                'order': position.order,
                'is_active': position.is_active,
                'created_at': position.created_at,
                'updated_at': position.updated_at,
            })
        except Position.DoesNotExist:
            return Response({'error': 'Position not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        try:
            position = Position.objects.get(pk=pk)
            name = request.data.get('name', '').strip()
            if not name:
                return Response({'error': 'Name is required'}, status=status.HTTP_400_BAD_REQUEST)

            position.name = name
            if 'code' in request.data:
                position.code = request.data.get('code', '').strip()
            if 'category' in request.data:
                position.category = request.data.get('category', '').strip()
            if 'description' in request.data:
                position.description = request.data.get('description', '').strip()
            if 'order' in request.data:
                position.order = int(request.data.get('order', 0))
            if 'is_active' in request.data:
                position.is_active = bool(request.data.get('is_active', True))

            position.save()

            return Response({
                'id': position.id,
                'name': position.name,
                'code': position.code,
                'description': position.description,
                'category': position.category,
                'order': position.order,
                'is_active': position.is_active,
                'created_at': position.created_at,
                'updated_at': position.updated_at,
            })
        except Position.DoesNotExist:
            return Response({'error': 'Position not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        return self.put(request, pk)

    def delete(self, request, pk):
        try:
            position = Position.objects.get(pk=pk)
            position.delete()
            return Response({'success': True, 'message': 'Position deleted successfully'})
        except Position.DoesNotExist:
            return Response({'error': 'Position not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminTagsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            include_inactive = request.query_params.get('include_inactive') == '1'
            tags = Tag.objects.all()
            if not include_inactive:
                tags = tags.filter(is_active=True)
            # Real usage count from the actual Question<->Tag relationship -
            # never a placeholder number.
            tags = tags.annotate(question_count=Count('questions', distinct=True)).order_by('name')

            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
            search = request.query_params.get('search', '')

            if search:
                tags = tags.filter(
                    Q(name__icontains=search) | Q(slug__icontains=search)
                )

            values = tags.values(
                'id', 'name', 'slug', 'description', 'color', 'is_active',
                'created_at', 'updated_at', 'question_count',
            )
            paginator = Paginator(list(values), page_size)
            page_obj = paginator.get_page(page)

            return Response({
                'results': list(page_obj.object_list),
                'count': paginator.count,
                'page': page,
                'page_size': page_size,
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def post(self, request):
        try:
            from django.utils.text import slugify
            name = request.data.get('name', '').strip()
            if not name:
                return Response({'error': 'Name is required'}, status=status.HTTP_400_BAD_REQUEST)

            tag = Tag.objects.create(
                name=name,
                slug=slugify(name),
                description=request.data.get('description', ''),
                color=request.data.get('color', '#6366f1'),
                is_active=True
            )

            return Response({
                'id': tag.id,
                'name': tag.name,
                'slug': tag.slug,
                'description': tag.description,
                'color': tag.color,
                'is_active': tag.is_active,
                'question_count': 0,
                'created_at': tag.created_at,
                'updated_at': tag.updated_at,
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class AdminTagDetailView(APIView):
    """Retrieve, update, or delete a single Tag.

    Delete is a hard delete of the Tag row only - Django simply drops the
    join rows in the Question<->Tag through table; Questions, Collections,
    ExaminationQuestion and Practice history are never touched.
    """
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        return Tag.objects.annotate(
            question_count=Count('questions', distinct=True)
        ).filter(pk=pk).first()

    def _serialize(self, tag):
        return {
            'id': tag.id,
            'name': tag.name,
            'slug': tag.slug,
            'description': tag.description,
            'color': tag.color,
            'is_active': tag.is_active,
            'question_count': tag.question_count,
            'created_at': tag.created_at,
            'updated_at': tag.updated_at,
        }

    def get(self, request, pk):
        tag = self._get(pk)
        if not tag:
            return Response({'error': 'Tag not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self._serialize(tag))

    def patch(self, request, pk):
        tag = self._get(pk)
        if not tag:
            return Response({'error': 'Tag not found.'}, status=status.HTTP_404_NOT_FOUND)

        if 'name' in request.data:
            name = (request.data.get('name') or '').strip()
            if not name:
                return Response({'error': 'Name cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)
            tag.name = name
            if request.data.get('regenerate_slug'):
                from django.utils.text import slugify
                tag.slug = slugify(name)
        if 'slug' in request.data and request.data.get('slug'):
            tag.slug = request.data['slug'].strip()
        if 'description' in request.data:
            tag.description = request.data.get('description') or ''
        if 'color' in request.data and request.data.get('color'):
            tag.color = request.data['color']
        if 'is_active' in request.data:
            tag.is_active = bool(request.data['is_active'])

        tag.save()
        tag.question_count = tag.questions.count()
        return Response(self._serialize(tag))

    def delete(self, request, pk):
        tag = Tag.objects.filter(pk=pk).first()
        if not tag:
            return Response({'error': 'Tag not found.'}, status=status.HTTP_404_NOT_FOUND)
        tag.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminStorageHealthView(APIView):
    """Admin-only check of whether Google Drive media storage is configured
    and reachable. Never returns tokens/secrets - only connection status and
    the account's own quota numbers."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.conf import settings
        from core import google_drive

        if not google_drive.is_configured():
            return Response({
                'provider': 'google_drive',
                'configured': False,
                'connected': False,
            })

        try:
            creds = google_drive.get_credentials(force_refresh=True)
            from googleapiclient.discovery import build
            service = build('drive', 'v3', credentials=creds, cache_discovery=False)
            about = service.about().get(fields='user(emailAddress), storageQuota').execute()
        except google_drive.GoogleDriveError as e:
            return Response({
                'provider': 'google_drive',
                'configured': True,
                'connected': False,
                'error': str(e),
            })
        except Exception:
            return Response({
                'provider': 'google_drive',
                'configured': True,
                'connected': False,
                'error': 'Unexpected error contacting Google Drive.',
            })

        quota = about.get('storageQuota', {})
        return Response({
            'provider': 'google_drive',
            'configured': True,
            'connected': True,
            'root_folder': 'LoksewaAI',
            'root_folder_id': settings.GOOGLE_DRIVE_ROOT_FOLDER_ID,
            'account_email': about.get('user', {}).get('emailAddress'),
            'storage_used_bytes': int(quota.get('usage', 0)),
            'storage_limit_bytes': int(quota.get('limit', 0)) if quota.get('limit') else None,
        })
