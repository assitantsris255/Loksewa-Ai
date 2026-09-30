from rest_framework import serializers
from django.utils import timezone
from .models import ExamSchedule, Examination, ExamCategory, Exam

class AdminExamScheduleSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='exam_category.name', read_only=True)
    exam_name = serializers.CharField(source='exam.name', read_only=True)
    is_upcoming = serializers.SerializerMethodField()

    class Meta:
        model = ExamSchedule
        fields = [
            'id', 'title', 'exam_type', 'exam_category', 'category_name',
            'exam', 'exam_name', 'description', 'exam_date',
            'exam_time', 'exam_datetime', 'timezone',
            'application_deadline', 'result_expected_date',
            'official_notice_url', 'is_published', 'is_active',
            'is_upcoming', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'exam_datetime', 'created_at', 'updated_at']

    def get_is_upcoming(self, obj):
        if not obj.exam_date:
            return False
        return obj.exam_date >= timezone.now().date()

    def validate(self, attrs):
        exam_date = attrs.get('exam_date', getattr(self.instance, 'exam_date', None))
        is_active = attrs.get('is_active', getattr(self.instance, 'is_active', False))
        
        if not exam_date:
            raise serializers.ValidationError({"exam_date": "Exam date is required."})

        # Prevent past schedules from being marked active as upcoming
        if is_active and exam_date < timezone.now().date():
            raise serializers.ValidationError({
                "exam_date": "Cannot set a past date schedule as the active upcoming exam."
            })

        return attrs


class StudentExamScheduleSerializer(serializers.ModelSerializer):
    """
    Clean, minimal, public/student-facing serializer for the Next Official Loksewa Exam.
    """
    category_name = serializers.CharField(source='exam_category.name', read_only=True)
    exam_name = serializers.CharField(source='exam.name', read_only=True)
    server_time = serializers.SerializerMethodField()

    class Meta:
        model = ExamSchedule
        fields = [
            'id', 'title', 'exam_type', 'exam_category', 'category_name',
            'exam', 'exam_name', 'description', 'exam_date',
            'exam_time', 'exam_datetime', 'timezone',
            'application_deadline', 'result_expected_date',
            'official_notice_url', 'server_time'
        ]

    def get_server_time(self, obj):
        return timezone.now().isoformat()


class StudentUpcomingMockExamSerializer(serializers.ModelSerializer):
    """
    Serializer for next published mock examination eligible for the student.
    """
    category_name = serializers.CharField(source='category.name', read_only=True)
    exam_name = serializers.CharField(source='exam.name', read_only=True)
    status = serializers.CharField(source='computed_status', read_only=True)
    duration_minutes = serializers.IntegerField(source='time_limit', read_only=True)
    server_time = serializers.SerializerMethodField()
    can_start = serializers.SerializerMethodField()
    active_attempt_id = serializers.SerializerMethodField()

    has_attempted = serializers.SerializerMethodField()

    class Meta:
        model = Examination
        fields = [
            'id', 'title', 'description', 'exam_type',
            'category_name', 'exam_name', 'start_time',
            'end_time', 'duration_minutes', 'total_questions',
            'total_marks', 'status', 'can_start',
            'active_attempt_id', 'has_attempted', 'server_time'
        ]

    def _user(self):
        request = self.context.get('request')
        return getattr(request, 'user', None)

    def get_server_time(self, obj):
        return timezone.now().isoformat()

    def get_has_attempted(self, obj):
        user = self._user()
        if not user or not user.is_authenticated:
            return False
        return obj.attempts.filter(student=user).exclude(status='in-progress').exists()

    def get_can_start(self, obj):
        user = self._user()
        if not user or not user.is_authenticated:
            return False
        if obj.computed_status != 'LIVE':
            return False
        if self.get_has_attempted(obj):
            return False
        return True

    def get_active_attempt_id(self, obj):
        user = self._user()
        if not user or not user.is_authenticated:
            return None
        active = obj.attempts.filter(student=user, status='in-progress').first()
        return active.id if active else None

