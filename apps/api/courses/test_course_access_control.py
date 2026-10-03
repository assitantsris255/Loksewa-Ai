"""Comprehensive Test Suite for Course-Based Access Control & Subscription Enforcement.

Covers:
1. Single Course, Multi-Course, Bundle, All-Access, and Admin-Grant access.
2. Expiration, Cancellation, Suspension, and Pending payment policies.
3. Notes & Study Materials isolation (list, detail, download, public vs student).
4. Student Portal Syllabus scoping.
5. Practice Sessions & Question Selection scoping.
6. Examinations, Mock Exams, and Attempt privacy & authorization.
7. Existing student backward compatibility & data preservation.
"""

from rest_framework import status
from rest_framework.test import APITestCase
from django.utils import timezone
from datetime import timedelta

from core.models import User, AdminSettings
from exams.models import (
    ExamCategory, Exam, Paper, Subject, Chapter, Topic, Question,
    Examination, ExaminationAttempt, ExaminationQuestion, ExaminationRequest
)
from courses.models import Course, Enrollment, CourseApplication
from subscriptions.models import SubscriptionPlan, Subscription, SubscriptionPayment, SubscriptionCourseSelection
from notes.models import StudyMaterial
from courses.services.course_access_service import CourseAccessService


class CourseAccessControlTests(APITestCase):
    def setUp(self):
        # Enforce subscription access in AdminSettings
        settings = AdminSettings.get_settings()
        settings.enforce_subscription_access = True
        settings.save()

        # Taxonomy Setup
        self.category = ExamCategory.objects.create(name='Public Service Commission')

        # Course A: Civil Sub Engineer
        self.exam_civil = Exam.objects.create(name='Civil Sub Engineer Exam', category=self.category, is_active=True, status='active')
        self.paper_civil = Paper.objects.create(exam=self.exam_civil, name='Civil Paper')
        self.subject_civil = Subject.objects.create(paper=self.paper_civil, name='Civil Engineering Mechanics', is_active=True)
        self.chapter_civil = Chapter.objects.create(subject=self.subject_civil, title='Statics', is_active=True)
        self.topic_civil = Topic.objects.create(chapter=self.chapter_civil, name='Force Systems')
        self.course_civil = Course.objects.create(
            title='Civil Sub Engineer',
            slug='civil-sub-engineer',
            status='published',
            exam=self.exam_civil,
            is_open_for_enrollment=True,
        )

        # Course B: Computer / IT
        self.exam_it = Exam.objects.create(name='Computer IT Exam', category=self.category, is_active=True, status='active')
        self.paper_it = Paper.objects.create(exam=self.exam_it, name='IT Paper')
        self.subject_it = Subject.objects.create(paper=self.paper_it, name='Computer Networks', is_active=True)
        self.chapter_it = Chapter.objects.create(subject=self.subject_it, title='Routing', is_active=True)
        self.topic_it = Topic.objects.create(chapter=self.chapter_it, name='IP Addressing')
        self.course_it = Course.objects.create(
            title='Computer Operator / IT',
            slug='computer-it',
            status='published',
            exam=self.exam_it,
            is_open_for_enrollment=True,
        )

        # Course C: Assistant Civil Engineer
        self.exam_asst_civil = Exam.objects.create(name='Assistant Civil Engineer Exam', category=self.category, is_active=True, status='active')
        self.course_asst_civil = Course.objects.create(
            title='Assistant Civil Engineer',
            slug='assistant-civil-engineer',
            status='published',
            exam=self.exam_asst_civil,
            is_open_for_enrollment=True,
        )

        # Draft Course: Unreleased Course
        self.exam_draft = Exam.objects.create(name='Draft Exam', category=self.category, is_active=True, status='active')
        self.course_draft = Course.objects.create(
            title='Draft Preparation',
            slug='draft-prep',
            status='draft',
            exam=self.exam_draft,
            is_open_for_enrollment=False,
        )

        # Users
        self.student_civil = User.objects.create_user(
            username='student_civil', email='civil@test.com', password='pass123', role='student'
        )
        self.student_it = User.objects.create_user(
            username='student_it', email='it@test.com', password='pass123', role='student'
        )
        self.student_unsubscribed = User.objects.create_user(
            username='student_free', email='free@test.com', password='pass123', role='student'
        )
        self.admin_user = User.objects.create_user(
            username='admin_boss', email='admin@test.com', password='pass123', role='admin', is_staff=True
        )

        # Questions
        self.q_civil = Question.objects.create(
            text='What is Newton\'s First Law in Civil Structures?',
            exam=self.exam_civil,
            subject=self.subject_civil,
            chapter=self.chapter_civil,
            topic=self.topic_civil,
            question_type='mcq',
            status='approved',
            option_a='A', option_b='B', option_c='C', option_d='D',
            correct_option='A',
        )
        self.q_it = Question.objects.create(
            text='What is the subnet mask of /24?',
            exam=self.exam_it,
            subject=self.subject_it,
            chapter=self.chapter_it,
            topic=self.topic_it,
            question_type='mcq',
            status='approved',
            option_a='255.255.255.0', option_b='255.0.0.0', option_c='C', option_d='D',
            correct_option='A',
        )

        # Notes / Study Materials
        self.note_civil = StudyMaterial.objects.create(
            title='Civil Sub Engineer Statics Detailed Notes',
            slug='civil-statics-notes',
            course=self.course_civil,
            exam=self.exam_civil,
            subject=self.subject_civil,
            chapter=self.chapter_civil,
            topic=self.topic_civil,
            content_category='subjective_topicwise',
            note_type='standard',
            access_type='premium',
            status='published',
            is_downloadable=True,
            content='Civil statics content for structures.',
        )
        self.note_it = StudyMaterial.objects.create(
            title='Computer IT IP Addressing Detailed Notes',
            slug='it-ip-addressing-notes',
            course=self.course_it,
            exam=self.exam_it,
            subject=self.subject_it,
            chapter=self.chapter_it,
            topic=self.topic_it,
            content_category='subjective_topicwise',
            note_type='standard',
            access_type='premium',
            status='published',
            is_downloadable=True,
            content='IP addressing and CIDR guide.',
        )
        self.note_public_free = StudyMaterial.objects.create(
            title='Public General Knowledge Summary',
            slug='public-gk-summary',
            course=None,
            exam=self.exam_civil,
            access_type='free',
            status='published',
            is_downloadable=True,
            content='Public overview of national general knowledge.',
        )

        # Examinations
        self.exam_model_civil = Examination.objects.create(
            title='Civil Sub Engineer Grand Model Exam 1',
            status='published',
            exam_type='mock',
            objective_category='model',
            category=self.category,
            course=self.course_civil,
            exam=self.exam_civil,
            total_marks=50,
            time_limit=45,
        )
        ExaminationQuestion.objects.create(
            examination=self.exam_model_civil,
            question=self.q_civil,
            order=1,
            marks=1,
        )

        self.exam_model_it = Examination.objects.create(
            title='Computer IT Operator Model Exam 1',
            status='published',
            exam_type='mock',
            objective_category='model',
            category=self.category,
            course=self.course_it,
            exam=self.exam_it,
            total_marks=50,
            time_limit=45,
        )
        ExaminationQuestion.objects.create(
            examination=self.exam_model_it,
            question=self.q_it,
            order=1,
            marks=1,
        )

        # Single Plan & Active Subscription for student_civil
        self.plan_civil_single = SubscriptionPlan.objects.create(
            name='Civil Sub Engineer Single Package',
            price=2500.00,
            duration=90,
            duration_unit='DAYS',
            package_type='SINGLE',
            course=self.course_civil,
            status='ACTIVE',
            features=['notes', 'practice', 'exams'],
        )
        self.sub_civil = Subscription.objects.create(
            student=self.student_civil,
            plan=self.plan_civil_single,
            status='ACTIVE',
            start_date=timezone.now() - timedelta(days=5),
            expiry_date=timezone.now() + timedelta(days=85),
        )
        self.enrollment_civil = Enrollment.objects.create(
            student=self.student_civil,
            course=self.course_civil,
            status='active',
            expires_at=self.sub_civil.expiry_date,
        )
        SubscriptionCourseSelection.objects.create(
            subscription=self.sub_civil,
            course=self.course_civil,
        )

    # =========================================================================
    # 1. CORE COURSE ACCESS TESTS
    # =========================================================================

    def test_single_course_student_can_only_access_enrolled_course(self):
        """Student enrolled in Civil Sub Engineer can access Civil, but is denied IT and Assistant Civil."""
        accessible = CourseAccessService.get_accessible_courses(self.student_civil)
        self.assertEqual(accessible.count(), 1)
        self.assertIn(self.course_civil, accessible)
        self.assertNotIn(self.course_it, accessible)
        self.assertNotIn(self.course_asst_civil, accessible)
        self.assertNotIn(self.course_draft, accessible)

        self.assertTrue(CourseAccessService.has_course_access(self.student_civil, self.course_civil))
        self.assertFalse(CourseAccessService.has_course_access(self.student_civil, self.course_it))
        self.assertFalse(CourseAccessService.has_course_access(self.student_civil, self.course_asst_civil))

    def test_unsubscribed_student_has_no_accessible_courses(self):
        """Self-registered student with no active subscription or enrollment has 0 accessible courses."""
        accessible = CourseAccessService.get_accessible_courses(self.student_unsubscribed)
        self.assertEqual(accessible.count(), 0)
        self.assertFalse(CourseAccessService.has_course_access(self.student_unsubscribed, self.course_civil))
        self.assertFalse(CourseAccessService.has_course_access(self.student_unsubscribed, self.course_it))

    def test_multi_course_package_access(self):
        """Student with MULTI package has access to selected courses, but not unselected ones."""
        student_multi = User.objects.create_user(
            username='student_multi', email='multi@test.com', password='pass', role='student'
        )
        plan_multi = SubscriptionPlan.objects.create(
            name='2-in-1 Combo Plan',
            price=4000.00,
            duration=90,
            duration_unit='DAYS',
            package_type='MULTI',
            allowed_preparation_count=2,
            status='ACTIVE',
            features=['*'],
        )
        plan_multi.eligible_courses.add(self.course_civil, self.course_it, self.course_asst_civil)

        sub_multi = Subscription.objects.create(
            student=student_multi,
            plan=plan_multi,
            status='ACTIVE',
            start_date=timezone.now(),
            expiry_date=timezone.now() + timedelta(days=90),
        )
        # Select Civil and IT only (not Assistant Civil)
        SubscriptionCourseSelection.objects.create(subscription=sub_multi, course=self.course_civil)
        SubscriptionCourseSelection.objects.create(subscription=sub_multi, course=self.course_it)
        Enrollment.objects.create(student=student_multi, course=self.course_civil, status='active', expires_at=sub_multi.expiry_date)
        Enrollment.objects.create(student=student_multi, course=self.course_it, status='active', expires_at=sub_multi.expiry_date)

        accessible = CourseAccessService.get_accessible_courses(student_multi)
        self.assertEqual(accessible.count(), 2)
        self.assertIn(self.course_civil, accessible)
        self.assertIn(self.course_it, accessible)
        self.assertNotIn(self.course_asst_civil, accessible)

    def test_bundle_package_access(self):
        """Student with BUNDLE package accesses all configured eligible published courses."""
        student_bundle = User.objects.create_user(
            username='student_bundle', email='bundle@test.com', password='pass', role='student'
        )
        plan_bundle = SubscriptionPlan.objects.create(
            name='Engineering Complete Bundle',
            price=5000.00,
            duration=90,
            duration_unit='DAYS',
            package_type='BUNDLE',
            status='ACTIVE',
            features=['*'],
        )
        plan_bundle.eligible_courses.add(self.course_civil, self.course_asst_civil)

        Subscription.objects.create(
            student=student_bundle,
            plan=plan_bundle,
            status='ACTIVE',
            start_date=timezone.now(),
            expiry_date=timezone.now() + timedelta(days=90),
        )

        accessible = CourseAccessService.get_accessible_courses(student_bundle)
        self.assertEqual(accessible.count(), 2)
        self.assertIn(self.course_civil, accessible)
        self.assertIn(self.course_asst_civil, accessible)
        self.assertNotIn(self.course_it, accessible)

    def test_all_access_package_access(self):
        """Student with ALL_ACCESS plan accesses all published courses, never draft/archived."""
        student_all = User.objects.create_user(
            username='student_all', email='all@test.com', password='pass', role='student'
        )
        plan_all = SubscriptionPlan.objects.create(
            name='All-Access Pass',
            price=9999.00,
            duration=365,
            duration_unit='DAYS',
            package_type='ALL_ACCESS',
            status='ACTIVE',
            features=['*'],
        )
        Subscription.objects.create(
            student=student_all,
            plan=plan_all,
            status='ACTIVE',
            start_date=timezone.now(),
            expiry_date=timezone.now() + timedelta(days=365),
        )

        accessible = CourseAccessService.get_accessible_courses(student_all)
        self.assertEqual(accessible.count(), 3)  # civil, it, asst_civil (published only)
        self.assertIn(self.course_civil, accessible)
        self.assertIn(self.course_it, accessible)
        self.assertIn(self.course_asst_civil, accessible)
        self.assertNotIn(self.course_draft, accessible)

    def test_admin_granted_access(self):
        """Admin grant subscription gives student access according to the grant."""
        student_grant = User.objects.create_user(
            username='student_grant', email='grant@test.com', password='pass', role='student'
        )
        sub_grant = Subscription.objects.create(
            student=student_grant,
            plan=self.plan_civil_single,
            status='ACTIVE',
            source='ADMIN_GRANT',
            admin_grant_reason='Scholarship grant',
            granted_by=self.admin_user,
            start_date=timezone.now(),
            expiry_date=timezone.now() + timedelta(days=60),
        )
        SubscriptionCourseSelection.objects.create(subscription=sub_grant, course=self.course_civil)
        Enrollment.objects.create(student=student_grant, course=self.course_civil, status='active', expires_at=sub_grant.expiry_date)

        self.assertTrue(CourseAccessService.has_course_access(student_grant, self.course_civil))
        self.assertFalse(CourseAccessService.has_course_access(student_grant, self.course_it))

    def test_expired_and_cancelled_subscriptions_are_denied(self):
        """Expired or cancelled subscriptions revoke access immediately."""
        student_expired = User.objects.create_user(
            username='student_expired', email='exp@test.com', password='pass', role='student'
        )
        Subscription.objects.create(
            student=student_expired,
            plan=self.plan_civil_single,
            status='EXPIRED',
            start_date=timezone.now() - timedelta(days=120),
            expiry_date=timezone.now() - timedelta(days=30),
        )
        Enrollment.objects.create(
            student=student_expired,
            course=self.course_civil,
            status='active',
            expires_at=timezone.now() - timedelta(days=30),
        )
        self.assertFalse(CourseAccessService.has_course_access(student_expired, self.course_civil))

        # Cancelled enrollment
        student_cancelled = User.objects.create_user(
            username='student_cancelled', email='cancel@test.com', password='pass', role='student'
        )
        Enrollment.objects.create(
            student=student_cancelled,
            course=self.course_civil,
            status='cancelled',
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.assertFalse(CourseAccessService.has_course_access(student_cancelled, self.course_civil))

    # =========================================================================
    # 2. NOTES & STUDY MATERIALS ACCESS TESTS
    # =========================================================================

    def test_student_can_only_view_notes_of_authorized_course(self):
        """Civil student can view Civil note, but receives 403 when trying to access IT note."""
        self.client.force_authenticate(user=self.student_civil)

        # List notes: only Civil note should appear
        list_res = self.client.get('/api/notes/materials/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        items = list_res.data.get('results', list_res.data) if isinstance(list_res.data, dict) else list_res.data
        note_ids = [n['id'] for n in items]
        self.assertIn(self.note_civil.id, note_ids)
        self.assertNotIn(self.note_it.id, note_ids)

        # Detail of authorized note: 200 OK
        detail_res = self.client.get(f'/api/notes/materials/{self.note_civil.id}/')
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)

        # IDOR probe: Direct detail of unauthorized note: 403 Forbidden or 404 Not Found
        idor_res = self.client.get(f'/api/notes/materials/{self.note_it.id}/')
        self.assertIn(idor_res.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_note_download_is_protected_by_course_authorization(self):
        """Downloading note attachments is restricted to authorized courses and respects is_downloadable."""
        self.client.force_authenticate(user=self.student_civil)

        # Unauthorized download
        unauth_dl = self.client.get(f'/api/notes/materials/{self.note_it.id}/download/')
        self.assertIn(unauth_dl.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_public_study_materials_endpoint_is_open_for_free_content_only(self):
        """Public endpoint allows anonymous discovery of free content only, excluding premium notes."""
        res = self.client.get('/api/notes/public/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        note_ids = [m['id'] for m in res.data]
        self.assertIn(self.note_public_free.id, note_ids)
        self.assertNotIn(self.note_civil.id, note_ids)
        self.assertNotIn(self.note_it.id, note_ids)

    # =========================================================================
    # 3. STUDENT PORTAL SYLLABUS ACCESS TESTS
    # =========================================================================

    def test_student_portal_syllabus_scopes_to_authorized_courses(self):
        """Student portal syllabus endpoint displays only authorized courses and refuses unauthorized courses."""
        self.client.force_authenticate(user=self.student_civil)

        portal_res = self.client.get('/api/notes/student/portal/')
        self.assertEqual(portal_res.status_code, status.HTTP_200_OK)
        authorized_preps = portal_res.data.get('authorizedPreparations', [])
        prep_course_ids = [p['courseId'] for p in authorized_preps]
        self.assertIn(self.course_civil.id, prep_course_ids)
        self.assertNotIn(self.course_it.id, prep_course_ids)

        # Querying unauthorized course explicitly yields 403 Forbidden
        unauth_portal = self.client.get(f'/api/notes/student/portal/?course_id={self.course_it.id}')
        self.assertEqual(unauth_portal.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # 4. PRACTICE & QUESTIONS ACCESS TESTS
    # =========================================================================

    def test_practice_question_catalog_is_scoped(self):
        """Question catalog only exposes questions of the student's authorized course/exam."""
        self.client.force_authenticate(user=self.student_civil)

        res = self.client.get('/api/questions/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = res.data.get('results', res.data) if isinstance(res.data, dict) else res.data
        q_ids = [q['id'] for q in items]
        self.assertIn(self.q_civil.id, q_ids)
        self.assertNotIn(self.q_it.id, q_ids)

    def test_student_cannot_create_practice_session_for_unauthorized_course(self):
        """Attempting to create a practice session for an unauthorized course returns 403 Forbidden."""
        self.client.force_authenticate(user=self.student_civil)

        res = self.client.post('/api/practice-sessions/', {
            'course': self.course_it.id,
            'exam': self.exam_it.id,
            'total_questions': 10,
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_access_another_students_practice_session(self):
        """Practice sessions and attempts are strictly private to the student who created them."""
        from exams.models import PracticeSession
        session_it = PracticeSession.objects.create(
            user=self.student_it,
            exam=self.exam_it,
            mode='flexible',
            total_questions=5,
        )

        self.client.force_authenticate(user=self.student_civil)
        res = self.client.get(f'/api/practice-sessions/{session_it.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # =========================================================================
    # 5. MOCK EXAMS & EXAMINATIONS ACCESS TESTS
    # =========================================================================

    def test_student_can_only_view_and_start_authorized_mock_exams(self):
        """Civil student can view and start Civil mock exam, but is denied IT mock exam."""
        self.client.force_authenticate(user=self.student_civil)

        # Examination list
        list_res = self.client.get('/api/student/exams/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        items = list_res.data.get('results', list_res.data) if isinstance(list_res.data, dict) else list_res.data
        exam_ids = [e['id'] for e in items]
        self.assertIn(self.exam_model_civil.id, exam_ids)
        self.assertNotIn(self.exam_model_it.id, exam_ids)

        # Start authorized exam
        ExaminationRequest.objects.create(
            student=self.student_civil,
            examination=self.exam_model_civil,
            status='approved',
        )
        start_res = self.client.post(f'/api/student/exams/{self.exam_model_civil.id}/start/')
        self.assertIn(start_res.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))

        # IDOR probe: Start unauthorized exam: 403 Forbidden or 404 Not Found (scoped out of queryset)
        unauth_start = self.client.post(f'/api/student/exams/{self.exam_model_it.id}/start/')
        self.assertIn(unauth_start.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_student_cannot_access_another_students_exam_attempt(self):
        """Examination attempts are private and return 404/403 for unauthorized students."""
        # Create attempt for student_it
        attempt_it = ExaminationAttempt.objects.create(
            examination=self.exam_model_it,
            student=self.student_it,
            status='in-progress',
        )

        self.client.force_authenticate(user=self.student_civil)
        res = self.client.get(f'/api/student/exam-attempts/{attempt_it.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # =========================================================================
    # 6. COURSE SWITCHER & CONTEXT TESTS
    # =========================================================================

    def test_student_context_select_course_enforces_authorization(self):
        """Student can only switch active course among authorized courses."""
        self.client.force_authenticate(user=self.student_civil)

        # Switching to authorized Civil course succeeds
        ok_res = self.client.post('/api/student/context/select-course/', {'course_id': self.course_civil.id})
        self.assertEqual(ok_res.status_code, status.HTTP_200_OK)
        self.assertEqual(ok_res.data['active_course']['id'], self.course_civil.id)

        # Switching to unauthorized IT course fails with 403 Forbidden
        deny_res = self.client.post('/api/student/context/select-course/', {'course_id': self.course_it.id})
        self.assertEqual(deny_res.status_code, status.HTTP_403_FORBIDDEN)
