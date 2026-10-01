from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from exams.models import ExamCategory, Exam, Paper, Subject, Chapter, Topic, Question

User = get_user_model()

class QuestionAcademicHierarchyTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin_test',
            email='admin_test@loksewaai.com',
            password='Password@123',
            role='super-admin'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

        # Setup Category 1
        self.cat1 = ExamCategory.objects.create(name='PSC Exams', order=1)
        # Setup Level 1 (Position)
        self.level1 = Exam.objects.create(name='5th Level', category=self.cat1, parent=None, order=1)
        # Setup Paper
        self.paper1 = Paper.objects.create(name='Paper I', exam=self.level1, order=1)
        # Setup Subject 1
        self.sub1 = Subject.objects.create(name='Building Construction', paper=self.paper1, order=1)
        # Setup Chapter 1
        self.chap1 = Chapter.objects.create(title='Foundation', subject=self.sub1, order=1)
        # Setup Topic 1
        self.top1 = Topic.objects.create(name='Shallow Foundation', chapter=self.chap1, order=1)

        # Setup second isolated tree for mismatch testing
        self.cat2 = ExamCategory.objects.create(name='Banking Exams', order=2)
        self.level2 = Exam.objects.create(name='Officer Level', category=self.cat2, parent=None, order=2)
        self.paper2 = Paper.objects.create(name='Banking Paper', exam=self.level2, order=2)
        self.sub2 = Subject.objects.create(name='Accountancy', paper=self.paper2, order=2)
        self.chap2 = Chapter.objects.create(title='Balance Sheet', subject=self.sub2, order=2)
        self.top2 = Topic.objects.create(name='Assets & Liabilities', chapter=self.chap2, order=2)

    def test_case_1_create_question_subject_only(self):
        """Case 1: Category + Level + Subject (Chapter=None, Topic=None) is valid and saves."""
        data = {
            'question_type': 'mcq',
            'status': 'draft',
            'difficulty': 'medium',
            'category': self.cat1.id,
            'position': self.level1.id,
            'subject': self.sub1.id,
            'chapter': None,
            'topic': None,
            'text': 'What is the standard slump for concrete in foundations?',
            'option_a': '10-25mm',
            'option_b': '50-100mm',
            'option_c': '150-200mm',
            'option_d': '250-300mm',
            'correct_option': 'B',
            'marks': 1,
            'negative_marks': 0.2,
            'expected_time_minutes': 1,
        }
        response = self.client.post('/api/admin/questions/', data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        q = Question.objects.get(id=response.data['id'])
        self.assertEqual(q.subject_id, self.sub1.id)
        self.assertIsNone(q.chapter)
        self.assertIsNone(q.topic)
        self.assertEqual(response.data['subject_name'], 'Building Construction')
        self.assertIsNone(response.data['chapter_name'])
        self.assertIsNone(response.data['topic_name'])

    def test_case_2_create_question_subject_and_chapter(self):
        """Case 2: Category + Level + Subject + Chapter (Topic=None) is valid and saves."""
        data = {
            'question_type': 'mcq',
            'status': 'draft',
            'difficulty': 'medium',
            'category': self.cat1.id,
            'position': self.level1.id,
            'subject': self.sub1.id,
            'chapter': self.chap1.id,
            'topic': None,
            'text': 'Which foundation is best suited for low bearing capacity soil?',
            'option_a': 'Isolated footing',
            'option_b': 'Combined footing',
            'option_c': 'Raft foundation',
            'option_d': 'Strap footing',
            'correct_option': 'C',
            'marks': 1,
            'negative_marks': 0.2,
            'expected_time_minutes': 1,
        }
        response = self.client.post('/api/admin/questions/', data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        q = Question.objects.get(id=response.data['id'])
        self.assertEqual(q.subject_id, self.sub1.id)
        self.assertEqual(q.chapter_id, self.chap1.id)
        self.assertIsNone(q.topic)
        self.assertEqual(response.data['subject_name'], 'Building Construction')
        self.assertEqual(response.data['chapter_name'], 'Foundation')
        self.assertIsNone(response.data['topic_name'])

    def test_case_3_create_question_full_hierarchy(self):
        """Case 3: Full hierarchy (Category + Level + Subject + Chapter + Topic) is valid and saves."""
        data = {
            'question_type': 'mcq',
            'status': 'approved',
            'difficulty': 'easy',
            'category': self.cat1.id,
            'position': self.level1.id,
            'subject': self.sub1.id,
            'chapter': self.chap1.id,
            'topic': self.top1.id,
            'text': 'A foundation is shallow if depth/width ratio is:',
            'option_a': 'Less than or equal to 1',
            'option_b': 'Greater than 5',
            'option_c': 'Between 10 and 15',
            'option_d': 'Always zero',
            'correct_option': 'A',
            'marks': 1,
            'negative_marks': 0.2,
            'expected_time_minutes': 1,
        }
        response = self.client.post('/api/admin/questions/', data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        q = Question.objects.get(id=response.data['id'])
        self.assertEqual(q.subject_id, self.sub1.id)
        self.assertEqual(q.chapter_id, self.chap1.id)
        self.assertEqual(q.topic_id, self.top1.id)
        self.assertEqual(response.data['subject_name'], 'Building Construction')
        self.assertEqual(response.data['chapter_name'], 'Foundation')
        self.assertEqual(response.data['topic_name'], 'Shallow Foundation')

    def test_mismatched_topic_and_chapter_rejected(self):
        """Topic belonging to Balance Sheet must be rejected when Chapter is Foundation."""
        data = {
            'question_type': 'mcq',
            'status': 'draft',
            'difficulty': 'medium',
            'subject': self.sub1.id,
            'chapter': self.chap1.id,
            'topic': self.top2.id, # from Banking / Accountancy
            'text': 'Mismatched topic test question?',
            'option_a': 'A', 'option_b': 'B', 'option_c': 'C', 'option_d': 'D',
            'correct_option': 'A',
        }
        response = self.client.post('/api/admin/questions/', data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('topic', response.data)

    def test_mismatched_chapter_and_subject_rejected(self):
        """Chapter belonging to Accountancy must be rejected when Subject is Building Construction."""
        data = {
            'question_type': 'mcq',
            'status': 'draft',
            'difficulty': 'medium',
            'subject': self.sub1.id,
            'chapter': self.chap2.id, # from Accountancy
            'text': 'Mismatched chapter test question?',
            'option_a': 'A', 'option_b': 'B', 'option_c': 'C', 'option_d': 'D',
            'correct_option': 'A',
        }
        response = self.client.post('/api/admin/questions/', data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('chapter', response.data)

    def test_mismatched_subject_and_position_rejected(self):
        """Subject belonging to 5th Level must be rejected when Position is Officer Level."""
        data = {
            'question_type': 'mcq',
            'status': 'draft',
            'difficulty': 'medium',
            'position': self.level2.id, # Officer Level (Banking)
            'subject': self.sub1.id,   # Building Construction (PSC 5th Level)
            'text': 'Mismatched subject position test question?',
            'option_a': 'A', 'option_b': 'B', 'option_c': 'C', 'option_d': 'D',
            'correct_option': 'A',
        }
        response = self.client.post('/api/admin/questions/', data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('subject', response.data)

    def test_question_without_subject_is_valid(self):
        """New question with Category and Position but without Subject is valid and saves."""
        data = {
            'status': 'draft',
            'category': self.cat1.id,
            'position': self.level1.id,
            'subject': None,
            'chapter': None,
            'topic': None,
            'text': 'Broad question without specific subject?',
            'option_a': 'A', 'option_b': 'B', 'option_c': 'C', 'option_d': 'D',
            'correct_option': 'A',
        }
        response = self.client.post('/api/admin/questions/', data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        q = Question.objects.get(id=response.data['id'])
        self.assertIsNone(q.subject)
        self.assertIsNone(q.chapter)
        self.assertIsNone(q.topic)
        self.assertEqual(q.exam_id, self.level1.id)
        self.assertEqual(q.category_id, self.cat1.id)
        self.assertEqual(response.data['position_name'], '5th Level')
        self.assertEqual(response.data['category_name'], 'PSC Exams')
        self.assertIsNone(response.data['subject_name'])
