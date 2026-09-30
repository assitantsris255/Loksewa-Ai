"""Course access for students: the single check behind course-scoped Practice.

A student may use a course only through an ACTIVE, unexpired Enrollment (the
row the package-approval flow creates), and only while the course itself is
published - a Coming Soon, draft or archived course grants nothing even if an
enrollment row exists. Nothing else should re-implement this.
"""
from django.db.models import Q
from django.utils import timezone

from .models import Enrollment


def active_enrollments(user):
    """The student's enrollments that currently grant access."""
    now = timezone.now()
    return Enrollment.objects.filter(student=user, status='active').filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )


def course_access_denial(user, course_id):
    """Why `user` may not use course `course_id`, as a (status, message)
    pair - or None when access is granted. One query.

    Not being enrolled and not existing look the same (403): a student can't
    probe which course ids exist.
    """
    if authorized_courses(user).filter(id=course_id).exists():
        return None
    return 403, 'You are not enrolled in this course.'


STAFF_ROLES = ('teacher', 'admin', 'super-admin')


def authorized_exam_ids(user, exams=None):
    """The exams `user` may practise - the single answer to "which exams does
    this student's purchase cover?".

    Returns None for staff (unrestricted), otherwise a set of Exam ids, all of
    them published (Exam.status == 'active'; Coming Soon and inactive exams
    are never practisable). An exam is authorised when it is - or sits under -
    the exam of:

      * a course the student has a live Enrollment in, while that course is
        published. Enrollments are what an approved payment creates for every
        package type that names courses (SINGLE, MULTI via the student's
        selection, BUNDLE); a pending or rejected payment creates none, and
        the enrollment expires with the subscription;
      * any published course, if the student holds an active ALL_ACCESS
        subscription (that package type names no courses - it means all);
      * the student's profile target position - but only where no purchase
        model applies: while package enforcement is OFF, or for accounts an
        admin granted access to directly (those have no payment/enrollment).
        A self-registered student's target is what they *intend* to buy, not
        something they own, so with enforcement ON it grants nothing.

    `exams` may carry the active exam rows (objects with id / parent_id / status)
    the caller has already loaded, saving one query.

    Computed from the database on every call - nothing is cached or
    remembered, so a change to an enrollment, subscription or exam takes
    effect on the very next request.
    """
    if user.role in STAFF_ROLES:
        return None
    from django.db.models import Exists

    from core.models import AdminSettings
    from exams.models import Exam
    from subscriptions.access import has_admin_granted_access
    from subscriptions.models import Subscription
    from .models import Course

    now = timezone.now()
    enrolled = active_enrollments(user).filter(
        course__status='published', course__exam_id__isnull=False
    ).values_list('course__exam_id', flat=True)
    all_access = Subscription.objects.filter(
        student=user, status='ACTIVE', expiry_date__gt=now, plan__package_type='ALL_ACCESS'
    )
    everything = Course.objects.filter(
        status='published', exam_id__isnull=False
    ).filter(Exists(all_access)).values_list('exam_id', flat=True)
    roots = set(enrolled.union(everything))

    if not AdminSettings.is_subscription_enforced() or has_admin_granted_access(user):
        try:
            target = user.student_profile.target_position_id
        except Exception:  # no profile
            target = None
        if target:
            roots.add(target)

    # An exam can be a level node with services underneath it; owning the
    # parent covers its children. One read of the (small) exam tree.
    if exams is None:
        rows = list(Exam.objects.filter(is_active=True).values_list('id', 'parent_id', 'status'))
    else:
        rows = [(e.id, e.parent_id, e.status) for e in exams]
    children = {}
    for exam_id, parent_id, _status in rows:
        children.setdefault(parent_id, []).append(exam_id)
    status_of = {exam_id: status for exam_id, _p, status in rows}
    covered, stack = set(), [r for r in roots if r in status_of]
    while stack:
        node = stack.pop()
        if node in covered:
            continue
        covered.add(node)
        stack.extend(children.get(node, []))
    return {i for i in covered if status_of.get(i) == 'active'}


def authorized_courses(user):
    """The authoritative QuerySet of Course objects `user` is authorized to access.

    Rules:
    - Staff (teacher/admin/super-admin): all published courses.
    - Students with active ALL_ACCESS subscription: all published courses.
    - Students with active Enrollments: published courses with active unexpired enrollment.
    - Admin granted access: StudentProfile.target_course (if published) or enrolled courses.
    - Non-published courses (draft, coming_soon, archived) are NEVER returned.
    """
    from .models import Course

    if not user or not user.is_authenticated:
        return Course.objects.none()

    if user.role in STAFF_ROLES:
        return Course.objects.filter(status='published')

    from core.models import AdminSettings
    from subscriptions.access import has_admin_granted_access
    from subscriptions.models import Subscription

    now = timezone.now()

    # Check if student has active ALL_ACCESS subscription
    has_all_access = Subscription.objects.filter(
        student=user, status='ACTIVE', expiry_date__gt=now, plan__package_type='ALL_ACCESS'
    ).exists()
    if has_all_access:
        return Course.objects.filter(status='published')

    # Enrolled courses
    enrolled_course_ids = set(
        active_enrollments(user).filter(course__status='published').values_list('course_id', flat=True)
    )

    # Admin granted access fallback if applicable
    if not AdminSettings.is_subscription_enforced() or has_admin_granted_access(user):
        try:
            profile = getattr(user, 'student_profile', None)
            if profile:
                if profile.target_course_id:
                    enrolled_course_ids.add(profile.target_course_id)
                elif profile.target_position_id:
                    target_exam_course_ids = Course.objects.filter(
                        exam_id=profile.target_position_id,
                        status='published'
                    ).values_list('id', flat=True)
                    enrolled_course_ids.update(target_exam_course_ids)
        except Exception:
            pass

    return Course.objects.filter(id__in=enrolled_course_ids, status='published')


def invalidate_student_course_context(user_id):
    """Invalidate cached student course context for user_id."""
    if not user_id:
        return
    from django.core.cache import cache
    try:
        cache.delete(f'student_course_ctx:{user_id}')
    except Exception:
        pass


def get_student_course_context(user):
    """Canonical dictionary representation of the student's authorized course context:
    - active_course: dict or None
    - authorized_courses: list of dicts
    - subscription: package / subscription status dict
    - exam_schedule: next exam schedule dict for active_course.exam, or None
    - schedule_message: str or None
    """
    if not user or not user.is_authenticated:
        return {
            "active_course": None,
            "authorized_courses": [],
            "subscription": None,
            "exam_schedule": None,
            "schedule_message": "Not authenticated",
        }

    from django.core.cache import cache
    cache_key = f'student_course_ctx:{user.id}'
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    except Exception:
        pass

    from core.views import _get_package_status
    from exams.models import ExamSchedule
    from exams.schedule_serializers import StudentExamScheduleSerializer

    package_status = _get_package_status(user)
    auth_courses_qs = authorized_courses(user).select_related('exam', 'exam__category', 'exam__parent')
    auth_courses_list = list(auth_courses_qs)

    def serialize_course(c):
        category_name = None
        level_name = None
        if c.exam:
            if c.exam.category:
                category_name = c.exam.category.name
            if c.exam.parent:
                level_name = c.exam.parent.name
            else:
                level_name = c.exam.name

        return {
            "id": c.id,
            "title": c.title,
            "short_description": c.short_description or "",
            "slug": c.slug,
            "exam_id": c.exam_id,
            "exam_name": c.exam.name if c.exam else None,
            "category_name": category_name,
            "level_name": level_name,
            "thumbnail": c.thumbnail.url if c.thumbnail else None,
        }

    authorized_courses_data = [serialize_course(c) for c in auth_courses_list]
    active_course_obj = None

    if len(auth_courses_list) == 1:
        active_course_obj = auth_courses_list[0]
        try:
            profile = getattr(user, 'student_profile', None)
            if profile and profile.target_course_id != active_course_obj.id:
                profile.target_course = active_course_obj
                profile.save(update_fields=['target_course'])
        except Exception:
            pass
    elif len(auth_courses_list) > 1:
        profile = getattr(user, 'student_profile', None)
        target_course_id = profile.target_course_id if profile else None
        matching = next((c for c in auth_courses_list if c.id == target_course_id), None)
        if matching:
            active_course_obj = matching
        else:
            active_course_obj = auth_courses_list[0]
            if profile:
                try:
                    profile.target_course = active_course_obj
                    profile.save(update_fields=['target_course'])
                except Exception:
                    pass

    active_course_data = serialize_course(active_course_obj) if active_course_obj else None

    # Exam schedule for active course
    exam_schedule_data = None
    schedule_message = None
    if active_course_obj and active_course_obj.exam_id:
        today = timezone.now().date()
        schedule = ExamSchedule.objects.filter(
            exam_id=active_course_obj.exam_id,
            is_published=True,
            exam_date__gte=today
        ).select_related('exam_category', 'exam').order_by('-is_active', 'exam_date', 'exam_time').first()

        if not schedule and active_course_obj.exam and active_course_obj.exam.parent_id:
            schedule = ExamSchedule.objects.filter(
                exam_id=active_course_obj.exam.parent_id,
                is_published=True,
                exam_date__gte=today
            ).select_related('exam_category', 'exam').order_by('-is_active', 'exam_date', 'exam_time').first()

        if schedule:
            exam_schedule_data = StudentExamScheduleSerializer(schedule).data
        else:
            schedule_message = "No exam schedule configured for this course yet."
    else:
        if active_course_obj:
            schedule_message = "No exam schedule configured for this course yet."
        else:
            schedule_message = "No active course yet."

    result = {
        "active_course": active_course_data,
        "authorized_courses": authorized_courses_data,
        "subscription": package_status,
        "exam_schedule": exam_schedule_data,
        "schedule_message": schedule_message,
    }
    try:
        cache.set(cache_key, result, 30)
    except Exception:
        pass
    return result


def get_course_exam_ids(course):
    """Returns the set of active Exam IDs covered by a Course (its exam_id plus any descendant children)."""
    if not course or not course.exam_id:
        return set()
    from exams.models import Exam
    rows = list(Exam.objects.filter(is_active=True).values_list('id', 'parent_id', 'status'))
    children = {}
    for exam_id, parent_id, _status in rows:
        children.setdefault(parent_id, []).append(exam_id)
    status_of = {exam_id: status for exam_id, _p, status in rows}

    covered = set()
    stack = [course.exam_id] if course.exam_id in status_of else []
    while stack:
        node = stack.pop()
        if node in covered:
            continue
        covered.add(node)
        stack.extend(children.get(node, []))
    return {i for i in covered if status_of.get(i) == 'active'}


def get_authorized_examination_filter(user, target_course=None):
    """
    Returns a Django Q object to filter Examination querysets to ONLY examinations
    authorized for this student. If the student has NO valid course authorization
    (or if target_course is specified but unauthorized), returns None (which the caller
    must translate to Examination.objects.none()).
    """
    if not user or not user.is_authenticated:
        return None

    if user.role in STAFF_ROLES:
        if target_course is not None:
            from .models import Course
            c_obj = target_course if isinstance(target_course, Course) else Course.objects.filter(id=target_course).first()
            if not c_obj:
                return Q(pk__in=[])
            exam_ids = get_course_exam_ids(c_obj)
            q = Q(course=c_obj)
            if exam_ids:
                q |= Q(course__isnull=True, exam_id__in=exam_ids)
            return q
        return Q()

    auth_courses = authorized_courses(user)
    if not auth_courses.exists():
        # Course-less published/live exams are platform-wide exams that remain
        # visible to students without a course enrollment. Course-scoped exams
        # continue to respect enrollment rules.
        return Q(status__in=['published', 'live'], course__isnull=True)

    if target_course is not None:
        from .models import Course
        c_id = target_course.id if isinstance(target_course, Course) else target_course
        c_obj = auth_courses.filter(id=c_id).first()
        if not c_obj:
            # Requested course is NOT authorized for this student -> strict denial
            return None
        exam_ids = get_course_exam_ids(c_obj)
        q = Q(course=c_obj)
        if exam_ids:
            q |= Q(course__isnull=True, exam_id__in=exam_ids)
        return q

    # No specific target course requested: student sees exams for ALL their authorized courses
    auth_course_ids = list(auth_courses.values_list('id', flat=True))
    auth_exam_scope = authorized_exam_ids(user) or set()
    q = Q(course_id__in=auth_course_ids)
    q |= Q(course__isnull=True, status__in=['published', 'live'])
    if auth_exam_scope:
        q |= Q(course__isnull=True, exam_id__in=auth_exam_scope)
    return q


def is_examination_authorized_for_student(user, examination):
    """
    Determines if student `user` is authorized to access `examination` (detail, start, attempt, result).
    Returns True/False.
    """
    if not user or not user.is_authenticated:
        return False
    if user.role in STAFF_ROLES:
        return True
    if user.role != 'student':
        return False

    auth_courses = authorized_courses(user)
    if not auth_courses.exists():
        # Global, course-less published/live exams are open to the student base.
        return bool(examination.status in ('published', 'live') and examination.course_id is None)

    # If exam is explicitly tied to a course, user must be enrolled/authorized in that course
    if examination.course_id:
        return auth_courses.filter(id=examination.course_id).exists()

    # If exam is not explicitly tied to a course, check exam taxonomy scope
    if examination.exam_id:
        scope = authorized_exam_ids(user)
        return bool(scope and examination.exam_id in scope)

    # Exam has neither course nor exam taxonomy - unauthorized
    return False

