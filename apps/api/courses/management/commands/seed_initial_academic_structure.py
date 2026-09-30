from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from courses.models import Course
from exams.models import Exam, ExamCategory


STRUCTURE = (
    {
        'category': 'PSC Exams',
        'category_aliases': ('Psc Exam', 'PSC Exam'),
        'order': 1,
        'levels': (
            {
                'name': '4th Level',
                'order': 1,
                'preparations': (
                    {'name': 'Assistant Civil Engineer', 'aliases': ('Civil engineering', 'Civil'), 'status': 'active'},
                    {'name': 'Amin/Surveyor', 'status': 'coming_soon'},
                ),
            },
            {
                'name': '5th Level',
                'order': 2,
                'preparations': (
                    {'name': 'Civil Sub Engineer', 'aliases': ('Civil',), 'status': 'active'},
                    {'name': 'Amin/Surveyor', 'status': 'coming_soon'},
                ),
            },
            {
                'name': '7th Level',
                'order': 3,
                'preparations': (
                    {'name': 'Civil Engineer', 'aliases': ('Civil',), 'status': 'active'},
                    {'name': 'Geomatic', 'status': 'coming_soon'},
                    {'name': 'Computer/IT', 'aliases': ('Computer',), 'status': 'coming_soon'},
                ),
            },
        ),
    },
    {
        'category': 'License Exams',
        'category_aliases': ('License Exam', 'Licence Exam'),
        'order': 2,
        'preparations': (
            {'name': 'Civil Engineering', 'status': 'active'},
            {'name': 'Geomatics Engineering', 'status': 'coming_soon'},
            {'name': 'Computer / IT Engineering', 'status': 'coming_soon'},
            {'name': 'Architecture', 'status': 'coming_soon'},
        ),
    },
    {'category': 'Entrance Exams', 'category_aliases': ('Entrance Exam',), 'order': 3, 'preparations': ()},
    {'category': 'University Exams', 'category_aliases': ('University Exam',), 'order': 4, 'preparations': ()},
)


def _find_unique(existing, names, scope, label):
    canonical_name = names[0].casefold()
    exact_matches = [
        obj for obj in existing
        if scope(obj) and obj.name.casefold() == canonical_name
    ]
    if len(exact_matches) > 1:
        raise CommandError(
            f'Multiple existing {label} records match the canonical name {names[0]!r}. '
            'Resolve the ambiguity manually; no records were changed.'
        )
    if exact_matches:
        return exact_matches[0]

    aliases = {name.casefold() for name in names[1:]}
    matches = [obj for obj in existing if scope(obj) and obj.name.casefold() in aliases]
    if len(matches) > 1:
        raise CommandError(
            f'Multiple existing {label} records match {sorted(names)}. '
            'Resolve the ambiguity manually; no records were changed.'
        )
    return matches[0] if matches else None


class Command(BaseCommand):
    help = 'Safely create or reconcile the required initial academic structure and its active Courses.'

    @transaction.atomic
    def handle(self, *args, **options):
        categories = list(ExamCategory.objects.all())
        exams = list(Exam.objects.select_related('category', 'parent').all())
        starting_exam_ids = {exam.pk for exam in exams}
        created_categories = created_courses = 0
        offerings = []

        for category_data in STRUCTURE:
            category_name = category_data['category']
            category_aliases = (category_name,) + category_data.get('category_aliases', ())
            category = _find_unique(
                categories,
                category_aliases,
                lambda item: True,
                f"ExamCategory for '{category_name}'",
            )
            if category is None:
                category = ExamCategory.objects.create(name=category_name)
                categories.append(category)
                created_categories += 1
            category.name = category_name
            category.is_active = True
            category.order = category_data['order']
            category.save(update_fields=('name', 'is_active', 'order', 'updated_at'))

            root_levels = []
            for level_data in category_data.get('levels', ()):
                level = self._ensure_exam(
                    exams, category, None, level_data['name'], (), 'active', level_data['order']
                )
                if level.pk not in {item.pk for item in root_levels}:
                    root_levels.append(level)
                for prep_order, preparation in enumerate(level_data['preparations'], start=1):
                    prep = self._ensure_exam(
                        exams,
                        category,
                        level,
                        preparation['name'],
                        preparation.get('aliases', ()),
                        preparation['status'],
                        prep_order,
                    )
                    if preparation['status'] == 'active':
                        offerings.append((prep, category_name, level.name))

            for prep_order, preparation in enumerate(category_data.get('preparations', ()), start=1):
                prep = self._ensure_exam(
                    exams,
                    category,
                    None,
                    preparation['name'],
                    preparation.get('aliases', ()),
                    preparation['status'],
                    prep_order,
                )
                if preparation['status'] == 'active':
                    offerings.append((prep, category_name, None))

            if category_name == 'PSC Exams':
                obsolete_nodes = (
                    ('5th Level', 'Computer'),
                    ('7th Level', 'Surveyor'),
                )
                for level_name, exam_name in obsolete_nodes:
                    level = Exam.objects.filter(
                        category=category, parent__isnull=True, name__iexact=level_name
                    ).first()
                    if level:
                        legacy_exam = Exam.objects.filter(
                            category=category, parent=level, name__iexact=exam_name
                        ).first()
                        if legacy_exam:
                            self._archive_exam_tree(legacy_exam)

        for exam, category_name, level_name in offerings:
            linked_courses = list(Course.objects.filter(exam=exam).order_by('id'))
            if linked_courses:
                continue

            course_name = exam.name
            slug_base = slugify(f'{course_name} {level_name or category_name}')
            slug = slug_base
            if Course.objects.filter(slug=slug).exists():
                slug = f'{slug_base}-{exam.pk}'
            if Course.objects.filter(slug=slug).exists():
                raise CommandError(
                    f"Cannot create the Course for '{exam.name}': slug '{slug}' is already in use."
                )

            Course.objects.create(
                title=course_name,
                slug=slug,
                status='published',
                exam=exam,
                is_open_for_enrollment=True,
            )
            created_courses += 1

        self.stdout.write(self.style.SUCCESS(
            'Academic structure reconciled without deleting records: '
            f'{created_categories} categories, '
            f'{Exam.objects.exclude(pk__in=starting_exam_ids).count()} academic nodes, '
            f'{created_courses} active Courses created.'
        ))
        self.stdout.write(
            'Existing unmatched categories, exams, Courses, subjects, chapters, topics, '
            'packages, subscriptions, and payment records were preserved.'
        )

    def _ensure_exam(self, exams, category, parent, name, aliases, exam_status, order):
        exam = _find_unique(
            exams,
            (name,) + tuple(aliases),
            lambda item: item.category_id == category.pk and item.parent_id == getattr(parent, 'pk', None),
            f"Exam '{name}'",
        )
        if exam is None:
            exam = Exam.objects.create(
                category=category,
                parent=parent,
                name=name,
                status=exam_status,
                order=order,
            )
            exams.append(exam)
        else:
            exam.category = category
            exam.parent = parent
            exam.name = name
            exam.status = exam_status
            exam.order = order
            exam.save()
        return exam

    def _archive_exam_tree(self, exam):
        for child in exam.children.all():
            self._archive_exam_tree(child)
        if exam.status != 'inactive':
            exam.status = 'inactive'
            exam.save()
        for course in Course.objects.filter(exam=exam):
            if course.status != 'archived' or course.is_open_for_enrollment:
                course.status = 'archived'
                course.is_open_for_enrollment = False
                course.save(update_fields=('status', 'is_open_for_enrollment', 'updated_at'))
