import io
from PIL import Image
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from rest_framework import status

from openpyxl import Workbook
from exams.models import (
    ExamCategory, Exam, Paper, Subject, Topic, Chapter,
    Examination, ExaminationQuestion, ExaminationAttempt, ExaminationRequest, Question
)
from courses.models import Course, Enrollment

User = get_user_model()


def make_xlsx(rows, headers=None):
    """Build an in-memory .xlsx upload matching the admin Excel template."""
    headers = headers or ['SN', 'Questions', 'Mark', 'Option A', 'Option B', 'Option C', 'Option D',
                           'Correct Answer', 'Explanation', 'Hint']
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = 'questions.xlsx'
    return buf


def create_dummy_pdf(num_pages=1):
    """Generates a minimal valid in-memory PDF using Pillow."""
    images = [Image.new('RGB', (200, 200), color='white') for _ in range(num_pages)]
    buf = io.BytesIO()
    images[0].save(buf, format='PDF', save_all=True, append_images=images[1:])
    buf.seek(0)
    return buf.getvalue()


class ExamImportWorkflowTests(APITestCase):
    """
    Comprehensive tests for the unified Admin Exam Import workflow:
    1. Objective Exam Import:
       - Questions enter the canonical Master Question Bank (Question model).
       - Duplicate questions reuse existing canonical Question records.
       - ExaminationQuestion links to canonical Question.
       - Exam duration (time_limit) is persisted and server-authoritative.
    2. Subjective Exam Import:
       - Question Paper PDF is attached to Examination.
       - Master Question Bank question count does NOT increase (zero Question records created).
       - Dual timers (Writing Time + Upload Window) are persisted and enforced server-side.
    """

    def setUp(self):
        # 1. Admin and Student Users
        self.admin = User.objects.create_superuser(
            username='admin_import',
            email='admin_import@loksewa.ai',
            password='Password123!',
            is_staff=True,
            role='admin'
        )
        self.student = User.objects.create_user(
            username='student_import',
            email='student_import@loksewa.ai',
            password='Password123!',
            role='student'
        )

        # 2. Academic Taxonomy
        self.category = ExamCategory.objects.create(name='PSC Nepal', order=1)
        self.exam = Exam.objects.create(category=self.category, name='Section Officer', is_active=True)
        self.paper = Paper.objects.create(exam=self.exam, name='Paper I')
        self.subject = Subject.objects.create(paper=self.paper, name='General Knowledge')
        self.chapter = Chapter.objects.create(subject=self.subject, title='Geography of Nepal')
        self.topic = Topic.objects.create(chapter=self.chapter, name='Mountains and Rivers')

        # 3. Course and Enrollment for student
        self.course = Course.objects.create(title='Officer Comprehensive', exam=self.exam, status='published')
        Enrollment.objects.create(student=self.student, course=self.course, status='active')

    def test_01_objective_exam_import_populates_master_question_bank(self):
        """
        Objective Exam Import:
        - Uploading objective questions adds them to the canonical Master Question Bank (Question).
        - Created ExaminationQuestion records reference those canonical questions.
        - Configured duration is saved as time_limit.
        """
        self.client.force_authenticate(user=self.admin)
        initial_q_count = Question.objects.count()

        # Step 1: Upload and analyze Excel file
        rows = [
            [1, 'What is the highest mountain peak in the world?', 1, 'K2', 'Mount Everest', 'Kangchenjunga', 'Lhotse', 'B', '8848.86m', 'Highest on Earth'],
            [2, 'What is the longest river in Nepal?', 1, 'Koshi', 'Gandaki', 'Karnali', 'Mahakali', 'C', 'Karnali is longest', 'Originates in Tibet'],
        ]
        upload_res = self.client.post('/api/admin/questions/import/upload/', {
            'file': make_xlsx(rows),
            'topic': self.topic.id,
            'question_type': 'mcq',
            'difficulty': 'medium',
        }, format='multipart')
        self.assertEqual(upload_res.status_code, status.HTTP_200_OK)
        import_id = upload_res.data['import_id']
        self.assertEqual(upload_res.data['valid_rows'], 2)

        # Step 2: Commit CSV -> enters Master Question Bank
        commit_res = self.client.post(f"/api/admin/questions/import/{import_id}/commit/")
        self.assertEqual(commit_res.status_code, status.HTTP_200_OK)
        new_q_ids = commit_res.data['question_ids']
        self.assertEqual(len(new_q_ids), 2)
        self.assertEqual(Question.objects.count(), initial_q_count + 2)

        # Step 3: Create Examination with duration
        exam_res = self.client.post('/api/admin/exams/', {
            'title': 'Section Officer Geography Mock Test',
            'exam_type': 'mock',
            'objective_category': 'model',
            'category': self.category.id,
            'exam': self.exam.id,
            'subject': self.subject.id,
            'time_limit': 45, # 45 minutes duration
        }, format='json')
        self.assertEqual(exam_res.status_code, status.HTTP_201_CREATED)
        exam_id = exam_res.data['id']
        self.assertEqual(exam_res.data['time_limit'], 45)

        # Step 4: Attach questions to exam
        add_res = self.client.post(f"/api/admin/exams/{exam_id}/add-questions/", {
            'question_ids': new_q_ids
        }, format='json')
        self.assertEqual(add_res.status_code, status.HTTP_200_OK)

        # Verify ExaminationQuestion links directly to canonical Question records
        exam = Examination.objects.get(id=exam_id)
        self.assertEqual(exam.examination_questions.count(), 2)
        eq_questions = [eq.question for eq in exam.examination_questions.all()]
        self.assertEqual(set(q.id for q in eq_questions), set(new_q_ids))
        for q in eq_questions:
            self.assertEqual(q.topic, self.topic)
            self.assertEqual(q.status, 'approved')

    def test_02_objective_exam_duplicate_reuse_without_polluting_question_bank(self):
        """
        Duplicate Objective Questions:
        - When an imported file contains questions that already exist in the Question Bank,
          the system reuses the existing canonical Question without creating duplicate Question records.
        - The Examination attaches both new and reused canonical questions via ExaminationQuestion.
        """
        self.client.force_authenticate(user=self.admin)

        # Create one existing question in Master Question Bank
        existing_q = Question.objects.create(
            topic=self.topic,
            question_type='mcq',
            text='What is the capital of Nepal?',
            option_a='Kathmandu',
            option_b='Pokhara',
            option_c='Lalitpur',
            option_d='Biratnagar',
            correct_option='A',
            marks=1,
            status='approved',
            created_by=self.admin,
            question_id='Q-000999',
        )
        initial_q_count = Question.objects.count()

        # Import a file with 1 existing duplicate and 1 brand new question
        rows = [
            [1, 'What is the capital of Nepal?', 1, 'Kathmandu', 'Pokhara', 'Lalitpur', 'Biratnagar', 'A', 'Kathmandu is capital', ''],
            [2, 'What is the national bird of Nepal?', 1, 'Danphe', 'Sparrow', 'Pigeon', 'Peacock', 'A', 'Lophophorus impejanus', ''],
        ]
        upload_res = self.client.post('/api/admin/questions/import/upload/', {
            'file': make_xlsx(rows),
            'topic': self.topic.id,
            'question_type': 'mcq',
            'difficulty': 'medium',
        }, format='multipart')
        self.assertEqual(upload_res.status_code, status.HTTP_200_OK)
        import_id = upload_res.data['import_id']
        self.assertEqual(upload_res.data['duplicate_rows'], 1)
        self.assertEqual(upload_res.data['valid_rows'], 1)

        # Commit import
        commit_res = self.client.post(f"/api/admin/questions/import/{import_id}/commit/")
        self.assertEqual(commit_res.status_code, status.HTTP_200_OK)

        # Verify only 1 new question was added to Question Bank (no duplicate Question created!)
        self.assertEqual(Question.objects.count(), initial_q_count + 1)
        self.assertEqual(commit_res.data['imported_count'], 1)
        self.assertIn(existing_q.id, commit_res.data['all_question_ids'])

        # Create Examination and attach all questions (new + reused)
        exam_res = self.client.post('/api/admin/exams/', {
            'title': 'General Knowledge Mixed Test',
            'exam_type': 'mock',
            'category': self.category.id,
            'exam': self.exam.id,
            'time_limit': 60,
        }, format='json')
        exam_id = exam_res.data['id']

        attach_res = self.client.post(f"/api/admin/exams/{exam_id}/add-questions/", {
            'question_ids': commit_res.data['all_question_ids']
        }, format='json')
        self.assertEqual(attach_res.status_code, status.HTTP_200_OK)

        # Both the reused canonical question and the new question are linked to this exam
        exam = Examination.objects.get(id=exam_id)
        self.assertEqual(exam.examination_questions.count(), 2)
        linked_ids = set(eq.question_id for eq in exam.examination_questions.all())
        self.assertIn(existing_q.id, linked_ids)

    def test_03_subjective_exam_import_creates_pdf_and_dual_timers_without_touching_question_bank(self):
        """
        Subjective Exam Import:
        - Creates a Subjective Examination with Question Paper PDF.
        - Persists Answer Writing Time (time_limit) and Answer Upload Time (upload_deadline_minutes).
        - CRITICAL: Master Question Bank question count does NOT increase (zero Question records created).
        - Question Paper PDF is attached and accessible securely.
        """
        self.client.force_authenticate(user=self.admin)
        initial_q_count = Question.objects.count()

        # Step 1: Create Subjective Examination with dual timers
        create_res = self.client.post('/api/admin/exams/', {
            'title': 'Section Officer Paper II - Subjective Written Examination',
            'exam_type': 'subjective',
            'category': self.category.id,
            'exam': self.exam.id,
            'subject': self.subject.id,
            'time_limit': 120, # 120 minutes writing time
            'upload_deadline_minutes': 30, # 30 minutes upload window
            'answer_upload_enabled': True,
            'allowed_file_types': 'jpg,jpeg,png,webp,pdf',
            'max_upload_size_mb': 50,
            'evaluation_type': 'admin',
            'status': 'draft',
        }, format='json')
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        exam_id = create_res.data['id']

        # Step 2: Upload Question Paper PDF
        pdf_bytes = create_dummy_pdf(num_pages=3)
        pdf_file = SimpleUploadedFile("paper2_subjective.pdf", pdf_bytes, content_type="application/pdf")
        upload_pdf_res = self.client.post(
            f"/api/admin/exams/{exam_id}/question-paper/",
            {'pdf_file': pdf_file},
            format='multipart'
        )
        self.assertEqual(upload_pdf_res.status_code, status.HTTP_200_OK)
        self.assertEqual(upload_pdf_res.data['page_count'], 3)

        # Step 3: Verify Master Question Bank is COMPLETELY UNTOUCHED
        self.assertEqual(Question.objects.count(), initial_q_count)
        self.assertFalse(Question.objects.filter(text__icontains='paper2').exists())

        # Step 4: Verify Examination model fields
        exam = Examination.objects.get(id=exam_id)
        self.assertEqual(exam.exam_type, 'subjective')
        self.assertEqual(exam.time_limit, 120)
        self.assertEqual(exam.upload_deadline_minutes, 30)
        self.assertTrue(exam.answer_upload_enabled)
        self.assertEqual(exam.question_paper_page_count, 3)
        self.assertTrue(bool(exam.question_paper_pdf))

    def test_04_server_authoritative_dual_timer_enforcement(self):
        """
        Server-Authoritative Timing for Subjective Exam:
        - Started attempt derives writing_expires_at and upload_expires_at from server timestamps.
        - Timer does not reset on client refresh or navigation.
        - Upload is allowed during upload window and rejected after upload window.
        """
        # Publish exam
        exam = Examination.objects.create(
            title='Subjective Timed Test',
            exam_type='subjective',
            category=self.category,
            exam=self.exam,
            time_limit=60, # 60 minutes writing
            upload_deadline_minutes=20, # 20 minutes upload
            answer_upload_enabled=True,
            status='published',
            created_by=self.admin,
        )

        ExaminationRequest.objects.create(
            student=self.student,
            examination=exam,
            status='approved',
        )

        # Student starts exam
        self.client.force_authenticate(user=self.student)
        start_res = self.client.post(f"/api/student/exams/{exam.id}/start/")
        self.assertEqual(start_res.status_code, status.HTTP_201_CREATED)
        attempt_id = start_res.data['id']

        # Get state (simulating first render, refresh, or back navigation)
        state_res = self.client.get(f"/api/student/exam-attempts/{attempt_id}/state/")
        self.assertEqual(state_res.status_code, status.HTTP_200_OK)
        data = state_res.data
        self.assertTrue(data['is_subjective'])
        self.assertIsNotNone(data['exam_expires_at'])
        self.assertIsNotNone(data['upload_expires_at'])
        self.assertGreater(data['remaining_seconds'], 0)
        self.assertGreater(data['upload_remaining_seconds'], data['remaining_seconds'])
        self.assertTrue(data['can_upload'])

        # Advance attempt past writing time (writing expired, upload window active)
        attempt = ExaminationAttempt.objects.get(id=attempt_id)
        attempt.started_at = timezone.now() - timedelta(minutes=65) # 65 mins ago > 60 mins writing
        attempt.save(update_fields=['started_at'])

        state_res2 = self.client.get(f"/api/student/exam-attempts/{attempt_id}/state/")
        self.assertEqual(state_res2.data['remaining_seconds'], 0)
        self.assertTrue(state_res2.data['is_exam_expired'])
        self.assertGreater(state_res2.data['upload_remaining_seconds'], 0)
        self.assertFalse(state_res2.data['is_upload_expired'])
        self.assertTrue(state_res2.data['can_upload'])

        # Advance attempt past upload window (both expired)
        attempt.started_at = timezone.now() - timedelta(minutes=85) # 85 mins ago > 60 + 20 mins
        attempt.save(update_fields=['started_at'])

        state_res3 = self.client.get(f"/api/student/exam-attempts/{attempt_id}/state/")
        self.assertEqual(state_res3.data['upload_remaining_seconds'], 0)
        self.assertTrue(state_res3.data['is_upload_expired'])
        self.assertFalse(state_res3.data['can_upload'])

        # Direct POST after deadline is rejected by backend
        pdf_bytes = create_dummy_pdf(1)
        pdf_file = SimpleUploadedFile("late_submission.pdf", pdf_bytes, content_type="application/pdf")
        upload_res = self.client.post(
            f"/api/student/exam-attempts/{attempt_id}/answer-sheet/",
            {'pdf_file': pdf_file},
            format='multipart'
        )
        self.assertEqual(upload_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('closed', upload_res.data['detail'].lower())
