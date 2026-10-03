from rest_framework import serializers
from .models import StudyMaterial, StudentMaterialProgress, StudentMaterialBookmark
from exams.models import Exam, Subject, Chapter, Topic
from django.db.models import Exists, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce


def with_student_state(queryset, user):
    """Annotate each material with the requesting student's bookmark and
    progress so the list serializer needs no per-row queries. Both values are
    scoped to `user`, so nothing about another student can leak in."""
    if not user or not user.is_authenticated:
        return queryset
    return queryset.annotate(
        _is_bookmarked=Exists(StudentMaterialBookmark.objects.filter(student=user, material=OuterRef('pk'))),
        _progress=Coalesce(Subquery(
            StudentMaterialProgress.objects.filter(student=user, material=OuterRef('pk')).values('progress')[:1],
            output_field=IntegerField()), Value(0)),
    )


class StudyMaterialListSerializer(serializers.ModelSerializer):
    exam_name = serializers.CharField(source='exam.name', read_only=True, default=None)
    parent_exam_name = serializers.CharField(source='exam.parent.name', read_only=True, default=None)
    category_name = serializers.CharField(source='exam.category.name', read_only=True, default=None)
    subject_name = serializers.CharField(source='subject.name', read_only=True, default=None)
    chapter_name = serializers.CharField(source='chapter.title', read_only=True, default=None)
    topic_name = serializers.CharField(source='topic.name', read_only=True, default=None)
    course_title = serializers.CharField(source='course.title', read_only=True, default=None)
    file = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    is_bookmarked = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = StudyMaterial
        fields = [
            'id', 'title', 'slug', 'description', 'material_type',
            'content_category', 'note_type',
            'access_type', 'status', 'is_downloadable', 'estimated_reading_time', 'updated_at', 'created_at',
            'exam', 'exam_name', 'parent_exam_name', 'category_name',
            'subject', 'subject_name',
            'chapter', 'chapter_name',
            'topic', 'topic_name',
            'course', 'course_title',
            'file', 'file_url',
            'is_bookmarked', 'progress'
        ]

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            download_path = f"/api/notes/materials/{obj.id}/download/"
            if request:
                return request.build_absolute_uri(download_path)
            return download_path
        return None

    def get_file(self, obj):
        return self.get_file_url(obj)

    def get_is_bookmarked(self, obj):
        if hasattr(obj, '_is_bookmarked'):
            return obj._is_bookmarked
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            return StudentMaterialBookmark.objects.filter(student=request.user, material=obj).exists()
        return False

    def get_progress(self, obj):
        if hasattr(obj, '_progress'):
            return obj._progress
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            prog = StudentMaterialProgress.objects.filter(student=request.user, material=obj).first()
            return prog.progress if prog else 0
        return 0


class StudyMaterialDetailSerializer(StudyMaterialListSerializer):
    class Meta(StudyMaterialListSerializer.Meta):
        fields = StudyMaterialListSerializer.Meta.fields + ['content', 'external_url', 'difficulty', 'review_note']


# ==========================================
# TEACHER / ADMIN WORKFLOW SERIALIZERS
# ==========================================

class TeacherStudyMaterialSerializer(serializers.ModelSerializer):
    exam_name = serializers.CharField(source='exam.name', read_only=True, default=None)
    subject_name = serializers.CharField(source='subject.name', read_only=True, default=None)
    chapter_name = serializers.CharField(source='chapter.title', read_only=True, default=None)
    topic_name = serializers.CharField(source='topic.name', read_only=True, default=None)
    author_name = serializers.CharField(source='teacher.get_full_name', read_only=True, default="Unknown")
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = StudyMaterial
        fields = [
            'id', 'title', 'slug', 'description', 'content', 'exam', 'subject', 'chapter', 'topic', 'course',
            'content_category', 'note_type',
            'material_type', 'difficulty', 'file', 'file_url', 'external_url', 'access_type', 'status', 'is_downloadable',
            'review_note', 'estimated_reading_time', 'created_at', 'updated_at',
            'exam_name', 'subject_name', 'chapter_name', 'topic_name', 'author_name'
        ]
        read_only_fields = ['status', 'review_note', 'slug']

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class AdminStudyMaterialSerializer(serializers.ModelSerializer):
    exam_name = serializers.CharField(source='exam.name', read_only=True, default=None)
    parent_exam_name = serializers.CharField(source='exam.parent.name', read_only=True, default=None)
    category_name = serializers.CharField(source='exam.category.name', read_only=True, default=None)
    subject_name = serializers.CharField(source='subject.name', read_only=True, default=None)
    chapter_name = serializers.CharField(source='chapter.title', read_only=True, default=None)
    topic_name = serializers.CharField(source='topic.name', read_only=True, default=None)
    author_name = serializers.CharField(source='teacher.get_full_name', read_only=True, default="Unknown")
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = StudyMaterial
        fields = [
            'id', 'title', 'slug', 'description', 'content', 'exam', 'subject', 'chapter', 'topic', 'course',
            'content_category', 'note_type',
            'material_type', 'difficulty', 'file', 'file_url', 'external_url', 'access_type', 'status',
            'review_note', 'estimated_reading_time', 'created_at', 'updated_at',
            'exam_name', 'parent_exam_name', 'category_name', 'subject_name', 'chapter_name', 'topic_name', 'author_name'
        ]

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None
