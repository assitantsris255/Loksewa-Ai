import os
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from courses.models import Course, Enrollment
from exams.assignment_service import SubjectiveExamAssignmentService
from exams.models import (
    Exam,
    ExamCategory,
    Examination,
    ExaminationRequest,
    Paper,
    Subject,
    SubjectiveQuestionSet,
)

User = get_user_model()


def make_pdf_bytes():
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF"


class SubjectiveQuestionBankAssignmentTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_directory = TemporaryDirectory()
        cls._storage_override = override_settings(
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
            },
            MEDIA_ROOT=cls._media_directory.name,
        )
        cls._storage_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._storage_override.disable()
        cls._media_directory.cleanup()

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='subjective_admin',
            email='admin@example.com',
            password='Password123!',
            is_staff=True,
            role='admin',
        )
        self.student = User.objects.create_user(
            username='subjective_student',
            email='student@example.com',
            password='Password123!',
            role='student',
        )

        self.category = ExamCategory.objects.create(name='PSC Nepal', order=1)
        self.exam = Exam.objects.create(category=self.category, name='Section Officer', is_active=True)
        self.paper = Paper.objects.create(exam=self.exam, name='Paper I', order=1)
        self.subject = Subject.objects.create(paper=self.paper, name='Constitutional Law', code='CL', order=1)
        self.course = Course.objects.create(title='Officer Written Batch', exam=self.exam, status='published')
        Enrollment.objects.create(student=self.student, course=self.course, status='active')

    def test_auto_assigns_active_question_set_for_pending_request(self):
        pdf = SimpleUploadedFile('set-one.pdf', make_pdf_bytes(), content_type='application/pdf')
        qset = SubjectiveQuestionSet.objects.create(
            title='PSC Set One',
            description='Sample paper',
            pdf_file=pdf,
            exam_category=self.category,
            level=self.exam,
            course=self.course,
            subject=self.subject,
            duration_minutes=180,
            total_marks=100,
            question_count=10,
            status='active',
            created_by=self.admin,
        )
        request = ExaminationRequest.objects.create(
            student=self.student,
            academic_exam=self.exam,
            course=self.course,
            subject=self.subject,
            request_type='subjective_live',
            status='pending',
        )

        exam = SubjectiveExamAssignmentService.assign_subjective_exam(request, mode='auto')

        self.assertIsNotNone(exam)
        self.assertEqual(exam.subjective_question_set_id, qset.id)
        self.assertEqual(request.examination_id, exam.id)
        self.assertEqual(request.status, 'approved')
        self.assertEqual(exam.title, qset.title)

    def test_manual_assignment_is_idempotent_for_same_request(self):
        pdf = SimpleUploadedFile('set-two.pdf', make_pdf_bytes(), content_type='application/pdf')
        qset = SubjectiveQuestionSet.objects.create(
            title='PSC Set Two',
            pdf_file=pdf,
            exam_category=self.category,
            level=self.exam,
            course=self.course,
            subject=self.subject,
            duration_minutes=180,
            total_marks=100,
            question_count=8,
            status='active',
            created_by=self.admin,
        )
        request = ExaminationRequest.objects.create(
            student=self.student,
            academic_exam=self.exam,
            course=self.course,
            subject=self.subject,
            request_type='subjective_live',
            status='pending',
        )

        first = SubjectiveExamAssignmentService.assign_subjective_exam(request, mode='manual', question_set_id=qset.id)
        second = SubjectiveExamAssignmentService.assign_subjective_exam(request, mode='manual', question_set_id=qset.id)

        self.assertEqual(first.id, second.id)
        self.assertEqual(Examination.objects.filter(student_requests=request).count(), 1)

    def test_no_eligible_set_keeps_request_pending(self):
        request = ExaminationRequest.objects.create(
            student=self.student,
            academic_exam=self.exam,
            course=self.course,
            subject=self.subject,
            request_type='subjective_live',
            status='pending',
        )

        exam = SubjectiveExamAssignmentService.assign_subjective_exam(request, mode='auto')

        self.assertIsNone(exam)
        request.refresh_from_db()
        self.assertEqual(request.status, 'pending')
        self.assertIsNone(request.examination_id)

    def test_admin_can_list_subjective_question_sets(self):
        pdf = SimpleUploadedFile('set-admin.pdf', make_pdf_bytes(), content_type='application/pdf')
        SubjectiveQuestionSet.objects.create(
            title='Admin Bank Set',
            pdf_file=pdf,
            exam_category=self.category,
            level=self.exam,
            course=self.course,
            subject=self.subject,
            duration_minutes=180,
            total_marks=100,
            question_count=5,
            status='active',
            created_by=self.admin,
        )

        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/admin/subjective-question-sets/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)
