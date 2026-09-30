"""Package/subscription + payment verification system.

Covers the spec's checklist: package CRUD/publish visibility, purchase using
the server-side price (never the client's), duplicate-payment prevention,
the full approve transaction (subscription activation, correct expiry math,
auto-enrollment, invoice, notification), rejection (reason required, nothing
activated), access control via HasActiveSubscription both with enforcement
off and on, cross-student IDOR, teacher/admin authorization boundaries, and
remaining-days/expiring-soon/expired computation.
"""
import base64
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from administration.models import AuditLog
from core.models import AdminSettings, Notification, User
from courses.models import Course, Enrollment
from exams.models import Exam, ExamCategory
from marketplace.models import PaymentMethod
from subscriptions.access import has_active_subscription, has_feature
from subscriptions.models import (
    Invoice, Subscription, SubscriptionCourseSelection,
    SubscriptionPayment, SubscriptionPlan,
)

# A 1x1 GIF - the same dummy upload fixture the marketplace test suite uses,
# small enough to pass validate_image_size_5mb and validate_image_extension.
_GIF_DATA = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')


def _dummy_screenshot(name='proof.gif'):
    return SimpleUploadedFile(name, _GIF_DATA, content_type='image/gif')


class PackageManagementTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin1', password='pw', role='admin', is_staff=True)
        self.student = User.objects.create_user(username='stud1', password='pw', role='student')

    def test_admin_can_create_package(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post('/api/subscriptions/plans/', {
            'name': 'PSC Foundation', 'description': 'Base plan', 'duration': 90,
            'duration_unit': 'DAYS', 'price': '2999.00', 'features': ['ai_tutor'],
            'status': 'ACTIVE',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertTrue(SubscriptionPlan.objects.filter(name='PSC Foundation').exists())

    def test_admin_can_edit_package(self):
        plan = SubscriptionPlan.objects.create(name='Basic', description='', duration=30, price='500.00')
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(f'/api/subscriptions/plans/{plan.id}/', {'price': '750.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        plan.refresh_from_db()
        self.assertEqual(str(plan.price), '750.00')

    def test_student_cannot_create_package(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post('/api/subscriptions/plans/', {
            'name': 'Hack', 'description': '', 'duration': 1, 'price': '0.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_permanently_delete_package_without_history(self):
        plan = SubscriptionPlan.objects.create(
            name='Unused Plan', description='', duration=30, price='500'
        )
        self.client.force_authenticate(self.admin)

        response = self.client.delete(f'/api/subscriptions/plans/{plan.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['deleted'])
        self.assertFalse(SubscriptionPlan.objects.filter(pk=plan.pk).exists())

    def test_delete_archives_package_with_historical_records(self):
        plan = SubscriptionPlan.objects.create(
            name='Purchased Plan', description='', duration=30, price='500'
        )
        course = Course.objects.create(
            title='Preparation', slug='package-delete-preparation', status='published'
        )
        plan.course = course
        plan.eligible_courses.add(course)
        plan.save()
        now = timezone.now()
        subscription = Subscription.objects.create(
            student=self.student, plan=plan, start_date=now,
            expiry_date=now + timedelta(days=30),
        )
        method = PaymentMethod.objects.create(
            method_type='ESEWA', display_name='eSewa', account_name='LoksewaAI',
            account_number='9800000000',
        )
        payment = SubscriptionPayment.objects.create(
            student=self.student, plan=plan, subscription=subscription,
            payment_method=method, amount='500', transaction_id='DELETE-HISTORY-1',
            screenshot='subscriptions/payment_proofs/proof.gif',
        )
        invoice = Invoice.objects.create(
            student=self.student, payment=payment,
            receipt_number='DELETE-HISTORY-INV-1', amount='500',
        )
        selection = SubscriptionCourseSelection.objects.create(
            subscription=subscription, course=course,
        )
        enrollment = Enrollment.objects.create(student=self.student, course=course)
        AuditLog.objects.create(
            actor=self.admin, action='PACKAGE_CREATED',
            entity_type='SubscriptionPlan', entity_id=str(plan.pk),
        )
        self.client.force_authenticate(self.admin)

        response = self.client.delete(f'/api/subscriptions/plans/{plan.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['archived'])
        self.assertEqual(response.data['dependencies']['subscriptions'], 1)
        self.assertEqual(response.data['dependencies']['payments'], 1)
        self.assertEqual(response.data['dependencies']['enrollments'], 1)
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'ARCHIVED')
        self.assertTrue(Subscription.objects.filter(pk=subscription.pk).exists())
        self.assertTrue(SubscriptionPayment.objects.filter(pk=payment.pk).exists())
        self.assertTrue(Invoice.objects.filter(pk=invoice.pk).exists())
        self.assertTrue(SubscriptionCourseSelection.objects.filter(pk=selection.pk).exists())
        self.assertTrue(Enrollment.objects.filter(pk=enrollment.pk).exists())
        self.assertNotIn(
            plan.name,
            [item['name'] for item in self.client.get('/api/packages/public/').data],
        )

    def test_teacher_cannot_delete_package(self):
        teacher = User.objects.create_user(username='teacher-delete', password='pw', role='teacher')
        plan = SubscriptionPlan.objects.create(
            name='Protected Plan', description='', duration=30, price='500'
        )
        self.client.force_authenticate(teacher)

        response = self.client.delete(f'/api/subscriptions/plans/{plan.id}/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(SubscriptionPlan.objects.filter(pk=plan.pk).exists())

    def test_package_cannot_include_coming_soon_course(self):
        category = ExamCategory.objects.create(name='PSC Exams')
        exam = Exam.objects.create(
            category=category, name='Coming Soon Preparation', status='coming_soon'
        )
        course = Course.objects.create(
            title='Coming Soon Course', slug='coming-soon-package-course',
            status='published', exam=exam,
        )
        self.client.force_authenticate(self.admin)

        response = self.client.post('/api/subscriptions/plans/', {
            'name': 'Coming Soon Package', 'description': '', 'duration': 30,
            'price': '500', 'package_type': 'SINGLE', 'course': course.id,
            'eligible_courses': [course.id],
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(SubscriptionPlan.objects.filter(name='Coming Soon Package').exists())

    def test_admin_can_create_package_for_active_canonical_course(self):
        category = ExamCategory.objects.create(name='PSC Exams')
        level = Exam.objects.create(category=category, name='4th Level')
        preparation = Exam.objects.create(
            category=category, parent=level, name='Assistant Civil Engineer'
        )
        course = Course.objects.create(
            title='Assistant Civil Engineer', slug='active-package-course',
            status='published', exam=preparation,
        )
        self.client.force_authenticate(self.admin)

        response = self.client.post('/api/subscriptions/plans/', {
            'name': 'Assistant Civil Engineer Access', 'description': '',
            'duration': 90, 'price': '2999', 'package_type': 'SINGLE',
            'course': course.id, 'eligible_courses': [course.id],
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['course'], course.id)

    def test_student_sees_only_active_plans(self):
        active = SubscriptionPlan.objects.create(name='Active Plan', description='', duration=30, price='500', status='ACTIVE')
        draft = SubscriptionPlan.objects.create(name='Draft Plan', description='', duration=30, price='500', status='INACTIVE')
        self.client.force_authenticate(self.student)
        resp = self.client.get('/api/subscriptions/plans/')
        names = [p['name'] for p in resp.data]
        self.assertIn('Active Plan', names)
        self.assertNotIn('Draft Plan', names)

    def test_public_endpoint_never_exposes_draft_plans(self):
        SubscriptionPlan.objects.create(name='Draft Plan', description='', duration=30, price='500', status='INACTIVE')
        resp = self.client.get('/api/packages/public/')
        names = [p['name'] for p in resp.data]
        self.assertNotIn('Draft Plan', names)

    def test_public_endpoint_derives_feature_flags_from_plan_features(self):
        SubscriptionPlan.objects.create(
            name='AI Plan', description='', duration=30, price='500', status='ACTIVE',
            features=['ai_tutor'],
        )
        resp = self.client.get('/api/packages/public/')
        plan_data = next(p for p in resp.data if p['name'] == 'AI Plan')
        self.assertTrue(plan_data['ai_features'])
        self.assertFalse(plan_data['mock_exam_access'])

    def test_wildcard_feature_grants_everything_on_public_endpoint(self):
        SubscriptionPlan.objects.create(
            name='All Access', description='', duration=30, price='500', status='ACTIVE',
            features=['*'],
        )
        resp = self.client.get('/api/packages/public/')
        plan_data = next(p for p in resp.data if p['name'] == 'All Access')
        self.assertTrue(plan_data['practice_access'])
        self.assertTrue(plan_data['mock_exam_access'])
        self.assertTrue(plan_data['notes_access'])
        self.assertTrue(plan_data['ai_features'])


class PurchaseFlowTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='stud1', password='pw', role='student')
        self.plan = SubscriptionPlan.objects.create(
            name='PSC Foundation', description='', duration=90, duration_unit='DAYS',
            price='2999.00', status='ACTIVE',
        )
        self.method = PaymentMethod.objects.create(
            method_type='ESEWA', display_name='eSewa', account_name='LoksewaAI', account_number='9800000000',
        )

    def test_archived_package_cannot_be_purchased(self):
        self.plan.status = 'ARCHIVED'
        self.plan.save(update_fields=['status', 'updated_at'])
        self.client.force_authenticate(self.student)

        response = self.client.post('/api/subscriptions/payments/', {
            'plan': self.plan.id, 'payment_method': self.method.id,
            'transaction_id': 'ARCHIVED-PLAN-PURCHASE',
            'screenshot': _dummy_screenshot(),
        }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(SubscriptionPayment.objects.filter(
            transaction_id='ARCHIVED-PLAN-PURCHASE'
        ).exists())

    @patch('core.google_drive.upload_file')
    def test_purchase_uses_server_side_price_not_client_amount(self, mock_upload):
        mock_upload.return_value = {'id': 'mock_id'}
        self.client.force_authenticate(self.student)
        resp = self.client.post('/api/subscriptions/payments/', {
            'plan': self.plan.id, 'payment_method': self.method.id,
            'amount': '1.00',  # tampered - must be ignored
            'transaction_id': 'TXN-001', 'screenshot': _dummy_screenshot(),
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        payment = SubscriptionPayment.objects.get(transaction_id='TXN-001')
        self.assertEqual(str(payment.amount), '2999.00')
        self.assertEqual(payment.status, 'PENDING')

    @patch('core.google_drive.upload_file')
    def test_purchase_notifies_student_and_admins(self, mock_upload):
        mock_upload.return_value = {'id': 'mock_id'}
        admin = User.objects.create_user(username='admin1', password='pw', role='admin', is_staff=True)
        self.client.force_authenticate(self.student)
        self.client.post('/api/subscriptions/payments/', {
            'plan': self.plan.id, 'payment_method': self.method.id, 'amount': '2999.00',
            'transaction_id': 'TXN-002', 'screenshot': _dummy_screenshot(),
        }, format='multipart')
        self.assertTrue(Notification.objects.filter(recipient=self.student, type='payment').exists())
        self.assertTrue(Notification.objects.filter(recipient=admin, type='payment').exists())

    @patch('core.google_drive.upload_file')
    def test_duplicate_transaction_id_rejected(self, mock_upload):
        mock_upload.return_value = {'id': 'mock_id'}
        self.client.force_authenticate(self.student)
        self.client.post('/api/subscriptions/payments/', {
            'plan': self.plan.id, 'payment_method': self.method.id, 'amount': '2999.00',
            'transaction_id': 'DUPLICATE', 'screenshot': _dummy_screenshot(),
        }, format='multipart')
        resp = self.client.post('/api/subscriptions/payments/', {
            'plan': self.plan.id, 'payment_method': self.method.id, 'amount': '2999.00',
            'transaction_id': 'DUPLICATE', 'screenshot': _dummy_screenshot('proof2.gif'),
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SubscriptionPayment.objects.filter(transaction_id='DUPLICATE').count(), 1)


class VerificationTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin1', password='pw', role='admin', is_staff=True)
        self.student = User.objects.create_user(username='stud1', password='pw', role='student')
        self.method = PaymentMethod.objects.create(
            method_type='ESEWA', display_name='eSewa', account_name='LoksewaAI', account_number='9800000000',
        )

    def _pending_payment(self, plan):
        return SubscriptionPayment.objects.create(
            student=self.student, plan=plan, payment_method=self.method,
            amount=plan.price, transaction_id=f'TXN-{plan.id}-{self.student.id}',
            screenshot=_dummy_screenshot(),
        )

    def test_admin_sees_pending_payment(self):
        plan = SubscriptionPlan.objects.create(name='Plan', description='', duration=30, price='500')
        self._pending_payment(plan)
        self.client.force_authenticate(self.admin)
        resp = self.client.get('/api/subscriptions/payments/')
        self.assertEqual(len(resp.data), 1)

    def test_approve_activates_subscription_with_correct_dates(self):
        plan = SubscriptionPlan.objects.create(name='Plan', description='', duration=90, duration_unit='DAYS', price='500')
        payment = self._pending_payment(plan)
        self.client.force_authenticate(self.admin)

        before = timezone.now()
        resp = self.client.post(f'/api/subscriptions/payments/{payment.id}/approve/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'APPROVED')
        self.assertIsNotNone(payment.subscription)

        sub = payment.subscription
        self.assertEqual(sub.status, 'ACTIVE')
        self.assertTrue(before <= sub.start_date)
        self.assertAlmostEqual(
            (sub.expiry_date - sub.start_date).total_seconds(),
            timedelta(days=90).total_seconds(),
            delta=5,
        )
        self.assertTrue(Invoice.objects.filter(payment=payment).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.student, type='payment').exists())
        self.assertTrue(has_active_subscription(self.student))

    def test_approve_renews_from_existing_expiry_not_from_now(self):
        plan = SubscriptionPlan.objects.create(name='Plan', description='', duration=30, duration_unit='DAYS', price='500')
        existing_expiry = timezone.now() + timedelta(days=10)
        Subscription.objects.create(
            student=self.student, plan=plan, status='ACTIVE',
            start_date=timezone.now(), expiry_date=existing_expiry,
        )
        payment = self._pending_payment(plan)
        self.client.force_authenticate(self.admin)
        self.client.post(f'/api/subscriptions/payments/{payment.id}/approve/')

        payment.refresh_from_db()
        new_sub = payment.subscription
        self.assertAlmostEqual(new_sub.start_date.timestamp(), existing_expiry.timestamp(), delta=5)

    def test_approve_auto_enrolls_when_plan_has_course(self):
        course = Course.objects.create(title='Constitutional Law', slug='constitutional-law')
        plan = SubscriptionPlan.objects.create(name='Course Plan', description='', duration=30, price='500', course=course)
        payment = self._pending_payment(plan)
        self.client.force_authenticate(self.admin)
        self.client.post(f'/api/subscriptions/payments/{payment.id}/approve/')

        enrollment = Enrollment.objects.get(student=self.student, course=course)
        self.assertEqual(enrollment.status, 'active')

    def test_cannot_approve_twice(self):
        plan = SubscriptionPlan.objects.create(name='Plan', description='', duration=30, price='500')
        payment = self._pending_payment(plan)
        self.client.force_authenticate(self.admin)
        self.client.post(f'/api/subscriptions/payments/{payment.id}/approve/')
        resp = self.client.post(f'/api/subscriptions/payments/{payment.id}/approve/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Subscription.objects.filter(student=self.student).count(), 1)

    def test_reject_requires_reason(self):
        plan = SubscriptionPlan.objects.create(name='Plan', description='', duration=30, price='500')
        payment = self._pending_payment(plan)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f'/api/subscriptions/payments/{payment.id}/reject/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_stores_reason_and_activates_nothing(self):
        plan = SubscriptionPlan.objects.create(name='Plan', description='', duration=30, price='500')
        payment = self._pending_payment(plan)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f'/api/subscriptions/payments/{payment.id}/reject/', {'reason': 'Blurry screenshot'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'REJECTED')
        self.assertEqual(payment.rejection_reason, 'Blurry screenshot')
        self.assertIsNone(payment.subscription)
        self.assertFalse(Subscription.objects.filter(student=self.student).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.student, type='payment', message__icontains='rejected').exists())

    def test_teacher_cannot_approve_or_reject(self):
        plan = SubscriptionPlan.objects.create(name='Plan', description='', duration=30, price='500')
        payment = self._pending_payment(plan)
        teacher = User.objects.create_user(username='teach1', password='pw', role='teacher')
        self.client.force_authenticate(teacher)
        resp = self.client.post(f'/api/subscriptions/payments/{payment.id}/approve/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class IDORTests(APITestCase):
    def setUp(self):
        self.student1 = User.objects.create_user(username='stud1', password='pw', role='student')
        self.student2 = User.objects.create_user(username='stud2', password='pw', role='student')
        self.teacher = User.objects.create_user(username='teach1', password='pw', role='teacher')
        self.method = PaymentMethod.objects.create(
            method_type='ESEWA', display_name='eSewa', account_name='LoksewaAI', account_number='9800000000',
        )
        self.plan = SubscriptionPlan.objects.create(name='Plan', description='', duration=30, price='500')
        self.payment = SubscriptionPayment.objects.create(
            student=self.student1, plan=self.plan, payment_method=self.method,
            amount=self.plan.price, transaction_id='TXN-IDOR', screenshot=_dummy_screenshot(),
        )
        self.subscription = Subscription.objects.create(
            student=self.student1, plan=self.plan, status='ACTIVE',
            start_date=timezone.now(), expiry_date=timezone.now() + timedelta(days=30),
        )

    def test_student_cannot_list_another_students_payment(self):
        self.client.force_authenticate(self.student2)
        resp = self.client.get('/api/subscriptions/payments/')
        ids = [p['id'] for p in resp.data]
        self.assertNotIn(self.payment.id, ids)

    def test_student_cannot_retrieve_another_students_payment(self):
        self.client.force_authenticate(self.student2)
        resp = self.client.get(f'/api/subscriptions/payments/{self.payment.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_student_cannot_approve_another_students_payment(self):
        self.client.force_authenticate(self.student2)
        resp = self.client.post(f'/api/subscriptions/payments/{self.payment.id}/approve/')
        self.assertIn(resp.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'PENDING')

    def test_student_cannot_see_another_students_subscription(self):
        self.client.force_authenticate(self.student2)
        resp = self.client.get('/api/subscriptions/my-subscriptions/')
        ids = [s['id'] for s in resp.data]
        self.assertNotIn(self.subscription.id, ids)

    def test_teacher_cannot_access_payment_queue(self):
        self.client.force_authenticate(self.teacher)
        resp = self.client.get(f'/api/subscriptions/payments/{self.payment.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class AccessControlTests(APITestCase):
    """HasActiveSubscription (subscriptions/permissions.py), exercised
    directly against a real gated endpoint (PracticeSessionViewSet)."""

    def setUp(self):
        self.student = User.objects.create_user(username='stud1', password='pw', role='student')
        self.admin = User.objects.create_user(username='admin1', password='pw', role='admin', is_staff=True)
        self.teacher = User.objects.create_user(username='teach1', password='pw', role='teacher')
        self.plan = SubscriptionPlan.objects.create(name='Plan', description='', duration=30, price='500', features=['*'])
        settings_obj = AdminSettings.get_settings()
        settings_obj.enforce_subscription_access = False
        settings_obj.save(update_fields=['enforce_subscription_access'])

    def test_enforcement_off_allows_student_with_no_package(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get('/api/practice-sessions/')
        self.assertNotEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_enforcement_on_denies_student_with_no_package(self):
        settings_obj = AdminSettings.get_settings()
        settings_obj.enforce_subscription_access = True
        settings_obj.save(update_fields=['enforce_subscription_access'])

        self.client.force_authenticate(self.student)
        resp = self.client.get('/api/practice-sessions/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_enforcement_on_allows_student_with_active_package(self):
        settings_obj = AdminSettings.get_settings()
        settings_obj.enforce_subscription_access = True
        settings_obj.save(update_fields=['enforce_subscription_access'])
        Subscription.objects.create(
            student=self.student, plan=self.plan, status='ACTIVE',
            start_date=timezone.now(), expiry_date=timezone.now() + timedelta(days=30),
        )

        self.client.force_authenticate(self.student)
        resp = self.client.get('/api/practice-sessions/')
        self.assertNotEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_enforcement_on_denies_student_with_expired_package(self):
        settings_obj = AdminSettings.get_settings()
        settings_obj.enforce_subscription_access = True
        settings_obj.save(update_fields=['enforce_subscription_access'])
        Subscription.objects.create(
            student=self.student, plan=self.plan, status='ACTIVE',
            start_date=timezone.now() - timedelta(days=60), expiry_date=timezone.now() - timedelta(days=1),
        )

        self.client.force_authenticate(self.student)
        resp = self.client.get('/api/practice-sessions/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(has_active_subscription(self.student))

    def test_enforcement_on_never_blocks_staff_roles(self):
        settings_obj = AdminSettings.get_settings()
        settings_obj.enforce_subscription_access = True
        settings_obj.save(update_fields=['enforce_subscription_access'])

        self.client.force_authenticate(self.teacher)
        resp = self.client.get('/api/practice-sessions/')
        self.assertNotEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin)
        resp = self.client.get('/api/practice-sessions/')
        self.assertNotEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_enforcement_on_allows_student_with_admin_granted_access(self):
        settings_obj = AdminSettings.get_settings()
        settings_obj.enforce_subscription_access = True
        settings_obj.save(update_fields=['enforce_subscription_access'])
        from support.models import StudentProfile
        StudentProfile.objects.create(
            user=self.student,
            access_origin='ADMIN_GRANTED',
            admin_granted_by=self.admin,
            admin_granted_at=timezone.now()
        )

        self.client.force_authenticate(self.student)
        resp = self.client.get('/api/practice-sessions/')
        self.assertNotEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(has_feature(self.student, 'ai_tutor'))

    def test_enforcement_on_denies_student_with_expired_admin_granted_access(self):
        settings_obj = AdminSettings.get_settings()
        settings_obj.enforce_subscription_access = True
        settings_obj.save(update_fields=['enforce_subscription_access'])
        from support.models import StudentProfile
        StudentProfile.objects.create(
            user=self.student,
            access_origin='ADMIN_GRANTED',
            admin_access_expiry=timezone.now() - timedelta(days=1),
            admin_granted_by=self.admin,
            admin_granted_at=timezone.now() - timedelta(days=30)
        )

        self.client.force_authenticate(self.student)
        resp = self.client.get('/api/practice-sessions/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(has_feature(self.student, 'ai_tutor'))

    def test_has_feature_respects_wildcard(self):
        Subscription.objects.create(
            student=self.student, plan=self.plan, status='ACTIVE',
            start_date=timezone.now(), expiry_date=timezone.now() + timedelta(days=30),
        )
        self.assertTrue(has_feature(self.student, 'ai_tutor'))
        self.assertTrue(has_feature(self.student, 'anything_at_all'))

    def test_has_feature_false_without_subscription(self):
        self.assertFalse(has_feature(self.student, 'ai_tutor'))


class ExpiryComputationTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='stud1', password='pw', role='student')
        self.plan = SubscriptionPlan.objects.create(name='Plan', description='', duration=30, price='500')

    def test_remaining_days_and_status_active(self):
        sub = Subscription.objects.create(
            student=self.student, plan=self.plan, status='ACTIVE',
            start_date=timezone.now(), expiry_date=timezone.now() + timedelta(days=20),
        )
        self.client.force_authenticate(self.student)
        resp = self.client.get('/api/subscriptions/my-subscriptions/')
        row = next(s for s in resp.data if s['id'] == sub.id)
        self.assertEqual(row['computed_status'], 'ACTIVE')
        self.assertIn(row['remaining_days'], (19, 20))

    def test_expiring_soon_within_threshold(self):
        sub = Subscription.objects.create(
            student=self.student, plan=self.plan, status='ACTIVE',
            start_date=timezone.now(), expiry_date=timezone.now() + timedelta(days=5),
        )
        self.client.force_authenticate(self.student)
        resp = self.client.get('/api/subscriptions/my-subscriptions/')
        row = next(s for s in resp.data if s['id'] == sub.id)
        self.assertEqual(row['computed_status'], 'EXPIRING_SOON')

    def test_expired_even_if_status_still_active_in_db(self):
        """Status is deliberately never flipped by a background job - the
        live expiry_date comparison is the source of truth."""
        sub = Subscription.objects.create(
            student=self.student, plan=self.plan, status='ACTIVE',
            start_date=timezone.now() - timedelta(days=40),
            expiry_date=timezone.now() - timedelta(days=1),
        )
        self.client.force_authenticate(self.student)
        resp = self.client.get('/api/subscriptions/my-subscriptions/')
        row = next(s for s in resp.data if s['id'] == sub.id)
        self.assertEqual(row['computed_status'], 'EXPIRED')
        self.assertEqual(row['remaining_days'], 0)
        self.assertFalse(has_active_subscription(self.student))


class ExpiryNotificationTaskTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='stud1', password='pw', role='student')
        self.plan = SubscriptionPlan.objects.create(name='Plan', description='', duration=30, price='500')

    def test_notifies_once_per_expiring_subscription(self):
        from core.notification_service import NotificationService

        Subscription.objects.create(
            student=self.student, plan=self.plan, status='ACTIVE',
            start_date=timezone.now(), expiry_date=timezone.now() + timedelta(days=3),
        )
        sent_first = NotificationService.notify_subscription_expiring_soon()
        sent_second = NotificationService.notify_subscription_expiring_soon()
        self.assertEqual(sent_first, 1)
        self.assertEqual(sent_second, 0)  # related_id dedupe - never double-notifies
        self.assertTrue(Notification.objects.filter(recipient=self.student, title='Package Expiring Soon').exists())

    def test_notifies_expired_subscription(self):
        from core.notification_service import NotificationService

        Subscription.objects.create(
            student=self.student, plan=self.plan, status='ACTIVE',
            start_date=timezone.now() - timedelta(days=40), expiry_date=timezone.now() - timedelta(days=1),
        )
        sent = NotificationService.notify_subscription_expired()
        self.assertEqual(sent, 1)
        self.assertTrue(Notification.objects.filter(recipient=self.student, title='Package Expired').exists())


class PackageMatchingAndPurchaseFlowTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin_flow', password='pw', role='admin', is_staff=True)
        self.student_a = User.objects.create_user(username='student_a', password='pw', role='student')
        self.student_b = User.objects.create_user(username='student_b', password='pw', role='student')

        from exams.models import ExamCategory, Exam
        from support.models import StudentProfile

        self.cat = ExamCategory.objects.create(name='PSC Category')
        self.level5 = Exam.objects.create(name='5th Level Exam', category=self.cat)
        self.exam_comp = Exam.objects.create(name='Computer Exam', category=self.cat, parent=self.level5)
        self.exam_civ = Exam.objects.create(name='Civil Exam', category=self.cat, parent=self.level5)

        self.course_comp = Course.objects.create(
            title='PSC Computer Course', slug='psc-comp-course',
            exam=self.exam_comp, status='published'
        )
        self.course_civ = Course.objects.create(
            title='PSC Civil Course', slug='psc-civ-course',
            exam=self.exam_civ, status='published'
        )

        self.profile_a, _ = StudentProfile.objects.get_or_create(
            user=self.student_a,
            defaults={
                'target_category': self.cat,
                'target_position': self.exam_comp,
                'target_course': self.course_comp,
                'is_verified': True
            }
        )
        self.profile_a.target_category = self.cat
        self.profile_a.target_position = self.exam_comp
        self.profile_a.target_course = self.course_comp
        self.profile_a.save()

        self.method = PaymentMethod.objects.create(
            display_name='eSewa Flow', method_type='ESEWA',
            account_name='Admin Flow', account_number='9800000000',
            is_active=True
        )

        self.plan_comp = SubscriptionPlan.objects.create(
            name='PSC Computer 3M', description='', duration=90, price='2999.00',
            package_type='SINGLE', course=self.course_comp, status='ACTIVE', display_order=1
        )
        self.plan_comp.eligible_courses.set([self.course_comp])

        self.plan_civ = SubscriptionPlan.objects.create(
            name='PSC Civil 3M', description='', duration=90, price='2999.00',
            package_type='SINGLE', course=self.course_civ, status='ACTIVE', display_order=2
        )
        self.plan_civ.eligible_courses.set([self.course_civ])

        self.plan_multi = SubscriptionPlan.objects.create(
            name='Any 2 PSC Multi', description='', duration=90, price='4999.00',
            package_type='MULTI', allowed_preparation_count=2, status='ACTIVE', display_order=3
        )
        self.plan_multi.eligible_courses.set([self.course_comp, self.course_civ])

    def test_available_plans_filters_to_student_preparation(self):
        self.client.force_authenticate(self.student_a)
        resp = self.client.get('/api/subscriptions/plans/available/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        data = resp.data
        self.assertTrue(data['preparation']['has_preference'])
        self.assertEqual(data['preparation']['course_title'], 'PSC Computer Course')

        returned_plan_names = [p['name'] for p in data['plans']]
        self.assertIn('PSC Computer 3M', returned_plan_names)
        self.assertIn('Any 2 PSC Multi', returned_plan_names)
        # Civil plan must NOT be returned because student is preparing for Computer
        self.assertNotIn('PSC Civil 3M', returned_plan_names)

    def test_multi_plan_submission_validation_and_admin_approval_unlocks_courses(self):
        self.client.force_authenticate(self.student_a)

        # 1. Attempt submitting with 3 courses when limit is 2 -> must fail
        dummy_c3 = Course.objects.create(title='C3', slug='c3', status='published')
        resp = self.client.post('/api/subscriptions/payments/', {
            'plan': self.plan_multi.id,
            'payment_method': self.method.id,
            'transaction_id': 'TXN-MULTI-OVERLIMIT',
            'screenshot': _dummy_screenshot('receipt.gif'),
            'course_ids': [self.course_comp.id, self.course_civ.id, dummy_c3.id],
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. Submit valid multi selection (2 courses)
        resp = self.client.post('/api/subscriptions/payments/', {
            'plan': self.plan_multi.id,
            'payment_method': self.method.id,
            'transaction_id': 'TXN-MULTI-VALID-1',
            'screenshot': _dummy_screenshot('receipt.gif'),
            'course_ids': [self.course_comp.id, self.course_civ.id],
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        payment_id = resp.data['id']
        self.assertEqual(resp.data['status'], 'PENDING')

        # 3. Duplicate pending payment for same plan is blocked
        resp_dup = self.client.post('/api/subscriptions/payments/', {
            'plan': self.plan_multi.id,
            'payment_method': self.method.id,
            'transaction_id': 'TXN-MULTI-VALID-2',
            'screenshot': _dummy_screenshot('receipt.gif'),
            'course_ids': [self.course_comp.id],
        }, format='multipart')
        self.assertEqual(resp_dup.status_code, status.HTTP_400_BAD_REQUEST)

        # 4. IDOR test: Student B cannot view or approve Student A's payment
        self.client.force_authenticate(self.student_b)
        resp_idor_get = self.client.get(f'/api/subscriptions/payments/{payment_id}/')
        self.assertEqual(resp_idor_get.status_code, status.HTTP_404_NOT_FOUND)

        resp_idor_approve = self.client.post(f'/api/subscriptions/payments/{payment_id}/approve/')
        self.assertEqual(resp_idor_approve.status_code, status.HTTP_403_FORBIDDEN)

        # 5. Admin approves payment
        self.client.force_authenticate(self.admin)
        resp_approve = self.client.post(f'/api/subscriptions/payments/{payment_id}/approve/')
        self.assertEqual(resp_approve.status_code, status.HTTP_200_OK)

        # 6. Verify enrollment & access for student A
        self.client.force_authenticate(self.student_a)
        self.assertTrue(Enrollment.objects.filter(student=self.student_a, course=self.course_comp, status='active').exists())
        self.assertTrue(Enrollment.objects.filter(student=self.student_a, course=self.course_civ, status='active').exists())

        # My courses API returns both courses
        resp_courses = self.client.get('/api/courses/my-courses/')
        self.assertEqual(resp_courses.status_code, status.HTTP_200_OK)
        enrolled_slugs = [item['course']['slug'] for item in resp_courses.data]
        self.assertIn('psc-comp-course', enrolled_slugs)
        self.assertIn('psc-civ-course', enrolled_slugs)

    def test_payment_rejection_stores_reason_and_leaves_unlocked_false(self):
        self.client.force_authenticate(self.student_a)
        resp = self.client.post('/api/subscriptions/payments/', {
            'plan': self.plan_comp.id,
            'payment_method': self.method.id,
            'transaction_id': 'TXN-REJECT-TEST',
            'screenshot': _dummy_screenshot('receipt.gif'),
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        payment_id = resp.data['id']

        # Admin rejects with reason
        self.client.force_authenticate(self.admin)
        resp_reject = self.client.post(f'/api/subscriptions/payments/{payment_id}/reject/', {
            'reason': 'Screenshot is blurred and transaction reference is unreadable.'
        }, format='json')
        self.assertEqual(resp_reject.status_code, status.HTTP_200_OK)

        payment = SubscriptionPayment.objects.get(id=payment_id)
        self.assertEqual(payment.status, 'REJECTED')
        self.assertEqual(payment.rejection_reason, 'Screenshot is blurred and transaction reference is unreadable.')
        self.assertIsNone(payment.subscription)
        self.assertFalse(has_active_subscription(self.student_a))

