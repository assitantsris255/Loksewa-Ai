import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from datetime import timedelta
from .models import User

logger = logging.getLogger(__name__)


def _access_token_for(user):
    """Mints an access token whose lifetime comes from
    AdminSettings.session_timeout_minutes (Admin Settings > Security),
    for the views here that mint tokens manually instead of going through
    CustomTokenObtainPairSerializer."""
    from .models import AdminSettings
    minutes = AdminSettings.get_settings().session_timeout_minutes
    access = AccessToken.for_user(user)
    access.set_exp(lifetime=timedelta(minutes=minutes))
    return str(access)

class SignupRequestOTPView(APIView):
    """POST /api/auth/signup/request-otp/ - body: {email}. Resends a 6-digit
    verification code (via core.email_service / Resend SMTP) for an ALREADY-registered-but-unverified
    account. Registration itself (StudentSignupView) sends the first code
    automatically, so this is only for "I didn't get it" / "it expired"."""
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get('email') or '').strip()
        if not email:
            return Response({'error': 'Please provide your email address.'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email, role='student').first()
        if not user:
            return Response(
                {'error': 'No pending registration found for this email. Please register first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from support.models import StudentProfile
        profile, _ = StudentProfile.objects.get_or_create(user=user)
        if profile.is_verified:
            return Response({'error': 'Email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        from .otp import create_and_send_otp, OTPError
        try:
            create_and_send_otp(email, 'signup')
        except OTPError as e:
            return Response({'error': str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        from administration.models import AuditLog
        AuditLog.objects.create(
            actor=None, action='REGISTRATION_OTP_RESENT',
            entity_type='User', entity_id=str(user.id), details={'email': email},
        )
        return Response({'detail': 'Verification code sent to your email.'})


class StudentSignupView(APIView):
    """POST /api/auth/signup/ - creates the account immediately as pending
    verification (StudentProfile.is_verified=False) and sends the first OTP;
    it does NOT verify a code or issue tokens itself. That split is what
    lets admins see and assist a registration that never received its email,
    which isn't possible if the account only starts existing once an OTP is
    already confirmed. See VerifyEmailOTPView for the next step."""
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        email = (request.data.get('email') or '').strip()
        password = request.data.get('password')
        full_name = (request.data.get('name') or '').strip()
        phone = (request.data.get('mobile') or request.data.get('phone') or '').strip()
        permanent_district = (request.data.get('permanent_district') or '').strip()
        permanent_local_level = (request.data.get('permanent_local_level') or '').strip()
        exam_category_id = request.data.get('exam_category_id')
        exam_position_id = request.data.get('exam_position_id')  # optional - Level or Service/Faculty, whichever is deepest chosen
        referral_code = request.data.get('ref', '').strip()
        plan_id = request.data.get('plan_id')
        course_id = request.data.get('course_id')

        missing = []
        if not username and not email: missing.append('username')
        if not email: missing.append('email')
        if not password: missing.append('password')
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

        from django.core.validators import validate_email
        try:
            validate_email(email)
        except DjangoValidationError:
            return Response({'error': 'Please enter a valid email address.'}, status=status.HTTP_400_BAD_REQUEST)

        from .validators import is_valid_nepal_phone, is_valid_nepal_district
        if not is_valid_nepal_phone(phone):
            return Response({'error': 'Please enter a valid 10-digit Nepali mobile number.'}, status=status.HTTP_400_BAD_REQUEST)

        if not is_valid_nepal_district(permanent_district):
            return Response({'error': 'Please select a valid district of Nepal.'}, status=status.HTTP_400_BAD_REQUEST)

        if not username and email:
            import re
            base_user = re.sub(r'[^a-zA-Z0-9_]', '', email.split('@')[0]) or 'student'
            candidate = base_user
            idx = 1
            while User.objects.filter(username=candidate).exists():
                candidate = f"{base_user}_{idx}"
                idx += 1
            username = candidate

        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already exists.'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email__iexact=email).exists():
            return Response({'error': 'Email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            django_validate_password(password)
        except DjangoValidationError as e:
            return Response({'error': ' '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        from exams.models import ExamCategory, Exam
        try:
            exam_category = ExamCategory.objects.get(id=exam_category_id, is_active=True)
        except (ExamCategory.DoesNotExist, ValueError):
            return Response({'error': 'Please select what you are preparing for.'}, status=status.HTTP_400_BAD_REQUEST)

        exam_position = None
        if exam_position_id:
            try:
                exam_position = Exam.objects.get(id=exam_position_id, is_active=True, category=exam_category)
            except (Exam.DoesNotExist, ValueError):
                return Response({'error': 'Invalid exam selection.'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate Referral Code BEFORE creating user
        if referral_code:
            from gamification.models import GamificationProfile
            if not GamificationProfile.objects.filter(referral_code=referral_code).exists():
                return Response({'error': 'Invalid referral code.'}, status=status.HTTP_400_BAD_REQUEST)

        first_name, _, last_name = full_name.partition(' ')

        target_course = None
        if course_id:
            from courses.models import Course
            try:
                target_course = Course.objects.filter(id=course_id).first()
                if target_course and not exam_position and target_course.exam:
                    exam_position = target_course.exam
                if target_course and not exam_category and target_course.exam and target_course.exam.category:
                    exam_category = target_course.exam.category
            except (ValueError, TypeError):
                target_course = None

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username, email=email, password=password, role='student',
                    first_name=first_name[:150], last_name=last_name[:150],
                )

                from support.models import StudentProfile, NotificationPreference
                StudentProfile.objects.create(
                    user=user, phone=phone,
                    permanent_district=permanent_district, permanent_local_level=permanent_local_level,
                    target_category=exam_category, target_position=exam_position, target_course=target_course,
                    is_verified=False,
                )
                NotificationPreference.objects.create(user=user)

                # Register Referral and gamification profile
                if referral_code:
                    from gamification.services import register_referral
                    register_referral(user, referral_code)
                else:
                    from gamification.models import GamificationProfile
                    GamificationProfile.objects.create(user=user)

                if target_course:
                    from courses.models import CourseApplication
                    CourseApplication.objects.create(
                        student=user,
                        course=target_course,
                        subscription_payment=None,
                        status='pending'
                    )

                    from core.notification_service import NotificationService
                    NotificationService.notify_admins(
                        notif_type='course_application',
                        title='New Course Application',
                        message=f"New student {username} applied for '{target_course.title}' during registration.",
                        action_url='/admin-dashboard/applications',
                    )

                from administration.models import AuditLog
                AuditLog.objects.create(
                    actor=None, action='REGISTRATION_CREATED',
                    entity_type='User', entity_id=str(user.id),
                    details={'email': email, 'username': username},
                )
        except Exception as e:
            logger.exception("Failed to process registration for email=%s", email)
            return Response({'error': 'Registration failed due to an internal error. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Admins should see this pending registration right away, and the
        # student should get their first code - neither is critical enough
        # to roll back a successfully-created account if it fails.
        from core.notification_service import NotificationService
        NotificationService.notify_admins(
            notif_type='new_registration',
            title='New Student Registered',
            message=f"{username} ({email}) just registered and is pending email verification.",
            action_url='/admin-dashboard/students/pending-verification',
        )
        from .otp import create_and_send_otp, OTPError
        try:
            create_and_send_otp(email, 'signup')
            from administration.models import AuditLog
            AuditLog.objects.create(
                actor=None, action='REGISTRATION_OTP_GENERATED',
                entity_type='User', entity_id=str(user.id), details={'email': email},
            )
        except OTPError:
            logger.warning("Could not send initial signup OTP for email=%s", email)

        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'pending_verification': True,
            'detail': 'Registration successful. Please check your email for a verification code.',
        }, status=status.HTTP_201_CREATED)


class VerifyEmailOTPView(APIView):
    """POST /api/auth/verify-email-otp/ - body: {email, otp}. Confirms the
    code StudentSignupView emailed, flips StudentProfile.is_verified, and
    (only here, for the normal happy path) logs the student straight in."""
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get('email') or '').strip()
        otp = (request.data.get('otp') or '').strip()
        if not email or not otp:
            return Response({'error': 'Please provide your email and the verification code.'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email, role='student').first()
        if not user:
            return Response({'error': 'No pending registration found for this email.'}, status=status.HTTP_400_BAD_REQUEST)

        from support.models import StudentProfile
        profile, _ = StudentProfile.objects.get_or_create(user=user)
        if profile.is_verified:
            return Response({'error': 'This account is already verified. Please log in.'}, status=status.HTTP_400_BAD_REQUEST)

        from .otp import verify_otp, OTPError
        from administration.models import AuditLog
        try:
            verify_otp(email, 'signup', otp)
        except OTPError as e:
            AuditLog.objects.create(
                actor=None, action='REGISTRATION_OTP_VERIFY_FAILED',
                entity_type='User', entity_id=str(user.id), details={'email': email, 'reason': str(e)},
            )
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        profile.is_verified = True
        profile.verified_at = timezone.now()
        profile.save(update_fields=['is_verified', 'verified_at'])
        AuditLog.objects.create(
            actor=None, action='REGISTRATION_OTP_VERIFIED',
            entity_type='User', entity_id=str(user.id), details={'email': email},
        )

        update_last_login(None, user)
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': _access_token_for(user),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
            }
        }, status=status.HTTP_200_OK)


class VerifyRecoveryCodeView(APIView):
    """POST /api/auth/verify-recovery-code/ - body: {email, code}. Confirms
    an admin-generated recovery code (see administration.registration_views.
    AdminGenerateRecoveryCodeView) for a student who never got their email
    OTP. Deliberately does NOT issue tokens - this only flips is_verified;
    the student then logs in the normal way, same as anyone else. That's the
    line between "recovery verification" and "a second login system"."""
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get('email') or '').strip()
        code = (request.data.get('code') or '').strip()
        if not email or not code:
            return Response({'error': 'Please provide your email and the recovery code.'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email, role='student').first()
        if not user:
            return Response({'error': 'No pending registration found for this email.'}, status=status.HTTP_400_BAD_REQUEST)

        from support.models import StudentProfile
        profile, _ = StudentProfile.objects.get_or_create(user=user)
        if profile.is_verified:
            return Response({'error': 'This account is already verified. Please log in.'}, status=status.HTTP_400_BAD_REQUEST)

        from .otp import verify_otp, OTPError
        from .models import EmailOTP
        from administration.models import AuditLog
        try:
            verify_otp(email, 'admin_recovery', code)
        except OTPError as e:
            AuditLog.objects.create(
                actor=None, action='RECOVERY_VERIFY_FAILED',
                entity_type='User', entity_id=str(user.id), details={'email': email, 'reason': str(e)},
            )
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        profile.is_verified = True
        profile.verified_at = timezone.now()
        profile.save(update_fields=['is_verified', 'verified_at'])

        used_otp = EmailOTP.objects.filter(
            email=email.lower(), purpose='admin_recovery', is_used=True
        ).order_by('-created_at').first()
        AuditLog.objects.create(
            actor=None, action='RECOVERY_VERIFIED',
            entity_type='User', entity_id=str(user.id),
            details={'email': email, 'generated_by': used_otp.generated_by_id if used_otp else None},
        )

        return Response({
            'verified': True,
            'detail': 'Your account is verified. Please log in.',
        }, status=status.HTTP_200_OK)


class UserMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            'id': user.id,
            'username': user.username,
            'name': f"{user.first_name} {user.last_name}".strip() or user.username,
            'email': user.email,
            'role': user.role,
            'is_active': user.is_active,
            'avatar': user.avatar,
        })


class AdminLoginView(APIView):
    """
    Admin-specific login endpoint.
    Validates credentials AND verifies the user has an admin role.
    Returns JWT tokens only for admin/super-admin users.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')

        if not username or not password:
            return Response(
                {'detail': 'Please provide both username/email and password.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .account_lockout import (
            find_user_by_username_or_email, is_locked, lockout_remaining_minutes,
            record_failed_attempt, record_successful_login,
        )

        looked_up_user = find_user_by_username_or_email(username)
        if is_locked(looked_up_user):
            return Response(
                {'detail': f'Too many failed attempts. Try again in {lockout_remaining_minutes(looked_up_user)} minute(s).'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Allow login by email or username
        user = authenticate(request, username=username, password=password)

        # If authentication by username failed, try by email
        if user is None:
            from core.models import User
            try:
                email_user = User.objects.get(email=username)
                user = authenticate(request, username=email_user.username, password=password)
            except User.DoesNotExist:
                pass

        if user is None:
            if looked_up_user:
                record_failed_attempt(looked_up_user)
            return Response(
                {'detail': 'Invalid credentials. Please check your username/email and password.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        record_successful_login(user)

        if not user.is_active:
            return Response(
                {'detail': 'This account has been deactivated. Please contact support.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.role not in ('admin', 'super-admin'):
            return Response(
                {'detail': 'This login is restricted to administrators only.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        from .models import AdminSettings
        if AdminSettings.get_settings().enable_two_factor_auth and user.is_2fa_enabled:
            from .two_factor_views import TwoFactorPendingToken
            pending = TwoFactorPendingToken.for_user(user)
            return Response({
                'twoFactorRequired': True,
                'pendingToken': str(pending),
            })

        # Generate JWT tokens
        update_last_login(None, user)
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': _access_token_for(user),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'name': f"{user.first_name} {user.last_name}".strip() or user.username,
                'email': user.email,
                'role': user.role,
            }
        })


class AuthLogoutView(APIView):
    """
    Logout endpoint — blacklists the refresh token so it cannot be reused.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass  # Token may already be invalid/blacklisted
        return Response({'detail': 'Logged out successfully.'}, status=status.HTTP_200_OK)


class ForgotPasswordView(APIView):
    """
    Requests a password-reset verification code via core.email_service (Resend SMTP). Always
    responds with the same generic message regardless of whether the email
    exists, so this endpoint can't be used to enumerate registered accounts.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip()
        if not email:
            return Response(
                {'detail': 'Please provide your email address.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        generic_response = {
            'detail': 'If an account exists for that email, a verification code has been sent.',
            'configured': True,
        }

        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is None:
            # Deliberately identical to the success path - see docstring.
            return Response(generic_response, status=status.HTTP_200_OK)

        from .otp import create_and_send_otp, OTPError
        try:
            create_and_send_otp(email, 'password_reset')
        except OTPError:
            # Rate-limited resend - still return the generic response so
            # this endpoint can't be used to enumerate accounts or probe
            # timing.
            logger.info('Password reset OTP resend throttled for email=%s', email)

        return Response(generic_response, status=status.HTTP_200_OK)


class ResetPasswordConfirmView(APIView):
    """Completes a password reset given the OTP emailed by ForgotPasswordView."""
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip()
        otp = request.data.get('otp', '').strip()
        new_password = request.data.get('password', '')

        if not email or not otp or not new_password:
            return Response(
                {'detail': 'email, otp, and password are all required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is None:
            return Response({'detail': 'Invalid or expired code.'}, status=status.HTTP_400_BAD_REQUEST)

        from .otp import verify_otp, OTPError
        try:
            verify_otp(email, 'password_reset', otp)
        except OTPError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            django_validate_password(new_password, user=user)
        except DjangoValidationError as e:
            return Response({'detail': ' '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password'])

        return Response({'detail': 'Your password has been reset. You can now sign in.'}, status=status.HTTP_200_OK)


def invalidate_student_dashboard(user_id):
    if not user_id:
        return
    from django.core.cache import cache
    try:
        cache.delete(f'student_dashboard:{user_id}')
        cache.delete(f'student_dashboard_v2:{user_id}:')
    except Exception:
        pass


class StudentDashboardView(APIView):
    """
    Consolidated dashboard data for the authenticated student.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        course_id_param = request.query_params.get('course_id') or ''

        from django.core.cache import cache
        cache_key = f'student_dashboard_v2:{user.id}:{course_id_param}'
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)
        except Exception:
            pass
        
        has_avatar = bool(hasattr(user, 'avatar') and user.avatar)
        has_phone = bool(getattr(user, 'phone_number', '') or getattr(user, 'phone', ''))
        has_name = bool(user.first_name and user.last_name)
        completion_points = 50 + (20 if has_avatar else 0) + (15 if has_phone else 0) + (15 if has_name else 0)

        # Profile
        profile_data = {
            "name": f"{user.first_name} {user.last_name}".strip() or user.username,
            "avatar": user.avatar if has_avatar else None,
            "targetPosition": getattr(user, 'role', 'Student').replace("-", " ").title(),
            "completionPercentage": completion_points,
            "phone": getattr(user, 'phone_number', '') or getattr(user, 'phone', '')
        }

        # Stats
        from analytics.services.analytics_service import AnalyticsService
        course_id_param = request.query_params.get('course_id')
        overview = AnalyticsService.get_overview(user, course_id=course_id_param)
        
        study_time_hours = overview.get("total_study_time_mins", 0) // 60
        study_time_mins = overview.get("total_study_time_mins", 0) % 60

        stats_data = {
            "totalExams": overview.get("total_available_exams", 0),
            "completedExams": overview.get("model_exams_taken", 0),
            "averageScore": overview.get("overall_accuracy", 0),
            "bestScore": overview.get("overall_accuracy", 0), 
            "accuracy": overview.get("overall_accuracy", 0),
            "questionsAttempted": overview.get("questions_solved", 0),
            "studyStreak": overview.get("study_streak", 0),
            "studyTime": f"{study_time_hours}h {study_time_mins}m",
            "progress": overview.get("journey_progress", 0)
        }

        # Continue Learning
        continue_learning = None
        active_course = overview.get("active_course")
        if active_course:
            course_name = active_course.get("name", "Active Course")
            course_slug = active_course.get("slug")
            
            continue_learning = {
                "id": active_course.get("id", 0),
                "type": "practice",
                "title": f"Continue {course_name}",
                "progress": overview.get("journey_progress", 0),
                "url": f"/student/courses/{course_slug}" if course_slug else "/student/practice"
            }

        # Recent Exams
        recent_exams_data = []
        try:
            from exams.models import ExaminationAttempt
            recent_attempts = ExaminationAttempt.objects.filter(
                student=user, status='submitted'
            ).select_related('examination').order_by('-started_at')[:5]
            
            for attempt in recent_attempts:
                recent_exams_data.append({
                    "id": attempt.id,
                    "title": attempt.examination.title if attempt.examination else "Examination",
                    "date": attempt.started_at.isoformat() if attempt.started_at else "",
                    "score": attempt.score,
                    "percentage": attempt.percentage
                })
                
        except Exception as e:
            logger.error(f"Error fetching recent exams for dashboard: {e}")

        # Purchases and Subject Performance: kept in the response shape for
        # API-contract stability, but their queries (CourseApplication fetch,
        # PracticeSession aggregate) are skipped - confirmed unused by every
        # frontend consumer of this endpoint (student/page.tsx,
        # student/purchases/page.tsx, student/layout.tsx all leave these two
        # fields untouched), so they were pure wasted round trips on a
        # critical/blocking path against a remote DB where each round trip
        # measured ~250-400ms. Restore the real computation here if a future
        # UI actually needs them.
        purchases_data = []
        formatted_subject_performance = []

        # Today's Plan
        todays_plan = []
        try:
            from study_plan.models import StudyTask
            from django.utils import timezone
            
            today = timezone.localdate()
            tasks = StudyTask.objects.filter(
                study_plan__student=user,
                date=today
            ).order_by('created_at')[:5]
            
            for task in tasks:
                todays_plan.append({
                    "id": task.id,
                    "title": task.title,
                    "type": "exam" if task.task_type == "MODEL_EXAM" else "practice",
                    "completed": task.status == 'COMPLETED',
                    "duration": task.duration_minutes
                })
        except Exception as e:
            logger.error(f"Error fetching today's plan for dashboard: {e}")

        # Package/subscription status - lets the frontend render the locked
        # dashboard state without a second round-trip. Reuses
        # subscriptions.access (the same check HasActiveSubscription enforces
        # server-side) so this can never drift from what's actually allowed.
        package_data = _get_package_status(user)

        data = {
            "profile": profile_data,
            "stats": stats_data,
            "continueLearning": continue_learning,
            # Same active_course the overview already computed (no extra
            # query) - lets the dashboard drop its separate analytics fetch.
            "activeCourse": active_course,
            "todaysPlan": todays_plan,
            "recentExams": recent_exams_data,
            "purchases": purchases_data,
            "supportTickets": [],
            "subjectPerformance": formatted_subject_performance,
            "package": package_data,
        }

        try:
            cache.set(cache_key, data, 45)
        except Exception:
            pass

        return Response(data)


def invalidate_package_status(user_id):
    if not user_id:
        return
    from django.core.cache import cache
    try:
        cache.delete(f'pkg_status:{user_id}')
    except Exception:
        pass


def _get_package_status(user):
    """
    Shared by StudentDashboardView and StudentPackageStatusView so the
    latter (a lightweight navigation-guard check - see student/layout.tsx)
    never has to pull in the full dashboard's profile/stats/activity
    computation just to read a couple of package-lock booleans.
    Fast locmem cache with 30s TTL collapses duplicate queries from login,
    context, and dashboard requests.
    """
    if not user or not user.is_authenticated:
        from .models import AdminSettings
        return {
            "enforcementEnabled": AdminSettings.get_settings().enforce_subscription_access,
            "hasActivePackage": False,
            "isAdminGranted": False,
            "planName": None,
            "status": None,
            "expiryDate": None,
            "remainingDays": None,
            "latestPayment": None,
        }

    from django.core.cache import cache
    cache_key = f'pkg_status:{user.id}'
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    except Exception:
        pass

    from .models import AdminSettings
    from subscriptions.access import get_active_subscription, has_admin_granted_access
    from subscriptions.models import SubscriptionPayment

    active_subscription = get_active_subscription(user)
    is_admin_granted = has_admin_granted_access(user)
    latest_payment = SubscriptionPayment.objects.filter(student=user).select_related('plan').order_by('-submitted_at').first()
    latest_payment_data = None
    if latest_payment and not active_subscription:
        # Only surface the latest payment while there's no active package
        # to explain - once a package is active, pending/rejected history
        # from before it belongs on the purchases/history page, not here.
        latest_payment_data = {
            "status": latest_payment.status,
            "rejectionReason": latest_payment.rejection_reason or None,
            "planName": latest_payment.plan.name,
            "amount": str(latest_payment.amount),
            "submittedAt": latest_payment.submitted_at.isoformat() if latest_payment.submitted_at else None,
        }

    result = {
        "enforcementEnabled": AdminSettings.get_settings().enforce_subscription_access,
        "hasActivePackage": active_subscription is not None or is_admin_granted,
        "isAdminGranted": is_admin_granted,
        "planName": active_subscription.plan.name if active_subscription else None,
        "status": active_subscription.status if active_subscription else None,
        "expiryDate": active_subscription.expiry_date.isoformat() if active_subscription else None,
        "remainingDays": max((active_subscription.expiry_date - timezone.now()).days, 0) if active_subscription else None,
        "latestPayment": latest_payment_data,
    }
    try:
        cache.set(cache_key, result, 30)
    except Exception:
        pass
    return result


class StudentPackageStatusView(APIView):
    """
    GET /api/dashboard/package-status/

    Just the package-lock fields from StudentDashboardView, for callers that
    only need to know "is this student locked out" - student/layout.tsx's
    navigation guard was calling the full /api/dashboard/ (profile + cached-
    but-still-real stats + today's plan + recent exams + purchases +
    subject performance - 16 queries) on every route change within /student/*
    purely to read two booleans here. That guard now hits this endpoint
    instead, cutting an unrelated ~3s+ round trip out of ordinary navigation.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"package": _get_package_status(request.user)})

class SocialLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        provider = request.data.get('provider')
        token = request.data.get('token')
        additional_data = request.data.get('additional_data', {})

        if not provider or not token:
            return Response({"detail": "Provider and token are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from core.social_auth import SocialAuthService

            if provider == 'google':
                provider_data = SocialAuthService.verify_google_token(token)
            elif provider == 'facebook':
                provider_data = SocialAuthService.verify_facebook_token(token)
            elif provider == 'apple':
                provider_data = SocialAuthService.verify_apple_token(token)
            else:
                return Response({"detail": "Invalid provider."}, status=status.HTTP_400_BAD_REQUEST)

            user, is_new_user = SocialAuthService.get_or_create_social_user(provider, provider_data, additional_data)

            # Determine whether the student has completed all required profile fields.
            profile_complete = False
            if user.role == 'student':
                from support.models import StudentProfile
                try:
                    profile = user.student_profile
                    profile_complete = bool(
                        profile.phone and
                        profile.permanent_district and
                        profile.permanent_local_level and
                        profile.target_category_id
                    )
                except Exception:
                    profile_complete = False
            else:
                # Teachers and admins have no onboarding requirement
                profile_complete = True

            from rest_framework_simplejwt.tokens import RefreshToken
            update_last_login(None, user)
            refresh = RefreshToken.for_user(user)

            return Response({
                'access': _access_token_for(user),
                'refresh': str(refresh),
                'is_new_user': is_new_user,
                'profile_complete': profile_complete,
                'package': _get_package_status(user),
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': user.role,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                }
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": f"Authentication failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CompleteGoogleProfileView(APIView):
    """
    POST /api/auth/complete-profile/

    Called by the /student/onboarding page after Google OAuth when the
    new user fills in their required profile fields. Requires a valid
    JWT (the token was already issued by SocialLoginView).

    Accepts:
        full_name             str  required
        phone                 str  required (Nepal format)
        permanent_district    str  required
        permanent_local_level str  required
        exam_category_id      int  required
        exam_position_id      int  optional
        ref                   str  optional referral code (see StudentSignupView)

    Returns:
        { profile_complete: true }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        full_name = (request.data.get('full_name') or '').strip()
        phone = (request.data.get('phone') or '').strip()
        permanent_district = (request.data.get('permanent_district') or '').strip()
        permanent_local_level = (request.data.get('permanent_local_level') or '').strip()
        exam_category_id = request.data.get('exam_category_id')
        exam_position_id = request.data.get('exam_position_id')
        course_id = request.data.get('course_id')
        referral_code = (request.data.get('ref') or '').strip()

        missing = []
        if not full_name: missing.append('full_name')
        if not phone: missing.append('phone')
        if not permanent_district: missing.append('permanent_district')
        if not permanent_local_level: missing.append('permanent_local_level')
        if not exam_category_id: missing.append('exam_category_id')
        if missing:
            return Response(
                {'error': f"Please provide: {', '.join(missing)}.", 'missing_fields': missing},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate before writing anything, matching StudentSignupView.
        if referral_code:
            from gamification.models import GamificationProfile
            if not GamificationProfile.objects.filter(referral_code=referral_code).exists():
                return Response({'error': 'Invalid referral code.'}, status=status.HTTP_400_BAD_REQUEST)

        from .validators import is_valid_nepal_phone, is_valid_nepal_district
        if not is_valid_nepal_phone(phone):
            return Response(
                {'error': 'Please enter a valid 10-digit Nepali mobile number.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not is_valid_nepal_district(permanent_district):
            return Response(
                {'error': 'Please select a valid district of Nepal.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from exams.models import ExamCategory, Exam
        try:
            exam_category = ExamCategory.objects.get(id=exam_category_id, is_active=True)
        except (ExamCategory.DoesNotExist, ValueError):
            return Response({'error': 'Please select what you are preparing for.'}, status=status.HTTP_400_BAD_REQUEST)

        exam_position = None
        if exam_position_id:
            try:
                exam_position = Exam.objects.get(id=exam_position_id, is_active=True, category=exam_category)
            except (Exam.DoesNotExist, ValueError):
                return Response({'error': 'Invalid exam selection.'}, status=status.HTTP_400_BAD_REQUEST)

        # Update User name fields
        first_name, _, last_name = full_name.partition(' ')
        user.first_name = first_name[:150]
        user.last_name = last_name[:150]
        user.save(update_fields=['first_name', 'last_name'])

        # Update / create StudentProfile
        from support.models import StudentProfile
        from django.utils import timezone as tz
        profile, _ = StudentProfile.objects.get_or_create(user=user)
        profile.phone = phone
        profile.permanent_district = permanent_district
        profile.permanent_local_level = permanent_local_level
        profile.target_category = exam_category
        if exam_position:
            profile.target_position = exam_position
        if course_id:
            from courses.models import Course
            target_course = Course.objects.filter(id=course_id).first()
            if target_course:
                profile.target_course = target_course
                if not profile.target_position and target_course.exam:
                    profile.target_position = target_course.exam
        if not profile.is_verified:
            profile.is_verified = True
            profile.verified_at = tz.now()
        profile.save()

        # Social sign-up (core/social_auth.py) never creates a
        # GamificationProfile for a new user the way StudentSignupView does -
        # this is the first point in the Google flow where one can exist, so
        # create it here (get_or_create is safe if it already exists from a
        # resubmit) and register the referral only on first creation, same
        # "once per account" guarantee as the email/password signup flow.
        from gamification.models import GamificationProfile
        gamification_profile, gamification_profile_created = GamificationProfile.objects.get_or_create(user=user)
        if gamification_profile_created and referral_code:
            from gamification.services import register_referral
            register_referral(user, referral_code)

        from administration.models import AuditLog
        AuditLog.objects.create(
            actor=user, action='GOOGLE_PROFILE_COMPLETED',
            entity_type='User', entity_id=str(user.id),
            details={'exam_category': exam_category.name},
        )

        return Response({'profile_complete': True})

