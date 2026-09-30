"""Tests for the Admin Exam Builder question-selection workflow.

Covers the canonical path:
    Question (Master Bank) → QuestionSelectionService → Examination
                                  → ExaminationQuestion
"""
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import User
from exams.models import (
    Chapter, Exam, ExamCategory, Examination, ExaminationQuestion,
    Paper, Question, Subject, Topic,
)


class ExamBuilderTestBase(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='s1', password='pw', role='student')
        self.teacher = User.objects.create_user(username='t1', password='pw', role='teacher')
        self.admin = User.objects.create_user(
            username='a1', password='pw', role='admin', is_staff=True
        )
        # A role-admin without is_staff - ExaminationViewSet gates on this
        # app's role-based IsAdminUser (like every other admin module), not
        # Django's is_staff flag, so this account must be treated identically
        # to self.admin.
        self.role_only_admin = User.objects.create_user(
            username='a2', password='pw', role='admin'
        )

        self.category = ExamCategory.objects.create(name='Loksewa')
        self.exam = Exam.objects.create(category=self.category, name='Section Officer')
        self.paper = Paper.objects.create(exam=self.exam, name='Paper I')
        self.subject = Subject.objects.create(paper=self.paper, name='General Knowledge')
        self.chapter = Chapter.objects.create(subject=self.subject, title='Geography')
        self.topic = Topic.objects.create(chapter=self.chapter, name='Rivers')

        # A second branch, to prove academic targeting actually narrows things.
        self.other_exam = Exam.objects.create(category=self.category, name='Kharidar')
        self.other_paper = Paper.objects.create(exam=self.other_exam, name='Paper I')
        self.other_subject = Subject.objects.create(paper=self.other_paper, name='Other')
        self.other_chapter = Chapter.objects.create(subject=self.other_subject, title='Misc')
        self.other_topic = Topic.objects.create(chapter=self.other_chapter, name='Misc Topic')

        # Approved pool: 6 easy, 5 medium, 4 hard.
        self.approved = []
        for difficulty, n in (('easy', 6), ('medium', 5), ('hard', 4)):
            for i in range(n):
                self.approved.append(Question.objects.create(
                    topic=self.topic, text=f'{difficulty} Q{i}', question_type='mcq',
                    status='approved', difficulty=difficulty, marks=1,
                    option_a='A', option_b='B', option_c='C', option_d='D', correct_option='A',
                ))

        # Never-selectable: not approved.
        self.draft_question = Question.objects.create(
            topic=self.topic, text='Draft question', question_type='mcq',
            status='draft', difficulty='easy', marks=1,
        )
        # Approved, but on a different exam branch.
        self.off_scope = Question.objects.create(
            topic=self.other_topic, text='Off-scope question', question_type='mcq',
            status='approved', difficulty='easy', marks=1,
        )

        self.examination = Examination.objects.create(
            title='GK Mock Test', exam_type='mock', category=self.category,
            exam=self.exam, subject=self.subject, time_limit=60,
            total_marks=0, total_questions=0, created_by=self.admin,
        )
        self.url = f'/api/admin/exams/{self.examination.id}/'

    def as_admin(self):
        self.client.force_authenticate(user=self.admin)


class PermissionTests(ExamBuilderTestBase):
    def test_anonymous_cannot_list_examinations(self):
        self.assertEqual(self.client.get('/api/admin/exams/').status_code,
                         status.HTTP_401_UNAUTHORIZED)

    def test_student_cannot_create_examination(self):
        self.client.force_authenticate(user=self.student)
        res = self.client.post('/api/admin/exams/', {'title': 'X'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_cannot_access_admin_exam_management(self):
        self.client.force_authenticate(user=self.teacher)
        self.assertEqual(self.client.get('/api/admin/exams/').status_code,
                         status.HTTP_403_FORBIDDEN)

    def test_student_cannot_add_questions(self):
        self.client.force_authenticate(user=self.student)
        res = self.client.post(f'{self.url}add-questions/',
                               {'question_ids': [self.approved[0].id]}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_role_admin_without_is_staff_can_access_exam_management(self):
        """ExaminationViewSet gates on role (admin/super-admin), matching
        every other admin module - an admin account only ever missing
        Django's separate is_staff flag must not be locked out of exam
        creation, the same as it isn't locked out of anything else."""
        self.client.force_authenticate(user=self.role_only_admin)
        self.assertEqual(self.client.get('/api/admin/exams/').status_code,
                         status.HTTP_200_OK)

    def test_admin_can_create_examination(self):
        self.as_admin()
        res = self.client.post('/api/admin/exams/', {
            'title': 'New Mock', 'exam_type': 'mock',
            'category': self.category.id, 'exam': self.exam.id,
            'time_limit': 60, 'total_marks': 10,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Examination.objects.filter(title='New Mock').exists())


class AvailableQuestionTests(ExamBuilderTestBase):
    def test_admin_retrieves_only_approved_questions(self):
        self.as_admin()
        res = self.client.get(f'{self.url}available-questions/?page_size=100')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        texts = [q['text'] for q in res.data['results']]
        self.assertNotIn('Draft question', texts)
        self.assertTrue(all(q['status'] == 'approved' for q in res.data['results']))

    def test_academic_targeting_scopes_the_bank(self):
        """The exam targets self.exam, so the other branch must not appear."""
        self.as_admin()
        res = self.client.get(f'{self.url}available-questions/?page_size=100')
        texts = [q['text'] for q in res.data['results']]
        self.assertNotIn('Off-scope question', texts)

    def test_pagination(self):
        self.as_admin()
        first = self.client.get(f'{self.url}available-questions/?page_size=5&page=1')
        self.assertEqual(len(first.data['results']), 5)
        self.assertEqual(first.data['count'], 15)
        self.assertTrue(first.data['has_next'])

        second = self.client.get(f'{self.url}available-questions/?page_size=5&page=2')
        first_ids = {q['id'] for q in first.data['results']}
        second_ids = {q['id'] for q in second.data['results']}
        self.assertEqual(first_ids & second_ids, set())

    def test_search_filters_server_side(self):
        self.as_admin()
        res = self.client.get(f'{self.url}available-questions/?search=hard')
        self.assertEqual(res.data['count'], 4)

    def test_difficulty_filter(self):
        self.as_admin()
        res = self.client.get(f'{self.url}available-questions/?difficulty=medium&page_size=100')
        self.assertEqual(res.data['count'], 5)

    def test_availability_summary_counts(self):
        self.as_admin()
        res = self.client.get(f'{self.url}question-availability/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['total_available'], 15)
        self.assertEqual(res.data['by_difficulty'],
                         {'easy': 6, 'medium': 5, 'hard': 4})
        self.assertEqual(res.data['selected'], 0)

    def test_assigned_questions_leave_the_available_pool(self):
        self.as_admin()
        self.client.post(f'{self.url}add-questions/',
                         {'question_ids': [self.approved[0].id]}, format='json')
        res = self.client.get(f'{self.url}question-availability/')
        self.assertEqual(res.data['total_available'], 14)
        self.assertEqual(res.data['selected'], 1)


class ManualSelectionTests(ExamBuilderTestBase):
    def test_manual_assignment_works(self):
        self.as_admin()
        ids = [q.id for q in self.approved[:3]]
        res = self.client.post(f'{self.url}add-questions/',
                               {'question_ids': ids}, format='json')
        self.assertEqual(res.data['added_count'], 3)
        self.assertEqual(res.data['total_questions'], 3)
        self.assertEqual(ExaminationQuestion.objects.filter(
            examination=self.examination).count(), 3)

    def test_duplicate_assignment_is_prevented(self):
        self.as_admin()
        qid = self.approved[0].id
        self.client.post(f'{self.url}add-questions/', {'question_ids': [qid]}, format='json')
        res = self.client.post(f'{self.url}add-questions/', {'question_ids': [qid]}, format='json')
        self.assertEqual(res.data['added_count'], 0)
        self.assertEqual(res.data['skipped_duplicates'], 1)
        self.assertEqual(ExaminationQuestion.objects.filter(
            examination=self.examination, question_id=qid).count(), 1)

    def test_unapproved_question_cannot_be_assigned(self):
        self.as_admin()
        res = self.client.post(f'{self.url}add-questions/',
                               {'question_ids': [self.draft_question.id]}, format='json')
        self.assertEqual(res.data['added_count'], 0)
        self.assertIn(self.draft_question.id, res.data['not_approved_or_missing'])

    def test_removal_detaches_but_keeps_the_question(self):
        self.as_admin()
        qid = self.approved[0].id
        self.client.post(f'{self.url}add-questions/', {'question_ids': [qid]}, format='json')
        res = self.client.post(f'{self.url}remove-questions/',
                               {'question_ids': [qid]}, format='json')
        self.assertEqual(res.data['removed_count'], 1)
        self.assertEqual(res.data['total_questions'], 0)
        # The question itself survives in the Master Question Bank.
        self.assertTrue(Question.objects.filter(id=qid).exists())

    def test_reorder_persists(self):
        self.as_admin()
        ids = [q.id for q in self.approved[:3]]
        self.client.post(f'{self.url}add-questions/', {'question_ids': ids}, format='json')
        res = self.client.post(f'{self.url}reorder-questions/', {'order_data': [
            {'question_id': ids[0], 'order': 30},
            {'question_id': ids[1], 'order': 10},
            {'question_id': ids[2], 'order': 20},
        ]}, format='json')
        self.assertEqual(res.data['reordered_count'], 3)
        ordered = list(self.examination.examination_questions
                       .order_by('order').values_list('question_id', flat=True))
        self.assertEqual(ordered, [ids[1], ids[2], ids[0]])

    def test_empty_payload_is_rejected(self):
        self.as_admin()
        res = self.client.post(f'{self.url}add-questions/', {'question_ids': []}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class RandomSelectionTests(ExamBuilderTestBase):
    def test_returns_requested_number_when_sufficient(self):
        self.as_admin()
        res = self.client.post(f'{self.url}generate-questions/',
                               {'count': 10}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data['satisfied'])
        self.assertEqual(res.data['selected'], 10)
        self.assertEqual(res.data['total_questions'], 10)

    def test_respects_difficulty_distribution(self):
        self.as_admin()
        res = self.client.post(f'{self.url}generate-questions/', {
            'difficulty_distribution': {'easy': 3, 'medium': 2, 'hard': 1},
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        rows = self.examination.examination_questions.select_related('question')
        counts = {}
        for row in rows:
            counts[row.question.difficulty] = counts.get(row.question.difficulty, 0) + 1
        self.assertEqual(counts, {'easy': 3, 'medium': 2, 'hard': 1})

    def test_never_selects_unapproved_questions(self):
        self.as_admin()
        self.client.post(f'{self.url}generate-questions/', {'count': 15}, format='json')
        assigned = self.examination.examination_questions.select_related('question')
        self.assertTrue(all(r.question.status == 'approved' for r in assigned))
        self.assertNotIn(self.draft_question.id,
                         [r.question_id for r in assigned])

    def test_respects_academic_targeting(self):
        self.as_admin()
        self.client.post(f'{self.url}generate-questions/', {'count': 15}, format='json')
        assigned_ids = list(self.examination.examination_questions
                            .values_list('question_id', flat=True))
        self.assertNotIn(self.off_scope.id, assigned_ids)

    def test_no_duplicates_within_a_generation(self):
        self.as_admin()
        self.client.post(f'{self.url}generate-questions/', {'count': 15}, format='json')
        ids = list(self.examination.examination_questions
                   .values_list('question_id', flat=True))
        self.assertEqual(len(ids), len(set(ids)))

    def test_insufficient_availability_returns_warning_and_writes_nothing(self):
        self.as_admin()
        res = self.client.post(f'{self.url}generate-questions/',
                               {'count': 50}, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(res.data['satisfied'])
        self.assertTrue(res.data['warnings'])
        # Nothing was silently committed.
        self.assertEqual(self.examination.examination_questions.count(), 0)

    def test_insufficient_difficulty_names_the_shortfall(self):
        self.as_admin()
        res = self.client.post(f'{self.url}generate-questions/', {
            'difficulty_distribution': {'easy': 6, 'medium': 5, 'hard': 10},
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(any('hard' in w for w in res.data['warnings']))

    def test_preview_writes_nothing(self):
        self.as_admin()
        res = self.client.post(f'{self.url}generate-questions/',
                               {'count': 5, 'preview': True}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['preview'])
        self.assertEqual(len(res.data['questions']), 5)
        self.assertEqual(self.examination.examination_questions.count(), 0)

    def test_regeneration_replaces_the_previous_selection(self):
        self.as_admin()
        self.client.post(f'{self.url}generate-questions/', {'count': 5}, format='json')
        first = set(self.examination.examination_questions.values_list('question_id', flat=True))

        res = self.client.post(f'{self.url}generate-questions/',
                               {'count': 5, 'replace': True}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        after = list(self.examination.examination_questions.values_list('question_id', flat=True))
        self.assertEqual(len(after), 5)
        self.assertEqual(len(after), len(set(after)))
        self.assertEqual(len(first), 5)

    def test_generation_without_replace_appends_without_duplicates(self):
        self.as_admin()
        self.client.post(f'{self.url}generate-questions/', {'count': 5}, format='json')
        self.client.post(f'{self.url}generate-questions/', {'count': 5}, format='json')
        ids = list(self.examination.examination_questions.values_list('question_id', flat=True))
        self.assertEqual(len(ids), 10)
        self.assertEqual(len(ids), len(set(ids)))

    def test_requires_a_count_or_distribution(self):
        self.as_admin()
        res = self.client.post(f'{self.url}generate-questions/', {}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class PublishTests(ExamBuilderTestBase):
    def test_publish_rejects_an_exam_with_no_questions(self):
        self.as_admin()
        res = self.client.post(f'{self.url}publish/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Add at least one question before publishing.', res.data['details'])

    def test_publish_succeeds_and_sets_a_valid_status(self):
        self.as_admin()
        self.client.post(f'{self.url}generate-questions/', {'count': 5}, format='json')
        res = self.client.post(f'{self.url}publish/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.examination.refresh_from_db()
        self.assertEqual(self.examination.status, 'published')
        valid = dict(Examination.STATUS_CHOICES)
        self.assertIn(self.examination.status, valid)

    def test_publish_rejects_passing_marks_above_total(self):
        self.as_admin()
        self.client.post(f'{self.url}generate-questions/', {'count': 5}, format='json')
        self.examination.refresh_from_db()
        self.examination.passing_marks = self.examination.total_marks + 10
        self.examination.save()
        res = self.client.post(f'{self.url}publish/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_preview_uses_assigned_questions_and_hides_answers(self):
        self.as_admin()
        self.client.post(f'{self.url}generate-questions/', {'count': 3}, format='json')
        res = self.client.get(f'{self.url}preview/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['total_questions'], 3)
        self.assertNotIn('correct_option', res.data['questions'][0])


class TopicwiseTestManagementTests(ExamBuilderTestBase):
    def setUp(self):
        super().setUp()
        from courses.models import Course
        self.course = Course.objects.create(
            title='Section Officer', slug='section-officer-topic-test',
            status='published', exam=self.exam,
        )

    def test_topicwise_examination_persists_course_and_topic(self):
        self.as_admin()
        response = self.client.patch(self.url, {
            'exam_type': 'subject', 'course': self.course.id, 'topic': self.topic.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['topic'], self.topic.id)
        self.assertEqual(response.data['topic_name'], self.topic.name)
        self.examination.refresh_from_db()
        self.assertEqual(self.examination.course_id, self.course.id)
        self.assertEqual(self.examination.topic_id, self.topic.id)

    def test_topicwise_assignment_rejects_questions_from_another_topic(self):
        self.as_admin()
        self.client.patch(self.url, {
            'exam_type': 'subject', 'course': self.course.id, 'topic': self.topic.id,
        }, format='json')

        response = self.client.post(f'{self.url}add-questions/', {
            'question_ids': [self.approved[0].id, self.off_scope.id],
        }, format='json')

        self.assertEqual(response.data['added_count'], 1)
        self.assertIn(self.off_scope.id, response.data['not_approved_or_missing'])
        self.assertEqual(list(self.examination.examination_questions.values_list('question_id', flat=True)), [self.approved[0].id])

    def test_topicwise_test_with_approved_topic_questions_can_publish(self):
        self.as_admin()
        self.client.patch(self.url, {
            'exam_type': 'subject', 'course': self.course.id, 'topic': self.topic.id,
        }, format='json')
        self.client.post(f'{self.url}add-questions/', {
            'question_ids': [self.approved[0].id],
        }, format='json')

        response = self.client.post(f'{self.url}publish/')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'published')


class AnalyticsResultsTests(ExamBuilderTestBase):
    def test_analytics_endpoint_still_works(self):
        self.as_admin()
        res = self.client.get(f'{self.url}analytics/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_results_endpoint_still_works(self):
        self.as_admin()
        res = self.client.get(f'{self.url}results/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
