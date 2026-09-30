import io
from PIL import Image
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from rest_framework import status

from exams.models import (
    ExamCategory, Exam, Examination, ExaminationAttempt, ExaminationRequest,
    SubjectiveSubmission, SubjectiveSubmissionPage, SubjectiveQuestionScore
)
from courses.models import Course, Enrollment

User = get_user_model()


def create_dummy_pdf(num_pages=1):
    """Generates a minimal valid in-memory PDF using Pillow."""
    images = [Image.new('RGB', (200, 200), color='white') for _ in range(num_pages)]
    buf = io.BytesIO()
    images[0].save(buf, format='PDF', save_all=True, append_images=images[1:])
    buf.seek(0)
    return buf.getvalue()


def create_dummy_image(color='blue'):
    """Generates a small valid in-memory JPEG image."""
    img = Image.new('RGB', (150, 150), color=color)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    return buf.getvalue()


class SubjectiveExamWorkflowTests(APITestCase):
    def setUp(self):
        # 1. Users
        self.admin = User.objects.create_superuser(
            username='admin_sub',
            email='admin_sub@loksewa.ai',
            password='Password123!',
            is_staff=True,
            role='admin'
        )

        self.student = User.objects.create_user(
            username='student_sub',
            email='student_sub@loksewa.ai',
            password='Password123!',
            role='student'
        )

        self.other_student = User.objects.create_user(
            username='other_sub',
            email='other_sub@loksewa.ai',
            password='Password123!',
            role='student'
        )

        # 2. Category, Exam and Course
        self.category = ExamCategory.objects.create(name='PSC Nepal', order=1)
        self.exam = Exam.objects.create(category=self.category, name='Section Officer', is_active=True)
        self.course = Course.objects.create(title='Officer Written Batch', exam=self.exam, status='published')

        # Enroll student in course
        Enrollment.objects.create(student=self.student, course=self.course, status='active')

        # 3. Subjective Examination
        self.subjective_exam = Examination.objects.create(
            title='Section Officer Paper II - Subjective',
            exam_type='subjective',
            category=self.category,
            exam=self.exam,
            time_limit=90, # 90 minutes writing time
            total_marks=100,
            passing_marks=40,
            upload_deadline_minutes=15, # 15 minutes upload window
            answer_upload_enabled=True,
            allowed_file_types='pdf,image',
            status='published',
            created_by=self.admin,
        )

        # Approved ExaminationRequest for subjective attempt
        ExaminationRequest.objects.create(
            student=self.student,
            examination=self.subjective_exam,
            status='approved',
        )

    def test_01_admin_upload_and_stream_question_paper_pdf(self):
        """Admin can upload question paper PDF and stream it."""
        self.client.force_authenticate(user=self.admin)

        pdf_content = create_dummy_pdf(num_pages=2)
        uploaded_file = SimpleUploadedFile("sample_qp.pdf", pdf_content, content_type="application/pdf")

        # Upload
        url = f"/api/admin/exams/{self.subjective_exam.id}/question-paper/"
        response = self.client.post(url, {'pdf_file': uploaded_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['page_count'], 2)

        # Verify model updated
        self.subjective_exam.refresh_from_db()
        self.assertTrue(bool(self.subjective_exam.question_paper_pdf))
        self.assertEqual(self.subjective_exam.question_paper_page_count, 2)
        self.assertGreater(self.subjective_exam.question_paper_file_size, 0)

        # Stream via admin GET
        stream_res = self.client.get(url)
        self.assertEqual(stream_res.status_code, status.HTTP_200_OK)
        self.assertEqual(stream_res['Content-Type'], 'application/pdf')

    def test_02_student_authorized_question_paper_streaming(self):
        """Enrolled student can stream question paper, unauthorized user is blocked."""
        # Attach question paper
        pdf_content = create_dummy_pdf(num_pages=1)
        self.subjective_exam.question_paper_pdf.save("officer_qp.pdf", io.BytesIO(pdf_content))
        self.subjective_exam.question_paper_page_count = 1
        self.subjective_exam.save()

        student_url = f"/api/student/exams/{self.subjective_exam.id}/question-paper/"

        # 1. Unauthenticated gets 401
        self.client.logout()
        res_anon = self.client.get(student_url)
        self.assertEqual(res_anon.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Unenrolled student gets 403 or 404 (scoped out)
        self.client.force_authenticate(user=self.other_student)
        res_unenrolled = self.client.get(student_url)
        self.assertIn(res_unenrolled.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        # 3. Enrolled student gets 200 PDF stream
        self.client.force_authenticate(user=self.student)
        res_enrolled = self.client.get(student_url)
        self.assertEqual(res_enrolled.status_code, status.HTTP_200_OK)
        self.assertEqual(res_enrolled['Content-Type'], 'application/pdf')

    def test_03_dual_timer_calculation_and_upload_window(self):
        """Attempt has both writing expiration and upload deadline calculation."""
        self.client.force_authenticate(user=self.student)

        # Start attempt
        start_res = self.client.post(f"/api/student/exams/{self.subjective_exam.id}/start/")
        self.assertEqual(start_res.status_code, status.HTTP_201_CREATED)
        attempt_id = start_res.data['id']

        # Check state endpoint
        state_url = f"/api/student/exam-attempts/{attempt_id}/state/"
        state_res = self.client.get(state_url)
        self.assertEqual(state_res.status_code, status.HTTP_200_OK)
        data = state_res.data

        self.assertTrue(data['is_subjective'])
        self.assertIsNotNone(data['exam_expires_at'])
        self.assertIsNotNone(data['upload_expires_at'])
        self.assertGreater(data['time_remaining_seconds'], 0)
        self.assertGreater(data['upload_time_remaining_seconds'], data['time_remaining_seconds'])
        self.assertTrue(data['can_upload'])

    def test_04_handwritten_image_upload_and_pdf_compilation(self):
        """Student can upload handwritten images which are automatically merged into an A4 PDF."""
        self.client.force_authenticate(user=self.student)

        # Start attempt
        attempt = ExaminationAttempt.objects.create(
            examination=self.subjective_exam,
            student=self.student,
            status='in-progress',
            started_at=timezone.now(),
        )

        img1_bytes = create_dummy_image(color='red')
        img2_bytes = create_dummy_image(color='blue')

        img1 = SimpleUploadedFile("page1.jpg", img1_bytes, content_type="image/jpeg")
        img2 = SimpleUploadedFile("page2.jpg", img2_bytes, content_type="image/jpeg")

        upload_url = f"/api/student/exam-attempts/{attempt.id}/answer-sheet/"
        upload_res = self.client.post(upload_url, {'images': [img1, img2]}, format='multipart')

        self.assertEqual(upload_res.status_code, status.HTTP_200_OK)
        self.assertEqual(upload_res.data['page_count'], 2)
        self.assertGreater(upload_res.data['file_size_bytes'], 0)

        # Verify database models
        submission = SubjectiveSubmission.objects.get(attempt=attempt)
        self.assertEqual(submission.page_count, 2)
        self.assertTrue(bool(submission.answer_pdf))
        self.assertEqual(submission.pages.count(), 2)

        # Verify page sequence
        page1 = submission.pages.get(page_number=1)
        page2 = submission.pages.get(page_number=2)
        self.assertIsNotNone(page1.image_file)
        self.assertIsNotNone(page2.image_file)

        # Stream student's submitted answer sheet
        stream_res = self.client.get(upload_url)
        self.assertEqual(stream_res.status_code, status.HTTP_200_OK)
        self.assertEqual(stream_res['Content-Type'], 'application/pdf')

    def test_05_admin_ocr_and_editing(self):
        """Admin can run OCR handwriting transcription and verify/edit the text."""
        # Create submission with PDF
        attempt = ExaminationAttempt.objects.create(
            examination=self.subjective_exam,
            student=self.student,
            status='in-progress',
            started_at=timezone.now(),
        )
        submission = SubjectiveSubmission.objects.create(
            attempt=attempt,
            status='submitted',
            page_count=1,
            file_size_bytes=1024,
        )
        pdf_content = create_dummy_pdf(1)
        submission.answer_pdf.save("answers.pdf", io.BytesIO(pdf_content))
        submission.save()

        # Admin runs OCR
        self.client.force_authenticate(user=self.admin)
        ocr_url = f"/api/admin/subjective-submissions/{submission.id}/ocr/"
        ocr_res = self.client.post(ocr_url)
        self.assertEqual(ocr_res.status_code, status.HTTP_200_OK)

        submission.refresh_from_db()
        self.assertEqual(submission.ocr_status, 'completed')
        self.assertTrue(len(submission.raw_ocr_text) > 0)

        # Admin edits transcription
        edit_url = f"/api/admin/subjective-submissions/{submission.id}/update-transcription/"
        corrected = "१. नेपालको संविधान अनुसार संघ, प्रदेश र स्थानीय तहको अधिकार।"
        edit_res = self.client.post(edit_url, {'extracted_text': corrected})
        self.assertEqual(edit_res.status_code, status.HTTP_200_OK)

        submission.refresh_from_db()
        self.assertEqual(submission.extracted_text, corrected)

    def test_06_admin_evaluate_and_publish_results(self):
        """Admin can dynamically grade submission with question scores, verify calculated totals, and publish."""
        attempt = ExaminationAttempt.objects.create(
            examination=self.subjective_exam,
            student=self.student,
            status='in-progress',
            started_at=timezone.now(),
        )
        submission = SubjectiveSubmission.objects.create(
            attempt=attempt,
            status='submitted',
            page_count=2,
            file_size_bytes=2048,
        )

        self.client.force_authenticate(user=self.admin)

        # 1. Evaluate with 3 dynamic questions: 10 + 20 + 10 = 40 max marks, 8 + 15 + 7 = 30 obtained
        eval_url = f"/api/admin/subjective-submissions/{submission.id}/evaluate/"
        eval_payload = {
            'evaluator_feedback': 'Good attempt. Needs more diagrams.',
            'question_scores': [
                {'question_number': 1, 'marks_obtained': 8, 'max_marks': 10, 'feedback': 'Good explanation'},
                {'question_number': 2, 'marks_obtained': 15, 'max_marks': 20, 'feedback': 'Clear presentation'},
                {'question_number': 3, 'marks_obtained': 7, 'max_marks': 10, 'feedback': 'Brief answer'},
            ]
        }
        eval_res = self.client.post(eval_url, eval_payload, format='json')
        self.assertEqual(eval_res.status_code, status.HTTP_200_OK)

        submission.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(submission.status, 'evaluated')
        # Backend authoritative calculation: 8 + 15 + 7 = 30
        self.assertEqual(attempt.score, 30.0)
        # Total max = 10 + 20 + 10 = 40. Percentage = 30 / 40 * 100 = 75.0%
        self.assertEqual(attempt.percentage, 75.0)
        self.assertTrue(attempt.passed)
        self.assertEqual(submission.question_scores.count(), 3)
        self.assertFalse(submission.is_published)

        # 2. Publish
        pub_url = f"/api/admin/subjective-submissions/{submission.id}/publish/"
        pub_res = self.client.post(pub_url)
        self.assertEqual(pub_res.status_code, status.HTTP_200_OK)

        submission.refresh_from_db()
        attempt.refresh_from_db()
        self.assertTrue(submission.is_published)
        self.assertIsNotNone(submission.published_at)
        self.assertEqual(attempt.status, 'evaluated')

    def test_07_student_cannot_access_other_students_submission(self):
        """Cross-student isolation: student cannot access another student's answer sheet or submission."""
        attempt = ExaminationAttempt.objects.create(
            examination=self.subjective_exam,
            student=self.student,
            status='in-progress',
            started_at=timezone.now(),
        )
        submission = SubjectiveSubmission.objects.create(
            attempt=attempt,
            status='submitted',
            page_count=1,
            file_size_bytes=1024,
        )
        pdf_content = create_dummy_pdf(1)
        submission.answer_pdf.save("answers.pdf", io.BytesIO(pdf_content))
        submission.save()

        # Other student tries to fetch answer sheet
        self.client.force_authenticate(user=self.other_student)
        res = self.client.get(f"/api/student/exam-attempts/{attempt.id}/answer-sheet/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_08_validation_rejects_obtained_exceeding_max(self):
        """Backend validation strictly rejects obtained marks > maximum marks."""
        attempt = ExaminationAttempt.objects.create(
            examination=self.subjective_exam,
            student=self.student,
            status='submitted',
            started_at=timezone.now(),
        )
        submission = SubjectiveSubmission.objects.create(
            attempt=attempt,
            status='submitted',
        )

        self.client.force_authenticate(user=self.admin)
        eval_url = f"/api/admin/subjective-submissions/{submission.id}/evaluate/"
        invalid_payload = {
            'question_scores': [
                {'question_number': 1, 'marks_obtained': 12, 'max_marks': 10, 'feedback': 'Over-marked'},
            ]
        }
        res = self.client.post(eval_url, invalid_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot exceed", res.data.get('detail', ''))

    def test_09_validation_rejects_negative_or_zero_max(self):
        """Backend rejects negative obtained marks or max_marks <= 0."""
        attempt = ExaminationAttempt.objects.create(
            examination=self.subjective_exam,
            student=self.student,
            status='submitted',
            started_at=timezone.now(),
        )
        submission = SubjectiveSubmission.objects.create(
            attempt=attempt,
            status='submitted',
        )

        self.client.force_authenticate(user=self.admin)
        eval_url = f"/api/admin/subjective-submissions/{submission.id}/evaluate/"

        # Negative obtained
        res1 = self.client.post(eval_url, {'question_scores': [{'question_number': 1, 'marks_obtained': -2, 'max_marks': 10}]}, format='json')
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)

        # Zero max marks
        res2 = self.client.post(eval_url, {'question_scores': [{'question_number': 1, 'marks_obtained': 0, 'max_marks': 0}]}, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_10_unpublished_marks_hidden_from_student(self):
        """Student cannot access draft evaluation marks before result publication."""
        attempt = ExaminationAttempt.objects.create(
            examination=self.subjective_exam,
            student=self.student,
            status='submitted',
            score=35.0,
            percentage=70.0,
            started_at=timezone.now(),
        )
        submission = SubjectiveSubmission.objects.create(
            attempt=attempt,
            status='evaluated',
            is_published=False,
            evaluator_feedback='Private draft teacher notes'
        )
        SubjectiveQuestionScore.objects.create(
            submission=submission,
            question_number=1,
            marks_obtained=8,
            max_marks=10
        )

        self.client.force_authenticate(user=self.student)
        res = self.client.get(f"/api/student/exam-attempts/{attempt.id}/result/")
        # Should be gated with 403 Forbidden
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("being evaluated", res.data.get('detail', ''))

    def test_11_student_submission_creates_admin_notification_and_deduplicates(self):
        """When a student submits subjective exam, all admins receive a notification, deduplicated."""
        from core.models import Notification, AdminSettings
        AdminSettings.objects.all().delete()
        AdminSettings.objects.create(notifications_enabled=True, enable_in_app_notifications=True)

        attempt = ExaminationAttempt.objects.create(
            examination=self.subjective_exam,
            student=self.student,
            status='in-progress',
            started_at=timezone.now(),
        )
        submission = SubjectiveSubmission.objects.create(
            attempt=attempt,
            status='processing',
        )

        from core.notification_service import NotificationService
        # 1st call
        NotificationService.notify_admins_subjective_submission(submission)
        admin_notifs = Notification.objects.filter(related_id=f"subjective-submission:{submission.id}")
        self.assertTrue(admin_notifs.exists())
        self.assertEqual(admin_notifs.first().title, "New Subjective Exam Submission")
        count_first = admin_notifs.count()

        # 2nd call (duplicate protection / idempotent)
        NotificationService.notify_admins_subjective_submission(submission)
        count_second = Notification.objects.filter(related_id=f"subjective-submission:{submission.id}").count()
        self.assertEqual(count_first, count_second)

    def test_12_publishing_creates_student_notification(self):
        """When admin publishes subjective result, student receives a notification."""
        from core.models import Notification
        attempt = ExaminationAttempt.objects.create(
            examination=self.subjective_exam,
            student=self.student,
            status='submitted',
            score=30.0,
            percentage=75.0,
            passed=True,
            started_at=timezone.now(),
        )
        submission = SubjectiveSubmission.objects.create(
            attempt=attempt,
            status='evaluated',
            is_published=False,
        )
        SubjectiveQuestionScore.objects.create(
            submission=submission,
            question_number=1,
            marks_obtained=30,
            max_marks=40
        )

        self.client.force_authenticate(user=self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            pub_res = self.client.post(f"/api/admin/subjective-submissions/{submission.id}/publish/")
        self.assertEqual(pub_res.status_code, status.HTTP_200_OK)

        student_notifs = Notification.objects.filter(recipient=self.student, related_id=f"subjective-result:{attempt.id}")
        self.assertTrue(student_notifs.exists())
        self.assertIn("published", student_notifs.first().title.lower())

    def test_13_student_cannot_evaluate_or_modify_marks(self):
        """Students and unauthorized users are forbidden from accessing admin evaluation endpoints."""
        attempt = ExaminationAttempt.objects.create(
            examination=self.subjective_exam,
            student=self.student,
            status='submitted',
            started_at=timezone.now(),
        )
        submission = SubjectiveSubmission.objects.create(
            attempt=attempt,
            status='submitted',
        )

        self.client.force_authenticate(user=self.student)
        eval_url = f"/api/admin/subjective-submissions/{submission.id}/evaluate/"
        res = self.client.post(eval_url, {'question_scores': []}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

