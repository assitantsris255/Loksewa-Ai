"""
Individual Exam Creation System - Objective + Subjective Model Exams.

Verifies the canonical Examination/ExaminationQuestion/ExaminationAttempt
architecture (no separate ObjectiveExam/SubjectiveExam models) correctly
supports subjective exams end-to-end: creation, question assignment via the
real Question model, student attempt with descriptive answers, and the new
teacher evaluation queue - alongside the pre-existing objective (MCQ) flow,
to prove the two share one architecture without interfering with each other.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from django.test import override_settings
from tempfile import TemporaryDirectory

from exams.models import (
    ExamCategory, Exam, Paper, Subject, Chapter, Topic, Question,
    Examination, ExaminationQuestion, ExaminationAttempt, ExaminationRequest, StudentAnswer,
)

User = get_user_model()


class SubjectiveExaminationTestBase(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin1', password='pw', role='admin', is_staff=True)
        self.teacher = User.objects.create_user(username='teach1', password='pw', role='teacher')
        self.teacher2 = User.objects.create_user(username='teach2', password='pw', role='teacher')
        self.student = User.objects.create_user(username='stu1', password='pw', role='student')

        self.category = ExamCategory.objects.create(name='Loksewa')
        self.exam_level = Exam.objects.create(name='Section Officer', category=self.category)
        self.paper = Paper.objects.create(exam=self.exam_level, name='General Knowledge')
        self.subject = Subject.objects.create(paper=self.paper, name='Civil Engineering')
        self.chapter = Chapter.objects.create(subject=self.subject, title='Structures')
        self.topic = Topic.objects.create(chapter=self.chapter, name='Bending Moment')

        self.mcq_question = Question.objects.create(
            topic=self.topic, question_type='mcq', text='2 + 2 = ?',
            option_a='3', option_b='4', option_c='5', option_d='6',
            correct_option='B', marks=2, status='approved',
        )
        self.subjective_question = Question.objects.create(
            topic=self.topic, question_type='subjective',
            text='Explain the concept of bending moment.',
            model_answer='A reference answer for evaluators...',
            marks=10, status='approved',
        )


class CanonicalExaminationCreationTests(SubjectiveExaminationTestBase):
    """Section 2-6, 15: one Examination model for both modes, questions
    referenced (not copied) via ExaminationQuestion."""

    def test_create_objective_model_exam(self):
        self.client.force_authenticate(user=self.teacher)
        resp = self.client.post('/api/teacher/mock-exams/', {
            'title': 'PSC 5th Level Civil Engineering - Model Exam 01',
            'exam_type': 'mock',
            'objective_category': 'model',
            'category': self.category.id,
            'exam': self.exam_level.id,
            'time_limit': 60,
            'total_marks': 100,
            'passing_marks': 40,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        exam = Examination.objects.get(pk=resp.data['id'])
        self.assertEqual(exam.exam_type, 'mock')
        self.assertEqual(exam.objective_category, 'model')

    def test_create_subjective_model_exam(self):
        self.client.force_authenticate(user=self.teacher)
        resp = self.client.post('/api/teacher/mock-exams/', {
            'title': 'PSC 5th Level Civil Engineering - Subjective Model Exam 01',
            'exam_type': 'subjective',
            'category': self.category.id,
            'exam': self.exam_level.id,
            'time_limit': 120,
            'total_marks': 100,
            'passing_marks': 40,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        exam = Examination.objects.get(pk=resp.data['id'])
        self.assertEqual(exam.exam_type, 'subjective')
        # No separate SubjectiveExam/ObjectiveExam table exists - both modes
        # are rows in the same Examination table.
        self.assertEqual(Examination.objects.filter(pk=exam.pk).count(), 1)


class SubjectiveLiveExamGenerationTests(SubjectiveExaminationTestBase):
    url = '/api/admin/exams/generate-subjective-live/'
    generation_key = 'a7d1dd0f-31be-4f5b-9a38-8a8c1c8137cc'

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

    def payload(self, **overrides):
        data = {
            'generation_key': self.generation_key,
            'exam': self.exam_level.id,
            'title': 'Section Officer Subjective Live Exam',
            'question_count': 1,
            'time_limit': 90,
            'question_type': 'subjective',
        }
        data.update(overrides)
        return data

    def test_generation_uses_approved_bank_and_stores_a_draft_pdf_idempotently(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(created.status_code, 201, created.data)
        examination = Examination.objects.get(pk=created.data['id'])
        self.assertEqual(examination.exam_type, 'subjective')
        self.assertEqual(examination.status, 'draft')
        self.assertEqual(examination.total_questions, 1)
        self.assertEqual(examination.total_marks, 10)
        self.assertEqual(
            list(examination.examination_questions.values_list('question_id', flat=True)),
            [self.subjective_question.id],
        )
        self.assertTrue(examination.question_paper_pdf)
        with examination.question_paper_pdf.open('rb') as paper:
            self.assertTrue(paper.read().startswith(b'%PDF-'))

        repeated = self.client.post(self.url, self.payload(), format='json')
        self.assertEqual(repeated.status_code, 200)
        self.assertTrue(repeated.data['reused'])
        self.assertEqual(repeated.data['id'], examination.id)
        self.assertEqual(Examination.objects.count(), 1)

    def test_regeneration_updates_the_existing_draft_and_changes_its_question_set(self):
        self.client.force_authenticate(self.admin)
        first = self.client.post(self.url, self.payload(), format='json')
        extra_question = Question.objects.create(
            topic=self.topic, question_type='long_answer', status='approved',
            text='Describe the bending moment diagram.', model_answer='Reference.', marks=15,
        )

        regenerated = self.client.post(
            self.url, self.payload(regenerate=True), format='json'
        )

        self.assertEqual(regenerated.status_code, 200, regenerated.data)
        self.assertEqual(regenerated.data['id'], first.data['id'])
        examination = Examination.objects.get(pk=first.data['id'])
        self.assertEqual(examination.examination_questions.count(), 1)
        self.assertEqual(examination.examination_questions.get().question_id, extra_question.id)
        self.assertTrue(examination.question_paper_pdf)

    def test_insufficient_approved_pool_does_not_create_an_examination(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(self.url, self.payload(question_count=2), format='json')

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Examination.objects.count(), 0)

    def test_student_cannot_use_the_subjective_generator(self):
        self.client.force_authenticate(self.student)

        response = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Examination.objects.count(), 0)

    def test_generated_subjective_request_is_approved_only_after_publishing(self):
        exam_request = ExaminationRequest.objects.create(
            student=self.student,
            academic_exam=self.exam_level,
            subject=self.subject,
            request_type='subjective_live',
        )
        self.client.force_authenticate(self.admin)

        generated = self.client.post(
            self.url,
            self.payload(request_id=exam_request.id, subject=self.subject.id),
            format='json',
        )

        self.assertEqual(generated.status_code, 201, generated.data)
        exam_request.refresh_from_db()
        self.assertEqual(exam_request.status, 'pending')
        self.assertEqual(exam_request.examination_id, generated.data['id'])
        retried = self.client.post(
            self.url,
            self.payload(request_id=exam_request.id, generation_key='4bd9440c-bf72-4f0f-8e9b-98d813cd5f05'),
            format='json',
        )
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.data['id'], generated.data['id'])
        premature_approval = self.client.post(f'/api/admin/exam-requests/{exam_request.id}/approve/')
        self.assertEqual(premature_approval.status_code, 409)

        published = self.client.post(f'/api/admin/exams/{generated.data["id"]}/publish/')

        self.assertEqual(published.status_code, 200, published.data)
        exam_request.refresh_from_db()
        self.assertEqual(exam_request.status, 'approved')
        self.assertEqual(exam_request.reviewed_by_id, self.admin.id)

    def test_manual_subjective_exam_creation_links_the_pending_request(self):
        exam_request = ExaminationRequest.objects.create(
            student=self.student,
            academic_exam=self.exam_level,
            subject=self.subject,
            request_type='subjective_live',
        )
        self.client.force_authenticate(self.admin)

        created = self.client.post('/api/admin/exams/', {
            'request_id': exam_request.id,
            'title': 'Manually Prepared Subjective Exam',
            'exam_type': 'subjective',
            'category': self.category.id,
            'exam': self.exam_level.id,
            'subject': self.subject.id,
            'time_limit': 90,
            'total_marks': 10,
        }, format='json')

        self.assertEqual(created.status_code, 201, created.data)
        exam_request.refresh_from_db()
        self.assertEqual(exam_request.examination_id, created.data['id'])
        self.assertEqual(exam_request.status, 'pending')

    def test_add_questions_references_canonical_question_not_a_copy(self):
        self.client.force_authenticate(user=self.teacher)
        exam = Examination.objects.create(
            title='Subjective Exam', exam_type='subjective', category=self.category,
            exam=self.exam_level, created_by=self.teacher, status='draft',
        )
        resp = self.client.post(f'/api/teacher/mock-exams/{exam.id}/questions/', {
            'question_ids': [self.subjective_question.id],
            'marks': 10,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(Question.objects.count(), 2)  # no copy was made
        eq = ExaminationQuestion.objects.get(examination=exam)
        self.assertEqual(eq.question_id, self.subjective_question.id)

    def test_mcq_options_not_required_for_subjective_question_add(self):
        """A subjective question has no option_a-d - adding it to an exam
        must not require or validate MCQ fields."""
        self.client.force_authenticate(user=self.teacher)
        exam = Examination.objects.create(
            title='Subjective Exam', exam_type='subjective', category=self.category,
            exam=self.exam_level, created_by=self.teacher, status='draft',
        )
        self.assertEqual(self.subjective_question.option_a, None)
        resp = self.client.post(f'/api/teacher/mock-exams/{exam.id}/questions/', {
            'question_ids': [self.subjective_question.id],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)


class ExaminationIndependenceTests(SubjectiveExaminationTestBase):
    """Section 9: editing one exam must never affect another."""

    def test_editing_exam_a_does_not_affect_exam_b(self):
        self.client.force_authenticate(user=self.teacher)
        exam_a = Examination.objects.create(
            title='Exam A', exam_type='subjective', category=self.category,
            exam=self.exam_level, created_by=self.teacher, status='draft', total_marks=50,
        )
        exam_b = Examination.objects.create(
            title='Exam B', exam_type='mock', category=self.category,
            exam=self.exam_level, created_by=self.teacher, status='draft', total_marks=75,
        )
        resp = self.client.patch(f'/api/teacher/mock-exams/{exam_a.id}/', {
            'title': 'Exam A - Renamed', 'total_marks': 999,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        exam_b.refresh_from_db()
        self.assertEqual(exam_b.title, 'Exam B')
        self.assertEqual(exam_b.total_marks, 75)


class TeacherPermissionTests(SubjectiveExaminationTestBase):
    """Section 14: backend-enforced, not just frontend."""

    def test_teacher_cannot_modify_another_teachers_exam(self):
        exam = Examination.objects.create(
            title='Teacher1 Exam', exam_type='subjective', category=self.category,
            exam=self.exam_level, created_by=self.teacher, status='draft',
        )
        self.client.force_authenticate(user=self.teacher2)
        resp = self.client.patch(f'/api/teacher/mock-exams/{exam.id}/', {'title': 'Hijacked'}, format='json')
        # get_queryset scopes to created_by=user, so a foreign exam 404s.
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        exam.refresh_from_db()
        self.assertEqual(exam.title, 'Teacher1 Exam')

    def test_student_cannot_create_exam(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.post('/api/teacher/mock-exams/', {
            'title': 'Should not work', 'exam_type': 'subjective',
            'category': self.category.id, 'exam': self.exam_level.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_access_draft_exam(self):
        exam = Examination.objects.create(
            title='Draft Exam', exam_type='subjective', category=self.category,
            exam=self.exam_level, created_by=self.teacher, status='draft',
        )
        self.client.force_authenticate(user=self.student)
        resp = self.client.get('/api/student/exams/')
        ids = [e['id'] for e in resp.data]
        self.assertNotIn(exam.id, ids)


class SubjectiveAttemptAndEvaluationTests(SubjectiveExaminationTestBase):
    """Section 12-13: canonical ExaminationAttempt/StudentAnswer for
    subjective too - no ObjectiveAttempt/SubjectiveAttempt split."""

    def _published_subjective_exam(self):
        exam = Examination.objects.create(
            title='Subjective Model Exam 01', exam_type='subjective', category=self.category,
            exam=self.exam_level, status='published', time_limit=120,
            total_marks=10, passing_marks=4, created_by=self.teacher,
        )
        ExaminationQuestion.objects.create(examination=exam, question=self.subjective_question, order=1, marks=10)
        exam.total_questions = 1
        exam.save(update_fields=['total_questions'])
        return exam

    def test_student_sees_subjective_exam_in_listing(self):
        exam = self._published_subjective_exam()
        self.client.force_authenticate(user=self.student)
        resp = self.client.get('/api/student/exams/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        matching = [e for e in resp.data if e['id'] == exam.id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]['exam_type'], 'subjective')

    def test_full_subjective_attempt_and_evaluation_flow(self):
        exam = self._published_subjective_exam()
        self.client.force_authenticate(user=self.student)

        start_resp = self.client.post(f'/api/student/exams/{exam.id}/start/')
        self.assertEqual(start_resp.status_code, status.HTTP_201_CREATED, start_resp.data)
        attempt_id = start_resp.data['id']

        answer_resp = self.client.post(f'/api/student/exam-attempts/{attempt_id}/answer/', {
            'question': self.subjective_question.id,
            'answer_text': 'Bending moment is the reaction induced in a structural element...',
        }, format='json')
        self.assertEqual(answer_resp.status_code, status.HTTP_200_OK)

        submit_resp = self.client.post(f'/api/student/exam-attempts/{attempt_id}/submit/')
        self.assertEqual(submit_resp.status_code, status.HTTP_200_OK)

        attempt = ExaminationAttempt.objects.get(pk=attempt_id)
        self.assertEqual(attempt.status, 'submitted')
        self.assertEqual(attempt.score, 0)  # not yet graded

        result_resp = self.client.get(f'/api/student/exam-attempts/{attempt_id}/result/')
        self.assertEqual(result_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(result_resp.data['needs_evaluation'])

        # Teacher grades it.
        self.client.force_authenticate(user=self.teacher)
        queue_resp = self.client.get('/api/teacher/examination-attempts/?status=pending')
        self.assertEqual(queue_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(queue_resp.data), 1)
        self.assertEqual(queue_resp.data[0]['id'], attempt_id)

        answer = StudentAnswer.objects.get(attempt_id=attempt_id, question=self.subjective_question)
        eval_resp = self.client.post(f'/api/teacher/examination-attempts/{attempt_id}/evaluate/', {
            'answers': [{'answer_id': answer.id, 'marks_awarded': 8}],
        }, format='json')
        self.assertEqual(eval_resp.status_code, status.HTTP_200_OK, eval_resp.data)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'evaluated')
        self.assertEqual(attempt.score, 8)
        self.assertEqual(attempt.percentage, 80.0)
        self.assertTrue(attempt.passed)

        # Now gone from the pending queue.
        queue_resp = self.client.get('/api/teacher/examination-attempts/?status=pending')
        self.assertEqual(len(queue_resp.data), 0)

        # Student now sees a final result, not "pending".
        self.client.force_authenticate(user=self.student)
        result_resp = self.client.get(f'/api/student/exam-attempts/{attempt_id}/result/')
        self.assertFalse(result_resp.data['needs_evaluation'])
        self.assertEqual(result_resp.data['score'], 8)

    def test_cannot_evaluate_objective_question_via_evaluation_endpoint(self):
        """MCQ answers are auto-graded - the evaluate action must refuse to
        let a human override them through this endpoint."""
        exam = Examination.objects.create(
            title='Mixed Exam', exam_type='subjective', category=self.category,
            exam=self.exam_level, status='published', total_marks=12,
            created_by=self.teacher,
        )
        ExaminationQuestion.objects.create(examination=exam, question=self.mcq_question, order=1, marks=2)
        ExaminationQuestion.objects.create(examination=exam, question=self.subjective_question, order=2, marks=10)

        attempt = ExaminationAttempt.objects.create(examination=exam, student=self.student, status='submitted')
        mcq_answer = StudentAnswer.objects.create(attempt=attempt, question=self.mcq_question, selected_option='B', is_correct=True, marks_awarded=2)

        self.client.force_authenticate(user=self.teacher)
        resp = self.client.post(f'/api/teacher/examination-attempts/{attempt.id}/evaluate/', {
            'answers': [{'answer_id': mcq_answer.id, 'marks_awarded': 0}],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_evaluate_rejects_marks_above_question_max(self):
        exam = self._published_subjective_exam()
        attempt = ExaminationAttempt.objects.create(examination=exam, student=self.student, status='submitted')
        answer = StudentAnswer.objects.create(attempt=attempt, question=self.subjective_question, answer_text='...')

        self.client.force_authenticate(user=self.teacher)
        resp = self.client.post(f'/api/teacher/examination-attempts/{attempt.id}/evaluate/', {
            'answers': [{'answer_id': answer.id, 'marks_awarded': 999}],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_cannot_evaluate_own_attempt(self):
        exam = self._published_subjective_exam()
        attempt = ExaminationAttempt.objects.create(examination=exam, student=self.student, status='submitted')
        answer = StudentAnswer.objects.create(attempt=attempt, question=self.subjective_question, answer_text='...')

        self.client.force_authenticate(user=self.student)
        resp = self.client.post(f'/api/teacher/examination-attempts/{attempt.id}/evaluate/', {
            'answers': [{'answer_id': answer.id, 'marks_awarded': 5}],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_objective_exam_still_autoscores_without_evaluation(self):
        """The pre-existing MCQ flow through the same canonical models must
        keep working unchanged."""
        exam = Examination.objects.create(
            title='Objective Model Exam 01', exam_type='mock', objective_category='model',
            category=self.category, exam=self.exam_level, status='published',
            total_marks=2, passing_marks=1, time_limit=30, created_by=self.teacher,
        )
        ExaminationQuestion.objects.create(examination=exam, question=self.mcq_question, order=1, marks=2)
        exam.total_questions = 1
        exam.save(update_fields=['total_questions'])

        self.client.force_authenticate(user=self.student)
        start_resp = self.client.post(f'/api/student/exams/{exam.id}/start/')
        attempt_id = start_resp.data['id']

        self.client.post(f'/api/student/exam-attempts/{attempt_id}/answer/', {
            'question': self.mcq_question.id, 'selected_option': 'B',
        }, format='json')
        self.client.post(f'/api/student/exam-attempts/{attempt_id}/submit/')

        attempt = ExaminationAttempt.objects.get(pk=attempt_id)
        self.assertEqual(attempt.status, 'submitted')
        self.assertEqual(attempt.score, 2)
        self.assertTrue(attempt.passed)

        result_resp = self.client.get(f'/api/student/exam-attempts/{attempt_id}/result/')
        self.assertFalse(result_resp.data['needs_evaluation'])
