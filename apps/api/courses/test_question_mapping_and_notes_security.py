"""
Comprehensive tests for:
1. Question academic & course mapping access control (CourseAccessService, QuestionSelectionService, Examination student submission).
2. Secure Notes file downloads and media protection.
"""
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import User
from exams.models import (
    ExamCategory, Exam, Paper, Subject, Chapter, Topic,
    Question, Examination, ExaminationAttempt, ExaminationQuestion
)
from courses.models import Course, Enrollment, TeacherCourseAssignment
from courses.services.course_access_service import CourseAccessService
from exams.selection_service import QuestionSelectionService
from notes.models import StudyMaterial


class QuestionMappingAndNotesSecurityTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.upload_patch = patch('core.google_drive.upload_file', side_effect=lambda name, f, **kwargs: {'id': 'mock_drive_id_123', 'name': name})
        cls.download_patch = patch('core.google_drive.download_file', return_value=b'%PDF-1.4 mock pdf content')
        cls.upload_patch.start()
        cls.download_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.upload_patch.stop()
        cls.download_patch.stop()
        super().tearDownClass()

    def setUp(self):
        # Users
        self.admin = User.objects.create_superuser(
            username='admin_user', email='admin@test.com', password='adminpassword123', role='admin'
        )
        self.teacher = User.objects.create_user(
            username='teacher_user', email='teacher@test.com', password='teacherpassword123', role='teacher'
        )
        self.student_a = User.objects.create_user(
            username='student_a', email='student_a@test.com', password='studentpassword123', role='student'
        )
        self.student_b = User.objects.create_user(
            username='student_b', email='student_b@test.com', password='studentpassword123', role='student'
        )

        # Academic Category
        self.category = ExamCategory.objects.create(name='PSC Technical')

        # Course A hierarchy
        self.exam_a = Exam.objects.create(name='Civil Sub Engineer', category=self.category, is_active=True)
        self.paper_a = Paper.objects.create(exam=self.exam_a, name='Technical Paper A')
        self.subject_a = Subject.objects.create(paper=self.paper_a, name='Surveying')
        self.chapter_a = Chapter.objects.create(subject=self.subject_a, title='Leveling', order=1)
        self.topic_a = Topic.objects.create(chapter=self.chapter_a, name='Direct Leveling', order=1)
        self.course_a = Course.objects.create(
            title='Civil Sub Engineer Preparation',
            slug='civil-sub-engineer',
            exam=self.exam_a,
            status='published',
            is_open_for_enrollment=True,
            duration_months=3
        )

        # Course B hierarchy
        self.exam_b = Exam.objects.create(name='Electrical Engineer', category=self.category, is_active=True)
        self.paper_b = Paper.objects.create(exam=self.exam_b, name='Technical Paper B')
        self.subject_b = Subject.objects.create(paper=self.paper_b, name='Circuits')
        self.chapter_b = Chapter.objects.create(subject=self.subject_b, title='AC Analysis', order=1)
        self.topic_b = Topic.objects.create(chapter=self.chapter_b, name='Resonance', order=1)
        self.course_b = Course.objects.create(
            title='Electrical Engineer Preparation',
            slug='electrical-engineer',
            exam=self.exam_b,
            status='published',
            is_open_for_enrollment=True,
            duration_months=3
        )

        # Unassigned Exam (no published course)
        self.exam_unassigned = Exam.objects.create(name='Draft Unassigned Exam', category=self.category, is_active=True)

        # Questions
        self.question_a = Question.objects.create(
            exam=self.exam_a,
            topic=self.topic_a,
            text='What is bench mark in surveying?',
            question_type='mcq',
            status='approved',
            difficulty='medium',
            marks=1
        )
        self.question_b = Question.objects.create(
            exam=self.exam_b,
            topic=self.topic_b,
            text='What is resonant frequency?',
            question_type='mcq',
            status='approved',
            difficulty='medium',
            marks=1
        )
        self.question_incomplete = Question.objects.create(
            exam=self.exam_a,
            topic=None,
            text='Incomplete question lacking topic',
            question_type='mcq',
            status='approved',
            difficulty='medium',
            marks=1
        )
        self.question_unassigned = Question.objects.create(
            exam=self.exam_unassigned,
            topic=None,
            text='Unassigned question lacking course',
            question_type='mcq',
            status='approved',
            difficulty='medium',
            marks=1
        )

        # Enrollments: Student A is enrolled only in Course A
        self.enrollment_a = Enrollment.objects.create(
            student=self.student_a,
            course=self.course_a,
            status='active'
        )

        # Teacher Assignment: Teacher assigned to Course A
        TeacherCourseAssignment.objects.create(
            teacher=self.teacher,
            course=self.course_a
        )

        # Study Materials (with exam, course, and subject set)
        test_file_a = SimpleUploadedFile("surveying_notes.pdf", b"%PDF-1.4 test surveying content", content_type="application/pdf")
        self.note_a = StudyMaterial.objects.create(
            title='Surveying Fundamentals',
            exam=self.exam_a,
            course=self.course_a,
            subject=self.subject_a,
            file=test_file_a,
            status='published',
            access_type='premium',
            is_downloadable=True
        )

        test_file_b = SimpleUploadedFile("circuits_notes.pdf", b"%PDF-1.4 test circuits content", content_type="application/pdf")
        self.note_b = StudyMaterial.objects.create(
            title='Circuits Advanced',
            exam=self.exam_b,
            course=self.course_b,
            subject=self.subject_b,
            file=test_file_b,
            status='published',
            access_type='premium',
            is_downloadable=True
        )

    # ── PART 1: QUESTION MAPPING & ACCESS CONTROL TESTS ──────────────────────────

    def test_question_mapping_status_resolution(self):
        """Verify mapping status classification: mapped, incomplete, unassigned."""
        self.assertEqual(CourseAccessService.get_question_mapping_status(self.question_a), 'mapped')
        self.assertEqual(CourseAccessService.get_question_mapping_status(self.question_incomplete), 'incomplete')
        self.assertEqual(CourseAccessService.get_question_mapping_status(self.question_unassigned), 'unassigned')

    def test_student_has_access_to_mapped_enrolled_course_question(self):
        """Student with Course A can access question_a."""
        self.assertTrue(CourseAccessService.has_question_access(self.student_a, self.question_a))

    def test_student_denied_access_to_foreign_course_question(self):
        """Student with Course A is denied access to question_b (Course B)."""
        self.assertFalse(CourseAccessService.has_question_access(self.student_a, self.question_b))

    def test_student_denied_access_to_unassigned_or_incomplete_question(self):
        """Unassigned and incomplete questions are never accessible to student practice."""
        self.assertFalse(CourseAccessService.has_question_access(self.student_a, self.question_unassigned))
        self.assertFalse(CourseAccessService.has_question_access(self.student_a, self.question_incomplete))

    def test_filter_questions_queryset_excludes_unmapped_and_foreign_questions(self):
        """filter_questions_queryset returns strictly Course A questions for student_a."""
        qs = CourseAccessService.filter_questions_queryset(self.student_a, Question.objects.all())
        question_ids = list(qs.values_list('id', flat=True))
        self.assertIn(self.question_a.id, question_ids)
        self.assertNotIn(self.question_b.id, question_ids)
        self.assertNotIn(self.question_unassigned.id, question_ids)
        self.assertNotIn(self.question_incomplete.id, question_ids)

    def test_question_selection_service_filters_to_course(self):
        """QuestionSelectionService respects course_id filtering."""
        service = QuestionSelectionService()
        result = service.select(course_id=self.course_a.id, count=10)
        questions = result.get("questions", [])
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].id, self.question_a.id)

    def test_examination_answer_endpoint_rejects_foreign_question(self):
        """Exam answer submission must reject questions not part of the attempt's examination."""
        exam_inst = Examination.objects.create(
            title='Surveying Midterm',
            exam_type='mock',
            category=self.category,
            exam=self.exam_a,
            course=self.course_a,
            status='published',
            total_marks=50,
            passing_marks=20,
            time_limit=45
        )
        ExaminationQuestion.objects.create(
            examination=exam_inst,
            question=self.question_a,
            order=1
        )
        attempt = ExaminationAttempt.objects.create(
            examination=exam_inst,
            student=self.student_a,
            status='in-progress'
        )

        self.client.force_authenticate(user=self.student_a)
        url = f'/api/student/exam-attempts/{attempt.id}/answer/'
        payload = {
            'question_id': self.question_b.id,
            'selected_option': 'A',
            'time_spent': 30
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('does not belong to this examination', str(res.data))

    # ── PART 2: SECURE NOTES FILE DOWNLOAD TESTS ─────────────────────────────────

    def test_authorized_student_can_download_enrolled_note(self):
        """Student A can download Note A belonging to Course A."""
        self.client.force_authenticate(user=self.student_a)
        url = f'/api/notes/materials/{self.note_a.id}/download/'
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('attachment', res['Content-Disposition'])

    def test_unauthorized_student_cannot_download_foreign_note(self):
        """Student A cannot download Note B (Course B). Returns 403 or 404 denying access."""
        self.client.force_authenticate(user=self.student_a)
        url = f'/api/notes/materials/{self.note_b.id}/download/'
        res = self.client.get(url)
        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_unauthenticated_user_cannot_download_notes(self):
        """Anonymous user is rejected with 401 Unauthorized."""
        url = f'/api/notes/materials/{self.note_a.id}/download/'
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_and_teacher_can_download_notes(self):
        """Admin and assigned Teacher can download course notes."""
        self.client.force_authenticate(user=self.admin)
        url = f'/api/notes/admin/materials/{self.note_a.id}/download/'
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.teacher)
        url_teacher = f'/api/notes/teacher/materials/{self.note_a.id}/download/'
        res_teacher = self.client.get(url_teacher)
        self.assertEqual(res_teacher.status_code, status.HTTP_200_OK)

    def test_direct_media_url_blocked_for_protected_files(self):
        """Direct access to /media/study_materials/... is blocked with 403 Forbidden."""
        direct_url = '/media/study_materials/pdfs/surveying_notes.pdf'
        res = self.client.get(direct_url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('protected media', res.content.decode('utf-8').lower())

    def test_drive_media_proxy_blocked_for_study_materials(self):
        """Direct access via drive media proxy is blocked with 403 Forbidden."""
        url = '/api/media/drive/mock_drive_id_123/'
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_note_serializer_masks_direct_media_urls(self):
        """Study material serializers must return download endpoint URL, never raw file paths."""
        self.client.force_authenticate(user=self.student_a)
        res = self.client.get(f'/api/notes/materials/{self.note_a.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        expected_download_url = f'/api/notes/materials/{self.note_a.id}/download/'
        self.assertTrue(res.data['file'].endswith(expected_download_url))
        self.assertTrue(res.data['file_url'].endswith(expected_download_url))
