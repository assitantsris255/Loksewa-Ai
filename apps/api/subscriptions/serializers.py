from django.utils import timezone
from rest_framework import serializers
from .models import SubscriptionPlan, Subscription, SubscriptionPayment, Invoice
from core.models import Notification
from marketplace.serializers import PaymentMethodSerializer
from core.models import User

# No existing product rule defines "expiring soon" - this is the simple,
# documented default the spec allows in the absence of one.
EXPIRING_SOON_THRESHOLD_DAYS = 7

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    eligible_courses_details = serializers.SerializerMethodField(read_only=True)
    course_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = '__all__'

    def _format_course_detail(self, course):
        if not course:
            return None
        exam = course.exam
        exam_name = exam.name if exam else None
        level_name = exam.parent.name if (exam and exam.parent) else (exam_name if exam_name and 'level' in exam_name.lower() else None)
        category_name = exam.category.name if (exam and exam.category) else None

        parts = []
        if category_name:
            parts.append(category_name)
        if level_name:
            parts.append(level_name)
        if exam_name and exam_name not in parts:
            parts.append(exam_name)
        elif course.title and course.title not in parts:
            parts.append(course.title)
        hierarchy_path = " › ".join(parts) if parts else course.title

        return {
            "id": course.id,
            "title": course.title,
            "exam": exam_name,
            "level": level_name,
            "category": category_name,
            "service": exam_name if exam and exam.parent else None,
            "hierarchy_path": hierarchy_path,
            "status": course.status,
            "is_coming_soon": course.status == 'coming_soon',
        }

    def get_eligible_courses_details(self, obj):
        return [
            self._format_course_detail(c)
            for c in obj.eligible_courses.all()
        ]

    def get_course_details(self, obj):
        if not obj.course:
            return None
        c = obj.course
        if hasattr(c, 'exam') and c.exam and hasattr(c.exam, 'category'):
            return self._format_course_detail(c)
        from courses.models import Course
        c_full = Course.objects.select_related('exam', 'exam__parent', 'exam__category').filter(id=obj.course_id).first()
        return self._format_course_detail(c_full)

    def validate(self, data):
        if (
            self.instance
            and self.instance.status == 'ARCHIVED'
            and data.get('status') not in (None, 'ARCHIVED')
        ):
            raise serializers.ValidationError({
                'status': 'Archived packages cannot be republished.'
            })

        package_type = data.get('package_type', getattr(self.instance, 'package_type', 'SINGLE'))
        course = data.get('course', getattr(self.instance, 'course', None))
        eligible_courses = data.get('eligible_courses')

        selected_courses = []
        if 'course' in data and data['course']:
            selected_courses.append(data['course'])
        if 'eligible_courses' in data:
            selected_courses.extend(data['eligible_courses'])
        for selected_course in {item.pk: item for item in selected_courses}.values():
            exam = selected_course.exam
            if selected_course.status != 'published' or not exam:
                raise serializers.ValidationError({
                    'eligible_courses': 'Packages can only grant access to published Courses linked to the active academic hierarchy.'
                })
            node = exam
            while node:
                if node.status != 'active' or not node.category.is_active:
                    raise serializers.ValidationError({
                        'eligible_courses': 'Coming Soon or inactive academic nodes cannot be included in packages.'
                    })
                node = node.parent

        if package_type == 'SINGLE':
            # Sync course and eligible_courses if either is provided
            if not course and eligible_courses and len(eligible_courses) == 1:
                data['course'] = eligible_courses[0]
            elif course and (eligible_courses is None or len(eligible_courses) == 0):
                data['eligible_courses'] = [course]
        elif package_type in ('MULTI', 'BUNDLE'):
            if eligible_courses is not None and len(eligible_courses) == 0:
                raise serializers.ValidationError({"eligible_courses": f"Please select at least one eligible preparation for {package_type} packages."})
            if package_type == 'MULTI':
                allowed = data.get('allowed_preparation_count', getattr(self.instance, 'allowed_preparation_count', 1))
                if allowed < 1:
                    raise serializers.ValidationError({"allowed_preparation_count": "Allowed preparations must be at least 1."})
        elif package_type == 'ALL_ACCESS':
            data['course'] = None
            data['eligible_courses'] = []

        return data


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_details = SubscriptionPlanSerializer(source='plan', read_only=True)
    remaining_days = serializers.SerializerMethodField()
    computed_status = serializers.SerializerMethodField()
    authorized_courses = serializers.SerializerMethodField()
    granted_by_username = serializers.CharField(source='granted_by.username', read_only=True, default=None)
    access_source = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = '__all__'
        read_only_fields = ('student', 'status', 'start_date', 'expiry_date')

    def get_access_source(self, obj):
        return "Admin Granted" if obj.source == 'ADMIN_GRANT' else "Student Payment"

    def get_authorized_courses(self, obj):
        from courses.models import Enrollment
        enrollments = Enrollment.objects.filter(student=obj.student, status='active').select_related('course', 'course__exam')
        return [
            {
                "id": e.course.id,
                "title": e.course.title,
                "exam": e.course.exam.name if e.course.exam else None,
            }
            for e in enrollments
        ]

    def get_remaining_days(self, obj):
        """Derived from expiry_date, never stored - stays correct without a
        background job having to decrement anything."""
        if obj.status != 'ACTIVE':
            return 0
        delta = obj.expiry_date - timezone.now()
        return max(delta.days, 0)

    def get_computed_status(self, obj):
        if obj.status != 'ACTIVE':
            return obj.status
        if obj.expiry_date <= timezone.now():
            return 'EXPIRED'
        if (obj.expiry_date - timezone.now()).days <= EXPIRING_SOON_THRESHOLD_DAYS:
            return 'EXPIRING_SOON'
        return 'ACTIVE'

class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    plan_details = SubscriptionPlanSerializer(source='plan', read_only=True)
    payment_method_details = PaymentMethodSerializer(source='payment_method', read_only=True)
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    selected_courses = serializers.SerializerMethodField()
    
    class Meta:
        model = SubscriptionPayment
        fields = '__all__'
        read_only_fields = ('student', 'amount', 'status', 'rejection_reason', 'verified_at', 'verified_by')

    def get_selected_courses(self, obj):
        apps = list(obj.course_applications.select_related('course', 'course__exam'))
        res = [
            {
                "id": app.course.id,
                "title": app.course.title,
                "exam": app.course.exam.name if app.course.exam else None
            }
            for app in apps
        ]
        if not res and obj.plan and obj.plan.course:
            res.append({
                "id": obj.plan.course.id,
                "title": obj.plan.course.title,
                "exam": obj.plan.course.exam.name if obj.plan.course.exam else None
            })
        return res

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ('student', 'type', 'title', 'message', 'related_id')

class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = '__all__'
