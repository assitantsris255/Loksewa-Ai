import logging

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
import uuid

from .models import SubscriptionPlan, Subscription, SubscriptionPayment, Invoice
from .models import SubscriptionCourseSelection
from core.models import Notification
from administration.models import AuditLog
from courses.models import Course, CourseApplication, Enrollment
from .serializers import (
    SubscriptionPlanSerializer, SubscriptionSerializer,
    SubscriptionPaymentSerializer, NotificationSerializer, InvoiceSerializer
)

logger = logging.getLogger(__name__)

class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ['admin', 'super-admin']

class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    serializer_class = SubscriptionPlanSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'available']:
            return [permissions.AllowAny()]
        return [IsAdminUser()]

    def get_queryset(self):
        qs = SubscriptionPlan.objects.select_related(
            'course', 'course__exam', 'course__exam__parent', 'course__exam__category'
        ).prefetch_related(
            'eligible_courses', 'eligible_courses__exam', 'eligible_courses__exam__parent', 'eligible_courses__exam__category'
        ).order_by('display_order')
        user = self.request.user
        if not (user and user.is_authenticated and user.role in ('admin', 'super-admin')):
            qs = qs.filter(status='ACTIVE')
        return qs

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        plan = self.get_object()
        course_ids = set(plan.eligible_courses.values_list('id', flat=True))
        if plan.course_id:
            course_ids.add(plan.course_id)

        dependencies = {
            'subscriptions': Subscription.objects.filter(plan=plan).count(),
            'payments': SubscriptionPayment.objects.filter(plan=plan).count(),
            'course_selections': SubscriptionCourseSelection.objects.filter(
                Q(payment__plan=plan) | Q(subscription__plan=plan)
            ).count(),
            'enrollments': Enrollment.objects.filter(course_id__in=course_ids).count(),
            'course_applications': CourseApplication.objects.filter(
                subscription_payment__plan=plan
            ).count(),
            'audit_records': AuditLog.objects.filter(entity_id=str(plan.pk)).filter(
                Q(entity_type__icontains='package')
                | Q(entity_type__icontains='subscriptionplan')
                | Q(entity_type__icontains='subscription plan')
            ).count(),
        }

        if any(dependencies.values()):
            plan.status = 'ARCHIVED'
            plan.save(update_fields=('status', 'updated_at'))
            return Response({
                'deleted': False,
                'archived': True,
                'message': 'Package archived because historical records depend on it.',
                'dependencies': dependencies,
            }, status=status.HTTP_200_OK)

        plan.delete()
        return Response({
            'deleted': True,
            'archived': False,
            'message': 'Package permanently deleted.',
            'dependencies': dependencies,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='available')
    def available(self, request):
        user = request.user if (request.user and request.user.is_authenticated) else None
        profile = getattr(user, 'student_profile', None) if user else None

        target_category = profile.target_category if profile else None
        target_position = profile.target_position if profile else None
        target_course = profile.target_course if profile else None

        # Check for query overrides (e.g. if student clicks "Buy Another Course" or explores specific preparation)
        course_id_param = request.query_params.get('course_id')
        exam_id_param = request.query_params.get('exam_id')

        from courses.models import Course, Enrollment

        if course_id_param:
            try:
                tc = Course.objects.filter(id=course_id_param).first()
                if tc:
                    target_course = tc
                    if tc.exam:
                        target_position = tc.exam
                        target_category = tc.exam.category
            except (ValueError, TypeError):
                pass
        elif exam_id_param:
            from exams.models import Exam
            try:
                tp = Exam.objects.filter(id=exam_id_param).first()
                if tp:
                    target_position = tp
                    target_category = tp.category
            except (ValueError, TypeError):
                pass

        # Identify candidate course IDs for this student's preparation
        candidate_courses_qs = Course.objects.filter(status='published')
        if target_course:
            candidate_course_ids = {target_course.id}
        elif target_position:
            child_exam_ids = list(target_position.children.values_list('id', flat=True))
            relevant_exam_ids = [target_position.id] + child_exam_ids
            if target_position.parent_id:
                relevant_exam_ids.append(target_position.parent_id)
            candidate_courses_qs = candidate_courses_qs.filter(exam_id__in=relevant_exam_ids)
            candidate_course_ids = set(candidate_courses_qs.values_list('id', flat=True))
        elif target_category:
            candidate_courses_qs = candidate_courses_qs.filter(exam__category=target_category)
            candidate_course_ids = set(candidate_courses_qs.values_list('id', flat=True))
        else:
            candidate_course_ids = set(candidate_courses_qs.values_list('id', flat=True))

        # Active enrollments student already owns
        owned_course_ids = set()
        if user:
            owned_course_ids = set(Enrollment.objects.filter(
                student=user,
                status='active'
            ).values_list('course_id', flat=True))

        all_active_plans = SubscriptionPlan.objects.filter(status='ACTIVE').order_by('display_order')

        matching_plans = []
        for plan in all_active_plans:
            is_compatible = False

            if plan.package_type == 'ALL_ACCESS':
                is_compatible = True
            elif plan.package_type == 'SINGLE':
                if plan.course_id and plan.course_id in candidate_course_ids:
                    is_compatible = True
                elif not plan.course_id and not plan.eligible_courses.exists():
                    is_compatible = True
                elif plan.eligible_courses.filter(id__in=candidate_course_ids).exists():
                    is_compatible = True
            elif plan.package_type in ('MULTI', 'BUNDLE'):
                if plan.eligible_courses.filter(id__in=candidate_course_ids).exists():
                    is_compatible = True
                elif not plan.eligible_courses.exists():
                    is_compatible = True
            else:
                if plan.course_id in candidate_course_ids or not plan.course_id:
                    is_compatible = True

            if is_compatible:
                matching_plans.append(plan)

        has_matched_specific = bool(matching_plans)
        if not matching_plans:
            matching_plans = list(all_active_plans)

        prep_info = {
            "has_preference": bool(target_category or target_position or target_course),
            "category_name": target_category.name if target_category else None,
            "category_id": target_category.id if target_category else None,
            "level_name": target_position.parent.name if (target_position and target_position.parent) else (target_position.name if target_position else None),
            "service_name": target_position.name if (target_position and target_position.parent) else None,
            "exam_id": target_position.id if target_position else None,
            "exam_name": target_position.name if target_position else None,
            "course_id": target_course.id if target_course else None,
            "course_title": target_course.title if target_course else None,
            "owned_course_ids": list(owned_course_ids),
            "has_matched_specific": has_matched_specific,
        }

        serializer = self.get_serializer(matching_plans, many=True)
        return Response({
            "preparation": prep_info,
            "plans": serializer.data,
        })

class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Subscription.objects.filter(student=self.request.user).order_by('-created_at')

class SubscriptionPaymentViewSet(viewsets.ModelViewSet):
    serializer_class = SubscriptionPaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role in ['admin', 'super-admin']:
            return SubscriptionPayment.objects.all().order_by('-submitted_at')
        return SubscriptionPayment.objects.filter(student=self.request.user).order_by('-submitted_at')

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError
        plan = serializer.validated_data['plan']
        if plan.status != 'ACTIVE':
            raise ValidationError({'plan': 'This package is no longer available for purchase.'})

        # Prevent duplicate pending payment for the same plan
        existing_pending = SubscriptionPayment.objects.filter(
            student=self.request.user,
            plan=plan,
            status='PENDING'
        ).first()
        if existing_pending:
            raise ValidationError({"detail": "You already have a pending payment under review for this package."})

        # Parse course_ids safely from FormData or JSON
        course_ids = self.request.data.getlist('course_ids') if hasattr(self.request.data, 'getlist') else self.request.data.get('course_ids', [])
        if not course_ids:
            raw = self.request.data.get('course_ids')
            if isinstance(raw, str):
                course_ids = [c.strip() for c in raw.split(',') if c.strip()]
            elif isinstance(raw, list):
                course_ids = raw
            else:
                course_ids = []

        if plan.package_type == 'MULTI':
            if not course_ids:
                raise ValidationError({"course_ids": "Please select your preparation(s) for this package."})
            if len(course_ids) > plan.allowed_preparation_count:
                raise ValidationError({"course_ids": f"This plan allows up to {plan.allowed_preparation_count} preparation(s)."})
            eligible_ids = list(plan.eligible_courses.values_list('id', flat=True))
            if eligible_ids:
                invalid_courses = [cid for cid in course_ids if int(cid) not in eligible_ids]
                if invalid_courses:
                    raise ValidationError({"course_ids": "Some selected preparations are not eligible for this package."})

        payment = serializer.save(student=self.request.user, amount=plan.price)

        from courses.models import Course, CourseApplication
        if plan.package_type == 'MULTI':
            for course_id in course_ids:
                CourseApplication.objects.update_or_create(
                    student=self.request.user,
                    course_id=course_id,
                    defaults={
                        'subscription_payment': payment,
                        'status': 'pending',
                        'reviewed_at': None,
                        'reviewed_by': None
                    }
                )
        elif plan.package_type == 'BUNDLE':
            for course in plan.eligible_courses.all():
                CourseApplication.objects.update_or_create(
                    student=self.request.user,
                    course=course,
                    defaults={
                        'subscription_payment': payment,
                        'status': 'pending',
                        'reviewed_at': None,
                        'reviewed_by': None
                    }
                )
        elif plan.package_type == 'SINGLE':
            single_course = plan.course
            if not single_course and plan.eligible_courses.count() == 1:
                single_course = plan.eligible_courses.first()
            elif not single_course and course_ids:
                single_course = Course.objects.filter(id=course_ids[0]).first()
            if single_course:
                CourseApplication.objects.update_or_create(
                    student=self.request.user,
                    course=single_course,
                    defaults={
                        'subscription_payment': payment,
                        'status': 'pending',
                        'reviewed_at': None,
                        'reviewed_by': None
                    }
                )
        elif plan.course:
            CourseApplication.objects.update_or_create(
                student=self.request.user,
                course=plan.course,
                defaults={
                    'subscription_payment': payment,
                    'status': 'pending',
                    'reviewed_at': None,
                    'reviewed_by': None
                }
            )

        from core.notification_service import NotificationService
        NotificationService.notify_student_payment_submitted(
            student=self.request.user,
            title_ref=plan.name,
            amount=payment.amount,
            action_url='/student/purchases',
        )
        NotificationService.notify_admins(
            notif_type='payment',
            title='New Subscription Payment Awaiting Verification',
            message=f"{self.request.user.get_full_name() or self.request.user.username} submitted a payment of NPR {payment.amount} for '{payment.plan.name}'.",
            action_url='/admin-dashboard/applications',
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        payment = self.get_object()
        if payment.status != 'PENDING':
            return Response({'detail': 'Payment is not pending.'}, status=status.HTTP_400_BAD_REQUEST)

        # Everything below is one admin action with several dependent writes
        # (payment, subscription, enrollment, invoice, notification) — wrap
        # it so a failure partway through rolls back cleanly instead of
        # leaving e.g. an APPROVED payment with no subscription/enrollment.
        with transaction.atomic():
            # Approve payment
            payment.status = 'APPROVED'
            payment.verified_by = request.user
            payment.verified_at = timezone.now()

            # Determine start and expiry dates
            plan = payment.plan
            now = timezone.now()
            start_date = now

            # Check if user has active subscription to extend
            active_sub = Subscription.objects.filter(student=payment.student, status='ACTIVE', expiry_date__gt=now).order_by('-expiry_date').first()
            if active_sub:
                start_date = active_sub.expiry_date

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

            expiry_date = start_date + delta

            # Create subscription
            subscription = Subscription.objects.create(
                student=payment.student,
                plan=plan,
                status='ACTIVE',
                start_date=start_date,
                expiry_date=expiry_date
            )

            payment.subscription = subscription
            payment.save()

            # ── AUTO-ENROLL: activate Enrollment based on CourseApplications ──
            enrolled_course_title = plan.name  # fallback notification text
            try:
                from courses.models import Enrollment, CourseApplication
                
                applications = CourseApplication.objects.filter(subscription_payment=payment)
                
                for app in applications:
                    enrollment, created = Enrollment.objects.get_or_create(
                        student=payment.student,
                        course=app.course,
                        defaults={
                            'status': 'active',
                            'expires_at': expiry_date,
                        }
                    )
                    if not created:
                        # Reactivate if previously cancelled/suspended
                        enrollment.status = 'active'
                        enrollment.expires_at = expiry_date
                        enrollment.save(update_fields=['status', 'expires_at'])

                    app.status = 'approved'
                    app.reviewed_at = now
                    app.reviewed_by = request.user
                    app.save()

                if plan.course:
                    enrollment, created = Enrollment.objects.get_or_create(
                        student=payment.student,
                        course=plan.course,
                        defaults={
                            'status': 'active',
                            'expires_at': expiry_date,
                        }
                    )
                    if not created:
                        enrollment.status = 'active'
                        enrollment.expires_at = expiry_date
                        enrollment.save(update_fields=['status', 'expires_at'])
                    enrolled_course_title = plan.course.title
                elif applications.exists():
                    if applications.count() == 1:
                        enrolled_course_title = applications.first().course.title
                    else:
                        enrolled_course_title = f"{applications.count()} Preparations"
            except Exception:
                # Deliberately not re-raised: a bug in the auto-enroll
                # step shouldn't block the payment approval itself, but
                # it must not fail silently either.
                logger.exception(
                    "Auto-enroll failed for payment_id=%s student_id=%s",
                    payment.id, payment.student_id,
                )

            # Create invoice
            Invoice.objects.create(
                student=payment.student,
                payment=payment,
                receipt_number=f"LKAI-{now.year}-{str(uuid.uuid4())[:8].upper()}",
                amount=payment.amount
            )

            # Notify student
            from core.notification_service import NotificationService
            NotificationService.notify_student_payment_approved(
                student=payment.student,
                title_ref=enrolled_course_title,
                action_url='/student/purchases',
            )

        # Placed after the atomic block so it only fires once the approval
        # (payment + subscription + enrollment + invoice) has actually
        # committed - a rollback partway through never leaves this orphaned.
        from core.notification_service import NotificationService
        NotificationService.notify_admins(
            notif_type='payment',
            title='Subscription Payment Approved',
            message=f"{request.user.get_full_name() or request.user.username} approved {payment.student.get_full_name() or payment.student.username}'s payment for '{plan.name}' — subscription activated.",
            action_url='/admin-dashboard/applications',
        )

        return Response({'status': 'approved'})


    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def reject(self, request, pk=None):
        payment = self.get_object()
        if payment.status != 'PENDING':
            return Response({'detail': 'Payment is not pending.'}, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get('reason', '')
        if not reason:
            return Response({'detail': 'Rejection reason is required.'}, status=status.HTTP_400_BAD_REQUEST)

        payment.status = 'REJECTED'
        payment.rejection_reason = reason
        payment.verified_by = request.user
        payment.verified_at = timezone.now()
        payment.save()
        
        from core.notification_service import NotificationService
        NotificationService.notify_student_payment_rejected(
            student=payment.student,
            title_ref=payment.plan.name,
            reason=reason,
            action_url='/student/purchases',
        )
        NotificationService.notify_admins(
            notif_type='payment',
            title='Subscription Payment Rejected',
            message=f"{request.user.get_full_name() or request.user.username} rejected {payment.student.get_full_name() or payment.student.username}'s payment for '{payment.plan.name}'. Reason: {reason}",
            action_url='/admin-dashboard/applications',
        )

        return Response({'status': 'rejected'})

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).order_by('-created_at')

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'all_read'})

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({'status': 'read'})
