from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from courses.models import Course
from exams.models import Exam, ExamCategory


class InitialAcademicStructureCommandTests(TestCase):
    def test_command_reuses_existing_rows_and_is_idempotent(self):
        psc, _ = ExamCategory.objects.get_or_create(name='PSC Exams')
        fourth_level, _ = Exam.objects.get_or_create(
            category=psc, parent=None, name='4th Level'
        )
        existing_preparation, _ = Exam.objects.get_or_create(
            category=psc, parent=fourth_level, name='Civil'
        )
        existing_course = Course.objects.create(
            title='Assistant Civil Engineer',
            slug='assistant-civil-engineer-4th-level',
            status='published',
            exam=existing_preparation,
            is_open_for_enrollment=True,
        )

        call_command('seed_initial_academic_structure', stdout=StringIO())
        call_command('seed_initial_academic_structure', stdout=StringIO())

        psc.refresh_from_db()
        existing_preparation.refresh_from_db()
        self.assertEqual(psc.name, 'PSC Exams')
        self.assertEqual(existing_preparation.name, 'Assistant Civil Engineer')
        self.assertEqual(existing_preparation.status, 'active')
        self.assertTrue(Course.objects.filter(pk=existing_course.pk, exam=existing_preparation).exists())
        self.assertEqual(ExamCategory.objects.filter(name='PSC Exams').count(), 1)

        self.assertEqual(
            Exam.objects.filter(category=psc, parent__isnull=True).count(),
            3,
        )
        self.assertEqual(
            Exam.objects.filter(category=psc, parent=fourth_level, name='Amin/Surveyor', status='coming_soon').count(),
            1,
        )
        self.assertEqual(
            Exam.objects.filter(category__name='License Exams', parent__isnull=True, status='coming_soon').count(),
            3,
        )
        self.assertEqual(Course.objects.filter(status='published', exam__is_active=True).count(), 4)
        self.assertEqual(ExamCategory.objects.filter(name__in=(
            'PSC Exams', 'License Exams', 'Entrance Exams', 'University Exams'
        )).count(), 4)