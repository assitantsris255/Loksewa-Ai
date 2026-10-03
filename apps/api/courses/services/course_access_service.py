"""CourseAccessService: The canonical, database-backed Course-Based Access Control
System for LoksewaAI.

This service is the single source of truth for:
- Course entitlement (which published courses a student is authorized to access)
- Academic hierarchy scope (which exams, subjects, chapters, and topics are accessible)
- Resource scoping and filtering (Notes/StudyMaterials, Examinations/Attempts, Practice Questions)
- Object-level permission verification

Entitlement sources evaluated:
1. Active unexpired Enrollment in a published course.
2. Active unexpired Subscription for:
   - ALL_ACCESS plan: unlocks all published courses.
   - BUNDLE plan: unlocks all configured eligible courses.
   - MULTI plan: unlocks courses selected in SubscriptionCourseSelection or approved CourseApplication.
   - SINGLE plan: unlocks the plan's course or selected course.
3. Admin-granted access:
   - Subscriptions created via ADMIN_GRANT.
   - StudentProfile with access_origin='ADMIN_GRANTED' and valid admin_access_expiry.
4. Non-enforced mode: If platform-wide subscription enforcement is explicitly disabled.

Strict Security Rules:
- A student cannot access resources simply by setting profile target preferences.
- A student cannot access resources by guessing IDs or passing frontend parameters.
- Pending or rejected payments do NOT grant access.
- Expired, cancelled, or suspended subscriptions/enrollments do NOT grant access.
- Non-published courses (draft, coming_soon, archived) NEVER grant student access.
- Staff and teachers have privileged access across published academic content.
"""

from typing import Optional, Set, Dict, Any, Union
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied


class CourseAccessService:
    STAFF_ROLES = ('teacher', 'admin', 'super-admin')

    @classmethod
    def is_privileged(cls, user) -> bool:
        """Returns True if user is a teacher, administrator, or staff."""
        if not user or not user.is_authenticated:
            return False
        return bool(
            user.is_staff
            or user.is_superuser
            or getattr(user, 'role', None) in cls.STAFF_ROLES
        )

    @classmethod
    def get_accessible_courses(cls, user) -> QuerySet:
        """
        Returns the authoritative QuerySet of Course objects `user` is authorized to access.
        Excludes all non-published courses.
        """
        from courses.models import Course, Enrollment

        if not user or not user.is_authenticated:
            return Course.objects.none()

        if cls.is_privileged(user):
            return Course.objects.filter(status='published')

        now = timezone.now()
        accessible_course_ids: Set[int] = set()

        # 1. Active unexpired enrollments in published courses
        enrolled_ids = Enrollment.objects.filter(
            student=user,
            status='active',
            course__status='published',
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).values_list('course_id', flat=True)
        accessible_course_ids.update(enrolled_ids)

        # 2. Active subscriptions
        from subscriptions.models import Subscription, SubscriptionCourseSelection
        from courses.models import CourseApplication

        active_subs = (
            Subscription.objects.filter(student=user, status='ACTIVE', expiry_date__gt=now)
            .select_related('plan')
            .prefetch_related('plan__eligible_courses')
        )

        for sub in active_subs:
            plan = sub.plan
            if not plan:
                continue

            pkg_type = getattr(plan, 'package_type', 'SINGLE')

            if pkg_type == 'ALL_ACCESS':
                # ALL_ACCESS unlocks all currently published courses
                return Course.objects.filter(status='published')

            sub_payment = None
            try:
                sub_payment = getattr(sub, 'payment', None)
            except Exception:
                sub_payment = None

            if pkg_type == 'BUNDLE':
                # Bundle grants all configured eligible published courses
                bundle_courses = plan.eligible_courses.filter(status='published').values_list('id', flat=True)
                accessible_course_ids.update(bundle_courses)

            elif pkg_type == 'MULTI':
                # Multi grants courses recorded in course selections or approved applications
                selection_q = Q(subscription=sub)
                if sub_payment:
                    selection_q |= Q(payment=sub_payment)
                selections = SubscriptionCourseSelection.objects.filter(
                    selection_q, course__status='published'
                ).values_list('course_id', flat=True)
                accessible_course_ids.update(selections)

                if sub_payment:
                    app_courses = CourseApplication.objects.filter(
                        subscription_payment=sub_payment,
                        status='approved',
                        course__status='published',
                    ).values_list('course_id', flat=True)
                    accessible_course_ids.update(app_courses)

            elif pkg_type == 'SINGLE':
                # Single preparation package
                if plan.course_id and plan.course and plan.course.status == 'published':
                    accessible_course_ids.add(plan.course_id)
                elif plan.eligible_courses.count() == 1:
                    first_course = plan.eligible_courses.first()
                    if first_course and first_course.status == 'published':
                        accessible_course_ids.add(first_course.id)

                # Check if course was explicitly selected on payment or subscription
                selection_q = Q(subscription=sub)
                if sub_payment:
                    selection_q |= Q(payment=sub_payment)
                selections = SubscriptionCourseSelection.objects.filter(
                    selection_q, course__status='published'
                ).values_list('course_id', flat=True)
                accessible_course_ids.update(selections)

                if sub_payment:
                    app_courses = CourseApplication.objects.filter(
                        subscription_payment=sub_payment,
                        status='approved',
                        course__status='published',
                    ).values_list('course_id', flat=True)
                    accessible_course_ids.update(app_courses)

        # 3. Admin-granted access fallback & open-enforcement fallback
        from core.models import AdminSettings
        from subscriptions.access import has_admin_granted_access

        if not AdminSettings.is_subscription_enforced() or has_admin_granted_access(user):
            try:
                profile = getattr(user, 'student_profile', None)
                if profile:
                    if profile.target_course_id:
                        target_c = Course.objects.filter(id=profile.target_course_id, status='published').first()
                        if target_c:
                            accessible_course_ids.add(target_c.id)
                    elif profile.target_position_id:
                        target_courses = Course.objects.filter(
                            exam_id=profile.target_position_id,
                            status='published'
                        ).values_list('id', flat=True)
                        accessible_course_ids.update(target_courses)
            except Exception:
                pass

        if not accessible_course_ids:
            return Course.objects.none()

        return Course.objects.filter(id__in=accessible_course_ids, status='published')

    @classmethod
    def has_course_access(cls, user, course_or_id: Union[int, Any]) -> bool:
        """Determines whether `user` has access to `course_or_id`."""
        if not user or not user.is_authenticated:
            return False
        if cls.is_privileged(user):
            return True

        course_id = course_or_id.id if hasattr(course_or_id, 'id') else course_or_id
        try:
            course_id = int(course_id)
        except (TypeError, ValueError):
            return False

        return cls.get_accessible_courses(user).filter(id=course_id).exists()

    @classmethod
    def require_course_access(cls, user, course_or_id: Union[int, Any]):
        """
        Returns the Course instance if accessible, or raises PermissionDenied.
        """
        if not user or not user.is_authenticated:
            raise PermissionDenied("Authentication required to access this course.")

        course_id = course_or_id.id if hasattr(course_or_id, 'id') else course_or_id
        from courses.models import Course

        course = cls.get_accessible_courses(user).filter(id=course_id).first()
        if not course:
            raise PermissionDenied("You do not have access to this course.")
        return course

    @classmethod
    def get_course_exam_ids(cls, course) -> Set[int]:
        """
        Returns the active Exam ID for `course` and all of its descendant child Exam IDs.
        """
        if not course or not getattr(course, 'exam_id', None):
            return set()

        from exams.models import Exam

        rows = list(Exam.objects.filter(is_active=True).values_list('id', 'parent_id', 'status'))
        children: Dict[Optional[int], list] = {}
        for exam_id, parent_id, _status in rows:
            children.setdefault(parent_id, []).append(exam_id)
        status_of = {exam_id: status for exam_id, _p, status in rows}

        covered: Set[int] = set()
        stack = [course.exam_id] if course.exam_id in status_of else []
        while stack:
            node = stack.pop()
            if node in covered:
                continue
            covered.add(node)
            stack.extend(children.get(node, []))

        return {i for i in covered if status_of.get(i) == 'active'}

    @classmethod
    def get_accessible_exam_ids(cls, user, exams=None) -> Optional[Set[int]]:
        """
        Returns None for staff/teachers (unrestricted),
        or the set of active Exam IDs covered by the student's authorized courses.
        """
        if cls.is_privileged(user):
            return None

        accessible_courses = cls.get_accessible_courses(user)
        if not accessible_courses.exists():
            return set()

        from exams.models import Exam

        roots = set(accessible_courses.filter(exam_id__isnull=False).values_list('exam_id', flat=True))
        if not roots:
            return set()

        if exams is None:
            rows = list(Exam.objects.filter(is_active=True).values_list('id', 'parent_id', 'status'))
        else:
            rows = [(e.id, e.parent_id, e.status) for e in exams]

        children: Dict[Optional[int], list] = {}
        for exam_id, parent_id, _status in rows:
            children.setdefault(parent_id, []).append(exam_id)
        status_of = {exam_id: status for exam_id, _p, status in rows}

        covered: Set[int] = set()
        stack = [r for r in roots if r in status_of]
        while stack:
            node = stack.pop()
            if node in covered:
                continue
            covered.add(node)
            stack.extend(children.get(node, []))

        return {i for i in covered if status_of.get(i) == 'active'}

    @classmethod
    def get_accessible_academic_scope(cls, user) -> Dict[str, Any]:
        """
        Returns full structured dictionary of accessible academic scope IDs for user:
        {
            'is_unrestricted': bool,
            'course_ids': Set[int],
            'exam_ids': Optional[Set[int]],
            'subject_ids': Optional[Set[int]],
            'chapter_ids': Optional[Set[int]],
            'topic_ids': Optional[Set[int]],
        }
        """
        if cls.is_privileged(user):
            return {
                'is_unrestricted': True,
                'course_ids': set(),
                'exam_ids': None,
                'subject_ids': None,
                'chapter_ids': None,
                'topic_ids': None,
            }

        courses = cls.get_accessible_courses(user)
        course_ids = set(courses.values_list('id', flat=True))
        exam_ids = cls.get_accessible_exam_ids(user) or set()

        if not exam_ids and not course_ids:
            return {
                'is_unrestricted': False,
                'course_ids': set(),
                'exam_ids': set(),
                'subject_ids': set(),
                'chapter_ids': set(),
                'topic_ids': set(),
            }

        from exams.models import Subject, Chapter, Topic

        subject_ids = set(Subject.objects.filter(paper__exam_id__in=exam_ids, is_active=True).values_list('id', flat=True))
        chapter_ids = set(Chapter.objects.filter(subject_id__in=subject_ids).values_list('id', flat=True))
        topic_ids = set(Topic.objects.filter(chapter_id__in=chapter_ids).values_list('id', flat=True))

        return {
            'is_unrestricted': False,
            'course_ids': course_ids,
            'exam_ids': exam_ids,
            'subject_ids': subject_ids,
            'chapter_ids': chapter_ids,
            'topic_ids': topic_ids,
        }

    # =========================================================================
    # RESOURCE QUERYSET FILTERS
    # =========================================================================

    @classmethod
    def filter_notes_queryset(cls, user, queryset: QuerySet, allow_public_free: bool = False) -> QuerySet:
        """
        Scopes StudyMaterial querysets to materials belonging to the student's authorized
        courses or academic taxonomy.
        """
        if cls.is_privileged(user):
            return queryset

        if not user or not user.is_authenticated:
            if allow_public_free:
                return queryset.filter(status='published', access_type='free', course__isnull=True)
            return queryset.none()

        auth_courses = cls.get_accessible_courses(user)
        auth_course_ids = set(auth_courses.values_list('id', flat=True))
        auth_exam_ids = cls.get_accessible_exam_ids(user) or set()

        if not auth_course_ids and not auth_exam_ids:
            if allow_public_free:
                return queryset.filter(status='published', access_type='free', course__isnull=True)
            return queryset.none()

        q = Q(course_id__in=auth_course_ids)
        if auth_exam_ids:
            q |= Q(course__isnull=True, exam_id__in=auth_exam_ids)
            q |= Q(course__isnull=True, subject__paper__exam_id__in=auth_exam_ids)
            q |= Q(course__isnull=True, topic__chapter__subject__paper__exam_id__in=auth_exam_ids)

        if allow_public_free:
            q |= Q(course__isnull=True, access_type='free', status='published')

        qs = queryset.filter(q)

        # Enforce subscription package for premium materials
        from core.models import AdminSettings
        from subscriptions.access import has_active_subscription
        if AdminSettings.get_settings().enforce_subscription_access:
            if not has_active_subscription(user):
                qs = qs.filter(access_type='free')

        return qs

    @classmethod
    def has_note_access(cls, user, note) -> bool:
        """Determines whether `user` may access the given StudyMaterial instance."""
        if cls.is_privileged(user):
            return True
        if not user or not user.is_authenticated:
            return bool(note.status == 'published' and note.access_type == 'free' and note.course_id is None)

        if note.status != 'published':
            return False

        # If note is tied directly to a course
        if note.course_id:
            if not cls.has_course_access(user, note.course_id):
                return False
        elif note.exam_id:
            scope = cls.get_accessible_exam_ids(user)
            if not scope or note.exam_id not in scope:
                return False

        # Premium gate
        from core.models import AdminSettings
        from subscriptions.access import has_active_subscription
        if AdminSettings.get_settings().enforce_subscription_access:
            if note.access_type == 'premium' and not has_active_subscription(user):
                return False

        return True

    @classmethod
    def filter_examinations_queryset(cls, user, queryset: QuerySet, target_course=None) -> QuerySet:
        """
        Scopes Examination querysets to examinations authorized for this student.
        """
        if cls.is_privileged(user):
            if target_course is not None:
                from courses.models import Course
                c_obj = target_course if isinstance(target_course, Course) else Course.objects.filter(id=target_course).first()
                if not c_obj:
                    return queryset.none()
                exam_ids = cls.get_course_exam_ids(c_obj)
                q = Q(course=c_obj)
                if exam_ids:
                    q |= Q(course__isnull=True, exam_id__in=exam_ids)
                return queryset.filter(q)
            return queryset

        if not user or not user.is_authenticated:
            return queryset.none()

        auth_courses = cls.get_accessible_courses(user)
        if not auth_courses.exists():
            # Only global platform-wide exams (course is null, exam is null or free)
            return queryset.filter(status__in=['published', 'live'], course__isnull=True, exam__isnull=True)

        if target_course is not None:
            from courses.models import Course
            c_id = target_course.id if isinstance(target_course, Course) else target_course
            c_obj = auth_courses.filter(id=c_id).first()
            if not c_obj:
                return queryset.none()
            exam_ids = cls.get_course_exam_ids(c_obj)
            q = Q(course=c_obj)
            if exam_ids:
                q |= Q(course__isnull=True, exam_id__in=exam_ids)
            return queryset.filter(q)

        auth_course_ids = list(auth_courses.values_list('id', flat=True))
        auth_exam_scope = cls.get_accessible_exam_ids(user) or set()
        q = Q(course_id__in=auth_course_ids)
        q |= Q(course__isnull=True, status__in=['published', 'live'], exam__isnull=True)
        if auth_exam_scope:
            q |= Q(course__isnull=True, exam_id__in=auth_exam_scope)

        return queryset.filter(q)

    @classmethod
    def has_examination_access(cls, user, examination) -> bool:
        """Determines whether `user` is authorized to access `examination`."""
        if not user or not user.is_authenticated:
            return False
        if cls.is_privileged(user):
            return True
        if getattr(user, 'role', None) != 'student':
            return False

        auth_courses = cls.get_accessible_courses(user)
        if not auth_courses.exists():
            return bool(examination.status in ('published', 'live') and examination.course_id is None and examination.exam_id is None)

        if examination.course_id:
            return auth_courses.filter(id=examination.course_id).exists()

        if examination.exam_id:
            scope = cls.get_accessible_exam_ids(user)
            return bool(scope and examination.exam_id in scope)

        return bool(examination.status in ('published', 'live') and examination.course_id is None)

    @classmethod
    def resolve_question_exam_id(cls, question) -> Optional[int]:
        """
        Resolves the canonical Exam ID for a question through its academic hierarchy:
        Topic -> Chapter -> Subject -> Paper -> Exam
        or Chapter -> Subject -> Paper -> Exam
        or Subject -> Paper -> Exam
        or direct exam_id.
        """
        if not question:
            return None

        # 1. Topic hierarchy
        if getattr(question, 'topic_id', None):
            topic = getattr(question, 'topic', None)
            if topic:
                chapter = getattr(topic, 'chapter', None)
                if chapter:
                    subject = getattr(chapter, 'subject', None)
                    if subject and getattr(subject, 'paper_id', None) and getattr(subject, 'paper', None):
                        exam_id = subject.paper.exam_id
                        if exam_id:
                            return exam_id

        # 2. Chapter hierarchy
        if getattr(question, 'chapter_id', None):
            chapter = getattr(question, 'chapter', None)
            if chapter:
                subject = getattr(chapter, 'subject', None)
                if subject and getattr(subject, 'paper_id', None) and getattr(subject, 'paper', None):
                    exam_id = subject.paper.exam_id
                    if exam_id:
                        return exam_id

        # 3. Subject hierarchy
        if getattr(question, 'subject_id', None):
            subject = getattr(question, 'subject', None)
            if subject and getattr(subject, 'paper_id', None) and getattr(subject, 'paper', None):
                exam_id = subject.paper.exam_id
                if exam_id:
                    return exam_id

        # 4. Direct exam
        if getattr(question, 'exam_id', None):
            return question.exam_id

        return None

    @classmethod
    def get_question_course(cls, question):
        """
        Returns the primary published Course instance for this question, or None.
        Determined through the authoritative hierarchy: Question -> Exam -> Course.
        """
        exam_id = cls.resolve_question_exam_id(question)
        if not exam_id:
            return None

        from courses.models import Course

        # Fast direct match on course.exam_id
        course = Course.objects.filter(exam_id=exam_id, status='published').first()
        if course:
            return course

        # Check if exam_id is a child/descendant of any published course's exam
        published_courses = Course.objects.filter(status='published', exam_id__isnull=False)
        for c in published_courses:
            if exam_id in cls.get_course_exam_ids(c):
                return c
        return None

    @classmethod
    def get_question_mapping_status(cls, question) -> str:
        """
        Determines the authoritative mapping status of a Question:
        - 'invalid': contradictory hierarchy (e.g. topic does not belong to chapter)
        - 'unassigned': no course mapping found
        - 'incomplete': maps to a course/exam, but missing subject/topic placement
        - 'mapped': fully and consistently mapped to course and academic scope
        """
        if not question:
            return 'unassigned'

        # 1. Check for contradictory/invalid hierarchy
        if question.topic_id and question.chapter_id:
            topic = getattr(question, 'topic', None)
            if topic and topic.chapter_id != question.chapter_id:
                return 'invalid'

        if question.chapter_id and question.subject_id:
            chapter = getattr(question, 'chapter', None)
            if chapter and chapter.subject_id != question.subject_id:
                return 'invalid'

        if question.subject_id and question.exam_id:
            subject = getattr(question, 'subject', None)
            if subject and getattr(subject, 'paper', None):
                sub_exam = subject.paper.exam
                if sub_exam and sub_exam.id != question.exam_id and getattr(sub_exam, 'parent_id', None) != question.exam_id:
                    return 'invalid'

        if question.exam_id and getattr(question, 'category_id', None):
            exam = getattr(question, 'exam', None)
            if exam and getattr(exam, 'category_id', None) and exam.category_id != question.category_id:
                return 'invalid'

        # 2. Check course connectivity
        course = cls.get_question_course(question)
        if not course:
            return 'unassigned'

        # 3. Check syllabus completeness
        # A fully mapped question has both a resolved subject and topic (or subject has no chapters)
        if question.subject_id and question.topic_id:
            return 'mapped'

        if question.subject_id:
            subject = getattr(question, 'subject', None)
            if subject and not subject.chapters.filter(is_active=True).exists():
                return 'mapped'

        return 'incomplete'

    @classmethod
    def get_all_course_exam_ids(cls) -> Set[int]:
        """Returns all exam IDs associated with published courses."""
        from courses.models import Course
        published_courses = Course.objects.filter(status='published', exam_id__isnull=False)
        all_ids: Set[int] = set()
        for c in published_courses:
            all_ids.update(cls.get_course_exam_ids(c))
        return all_ids

    @classmethod
    def filter_admin_questions_by_mapping(cls, queryset: QuerySet, status_filter: str) -> QuerySet:
        """
        Filters Question querysets by mapping status for Admin Question Bank:
        - 'mapped': fully mapped to course and academic scope
        - 'needs_mapping': all questions requiring admin mapping (incomplete, unassigned, invalid)
        - 'incomplete': linked to course but missing subject/topic
        - 'unassigned': not linked to any published course
        - 'invalid': contradictory hierarchy
        """
        if not status_filter or status_filter == 'all':
            return queryset

        course_exam_ids = list(cls.get_all_course_exam_ids())
        
        has_course_exam = (
            Q(exam_id__in=course_exam_ids) |
            Q(subject__paper__exam_id__in=course_exam_ids) |
            Q(chapter__subject__paper__exam_id__in=course_exam_ids) |
            Q(topic__chapter__subject__paper__exam_id__in=course_exam_ids)
        ) if course_exam_ids else Q(pk__in=[])

        from django.db.models import F
        invalid_q = (
            (Q(topic_id__isnull=False, chapter_id__isnull=False) & ~Q(topic__chapter_id=F('chapter_id'))) |
            (Q(chapter_id__isnull=False, subject_id__isnull=False) & ~Q(chapter__subject_id=F('subject_id')))
        )

        if status_filter == 'invalid':
            return queryset.filter(invalid_q)

        mapped_q = has_course_exam & Q(subject_id__isnull=False) & ~invalid_q
        if status_filter == 'mapped':
            return queryset.filter(mapped_q)

        if status_filter == 'needs_mapping':
            return queryset.exclude(mapped_q)

        if status_filter == 'incomplete':
            return queryset.filter(has_course_exam, subject_id__isnull=True).exclude(invalid_q)

        if status_filter == 'unassigned':
            return queryset.exclude(has_course_exam).exclude(invalid_q)

        return queryset

    @classmethod
    def filter_questions_queryset(cls, user, queryset: QuerySet, target_course=None) -> QuerySet:
        """
        Scopes Question querysets to questions under the student's authorized course/exam taxonomy.
        Excludes unassigned questions from student practice.
        """
        if cls.is_privileged(user):
            if target_course is not None:
                from courses.models import Course
                c_obj = target_course if isinstance(target_course, Course) else Course.objects.filter(id=target_course).first()
                if not c_obj:
                    return queryset.none()
                exam_ids = cls.get_course_exam_ids(c_obj)
                if not exam_ids:
                    return queryset.none()
                exam_ids_list = list(exam_ids)
                return queryset.filter(
                    Q(exam_id__in=exam_ids_list) |
                    Q(subject__paper__exam_id__in=exam_ids_list) |
                    Q(chapter__subject__paper__exam_id__in=exam_ids_list) |
                    Q(topic__chapter__subject__paper__exam_id__in=exam_ids_list)
                )
            return queryset

        if not user or not user.is_authenticated:
            return queryset.none()

        if target_course is not None:
            from courses.models import Course
            c_id = target_course.id if isinstance(target_course, Course) else target_course
            if not cls.has_course_access(user, c_id):
                return queryset.none()
            c_obj = Course.objects.filter(id=c_id, status='published').first()
            if not c_obj:
                return queryset.none()
            exam_ids = cls.get_course_exam_ids(c_obj)
        else:
            exam_ids = cls.get_accessible_exam_ids(user)

        if not exam_ids:
            return queryset.none()

        exam_ids_list = list(exam_ids)
        academic_mapped = Q(subject_id__isnull=False) | Q(topic_id__isnull=False) | Q(chapter_id__isnull=False)
        return queryset.filter(
            academic_mapped & (
                Q(exam_id__in=exam_ids_list) |
                Q(subject__paper__exam_id__in=exam_ids_list) |
                Q(chapter__subject__paper__exam_id__in=exam_ids_list) |
                Q(topic__chapter__subject__paper__exam_id__in=exam_ids_list)
            )
        )

    @classmethod
    def has_question_access(cls, user, question) -> bool:
        """
        Determines whether `user` is authorized to access `question`.
        Questions without complete course and academic mapping are strictly DENIED to students.
        """
        if cls.is_privileged(user):
            return True
        if not user or not user.is_authenticated:
            return False

        # Only approved questions are exposed to students
        if getattr(question, 'status', None) != 'approved':
            return False

        mapping_status = cls.get_question_mapping_status(question)
        if mapping_status != 'mapped':
            return False

        scope = cls.get_accessible_exam_ids(user)
        if scope is None:
            return True
        if not scope:
            return False

        exam_id = cls.resolve_question_exam_id(question)
        return bool(exam_id and exam_id in scope)

