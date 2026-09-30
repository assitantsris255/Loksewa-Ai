from rest_framework import status
from rest_framework.test import APITestCase

from core.models import User
from exams.models import ExamCategory, Exam, Paper, Subject, Chapter, Topic


class AcademicTreeDataSafetyTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='tree_admin', password='pw', role='admin', is_staff=True,
        )
        self.category = ExamCategory.objects.create(name='PSC')
        self.exam = Exam.objects.create(category=self.category, name='5th Level')
        self.paper = Paper.objects.create(exam=self.exam, name='Paper I')
        self.subject = Subject.objects.create(paper=self.paper, name='General Knowledge')
        self.chapter = Chapter.objects.create(subject=self.subject, title='Geography')
        self.topic = Topic.objects.create(chapter=self.chapter, name='Rivers')
        self.client.force_authenticate(user=self.admin)

    def test_force_delete_preserves_shared_academic_tree(self):
        response = self.client.delete(
            f'/api/admin/syllabus/categories/{self.category.id}/?force=true'
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(ExamCategory.objects.filter(pk=self.category.pk).exists())
        self.assertTrue(Exam.objects.filter(pk=self.exam.pk).exists())
        self.assertTrue(Paper.objects.filter(pk=self.paper.pk).exists())
        self.assertTrue(Subject.objects.filter(pk=self.subject.pk).exists())
        self.assertTrue(Chapter.objects.filter(pk=self.chapter.pk).exists())
        self.assertTrue(Topic.objects.filter(pk=self.topic.pk).exists())