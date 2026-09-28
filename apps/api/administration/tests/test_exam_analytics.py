from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse
from exams.models import Examination, ExaminationAttempt, ExamCategory, Exam, Question, Topic, StudentAnswer, Chapter, Subject, Paper
from django.utils import timezone
import datetime

User = get_user_model()

class ExamAnalyticsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_superuser(username='admin', password='password', email='admin@test.com')
        self.admin_user.role = 'admin'
        self.admin_user.save(update_fields=['role'])
        self.student_user = User.objects.create_user(username='student1', password='password', email='s1@test.com')
        self.student_user2 = User.objects.create_user(username='student2', password='password', email='s2@test.com')
        
        self.category = ExamCategory.objects.create(name='Test Category', description='test-category')
        self.parent_exam = Exam.objects.create(name='Parent Exam', category=self.category, description='parent-exam')
        self.exam = Examination.objects.create(
            title='Test Exam',
            category=self.category,
            exam=self.parent_exam,
            total_questions=10,
            time_limit=60,
            total_marks=100,
            passing_marks=40,
            created_by=self.admin_user
        )
        
    def test_analytics_no_attempts(self):
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('admin-examination-analytics', kwargs={'pk': self.exam.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['summary']['total_attempts'], 0)
        
    def test_analytics_with_attempts(self):
        # Create evaluated attempts
        ExaminationAttempt.objects.create(
            examination=self.exam, student=self.student_user, 
            status='evaluated', score=80.0, passed=True, 
            time_taken_seconds=1200, started_at=timezone.now(), submitted_at=timezone.now()
        )
        ExaminationAttempt.objects.create(
            examination=self.exam, student=self.student_user2, 
            status='evaluated', score=30.0, passed=False, 
            time_taken_seconds=600, started_at=timezone.now(), submitted_at=timezone.now()
        )
        
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('admin-examination-analytics', kwargs={'pk': self.exam.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data
        self.assertEqual(data['summary']['total_attempts'], 2)
        self.assertEqual(data['summary']['completed_attempts'], 2)
        self.assertEqual(data['summary']['average_score'], 55.0)
        self.assertEqual(data['summary']['highest_score'], 80.0)
        self.assertEqual(data['summary']['lowest_score'], 30.0)
        self.assertEqual(data['summary']['pass_count'], 1)
        self.assertEqual(data['summary']['fail_count'], 1)

    def test_results_pagination(self):
        for i in range(15):
            ExaminationAttempt.objects.create(
                examination=self.exam, student=self.student_user, 
                status='evaluated', score=50.0 + i, passed=True, 
                time_taken_seconds=1000, started_at=timezone.now(), submitted_at=timezone.now()
            )
        
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('admin-examination-results', kwargs={'pk': self.exam.id})
        response = self.client.get(f"{url}?page=1&page_size=10")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 15)
        self.assertEqual(len(response.data['results']), 10)
        
        # Test rank ordering (highest score first)
        self.assertEqual(response.data['results'][0]['score'], 64.0)

    def test_unauthorized_access(self):
        self.client.force_authenticate(user=self.student_user)
        url = reverse('admin-examination-analytics', kwargs={'pk': self.exam.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_exams_overview_counts_examinations_not_taxonomy(self):
        self.parent_exam.status = 'inactive'
        self.parent_exam.save()
        Examination.objects.create(
            title='Published Exam',
            category=self.category,
            exam=self.parent_exam,
            status='published',
            created_by=self.admin_user,
        )

        cache.delete('admin:exams:overview')
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(reverse('admin-exams-overview'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['totalExams'], 2)
        self.assertEqual(response.data['activeExams'], 1)

    def test_advanced_analytics_and_question_performance(self):
        # Create questions
        paper = Paper.objects.create(name='test_paper', exam=self.parent_exam)
        subject = Subject.objects.create(name='test_subj', paper=paper)
        chapter = Chapter.objects.create(title='test_chap', subject=subject)
        topic = Topic.objects.create(name='test_topic', chapter=chapter)
        q1 = Question.objects.create(text='q1', topic=topic, difficulty='easy', correct_option='A')
        q2 = Question.objects.create(text='q2', topic=topic, difficulty='hard', correct_option='B')
        
        attempt = ExaminationAttempt.objects.create(
            examination=self.exam, student=self.student_user, 
            status='evaluated', score=50.0, percentage=50.0, passed=True, 
            time_taken_seconds=1200, started_at=timezone.now(), submitted_at=timezone.now()
        )
        StudentAnswer.objects.create(attempt=attempt, question=q1, is_correct=True, selected_option='A')
        StudentAnswer.objects.create(attempt=attempt, question=q2, is_correct=False, selected_option='C')
        
        attempt2 = ExaminationAttempt.objects.create(
            examination=self.exam, student=self.student_user2, 
            status='evaluated', score=0.0, percentage=0.0, passed=False, 
            time_taken_seconds=600, started_at=timezone.now(), submitted_at=timezone.now()
        )
        StudentAnswer.objects.create(attempt=attempt2, question=q1, is_correct=False, selected_option='B')
        StudentAnswer.objects.create(attempt=attempt2, question=q2, is_correct=False, selected_option=None) # skipped
        
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('admin-examination-analytics', kwargs={'pk': self.exam.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        data = response.data
        self.assertEqual(data['summary']['total_attempts'], 2)
        self.assertEqual(data['time_statistics']['average_duration_seconds'], 900.0)
        
        q_perf = {q['question_id']: q for q in data['question_performance']}
        self.assertEqual(q_perf[q1.id]['correct'], 1)
        self.assertEqual(q_perf[q1.id]['incorrect'], 1)
        self.assertEqual(q_perf[q1.id]['skipped'], 0)
        
        self.assertEqual(q_perf[q2.id]['correct'], 0)
        self.assertEqual(q_perf[q2.id]['incorrect'], 1)
        self.assertEqual(q_perf[q2.id]['skipped'], 1)
        
        diff_perf = {d['level']: d for d in data['difficulty_performance']}
        self.assertEqual(diff_perf['Easy']['attempts'], 2)
        self.assertEqual(diff_perf['Hard']['attempts'], 2)

    def test_results_annotations_and_ranking(self):
        paper = Paper.objects.create(name='test_paper', exam=self.parent_exam)
        subject = Subject.objects.create(name='test_subj', paper=paper)
        chapter = Chapter.objects.create(title='test_chap', subject=subject)
        topic = Topic.objects.create(name='test_topic', chapter=chapter)
        q1 = Question.objects.create(text='q1', topic=topic, difficulty='easy', correct_option='A')
        
        attempt = ExaminationAttempt.objects.create(
            examination=self.exam, student=self.student_user, 
            status='evaluated', score=50.0, passed=True, 
            time_taken_seconds=1200, started_at=timezone.now(), submitted_at=timezone.now()
        )
        StudentAnswer.objects.create(attempt=attempt, question=q1, is_correct=True, selected_option='A')
        
        attempt2 = ExaminationAttempt.objects.create(
            examination=self.exam, student=self.student_user2, 
            status='evaluated', score=100.0, passed=True, 
            time_taken_seconds=600, started_at=timezone.now(), submitted_at=timezone.now()
        )
        StudentAnswer.objects.create(attempt=attempt2, question=q1, is_correct=True, selected_option='A')
        
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('admin-examination-results', kwargs={'pk': self.exam.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        results = response.data['results']
        # attempt2 should be rank 1 (score 100), attempt 1 rank 2 (score 50)
        self.assertEqual(results[0]['id'], attempt2.id)
        self.assertEqual(results[0]['rank'], 1)
        self.assertEqual(results[0]['correct_answers'], 1)
        
        self.assertEqual(results[1]['id'], attempt.id)
        self.assertEqual(results[1]['rank'], 2)
