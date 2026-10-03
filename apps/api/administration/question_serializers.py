from rest_framework import serializers
from exams.models import Question, Topic, Subject, Chapter, ExamCategory, Exam, QuestionCollection
from core.models import Tag
from courses.models import Course
from courses.services.course_access_service import CourseAccessService

class AdminQuestionSerializer(serializers.ModelSerializer):
    course = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(), required=False, allow_null=True, write_only=True
    )
    subject = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all(), required=False, allow_null=True
    )
    chapter = serializers.PrimaryKeyRelatedField(
        queryset=Chapter.objects.all(), required=False, allow_null=True
    )
    topic = serializers.PrimaryKeyRelatedField(
        queryset=Topic.objects.all(), required=False, allow_null=True
    )
    category = serializers.PrimaryKeyRelatedField(
        queryset=ExamCategory.objects.all(), required=False, allow_null=True
    )
    position = serializers.PrimaryKeyRelatedField(
        queryset=Exam.objects.all(), required=False, allow_null=True, source='exam'
    )

    course_id = serializers.SerializerMethodField()
    course_title = serializers.SerializerMethodField()
    mapping_status = serializers.SerializerMethodField()
    mapping_status_display = serializers.SerializerMethodField()

    def get_course_id(self, obj):
        course = CourseAccessService.get_question_course(obj)
        return course.id if course else None

    def get_course_title(self, obj):
        course = CourseAccessService.get_question_course(obj)
        return course.title if course else None

    def get_mapping_status(self, obj):
        return CourseAccessService.get_question_mapping_status(obj)

    def get_mapping_status_display(self, obj):
        status_val = CourseAccessService.get_question_mapping_status(obj)
        displays = {
            'mapped': 'Mapped',
            'incomplete': 'Incomplete',
            'unassigned': 'Unassigned',
            'invalid': 'Invalid',
        }
        return displays.get(status_val, 'Unassigned')

    collections = serializers.SerializerMethodField()
    collection_ids = serializers.PrimaryKeyRelatedField(
        queryset=QuestionCollection.objects.all(), many=True, required=False,
        write_only=True, source='collections',
        help_text="Optional QuestionCollection IDs to add this question to.",
    )

    def get_collections(self, obj):
        return [{'id': c.id, 'name': c.name} for c in obj.collections.all()]

    tag_objects = serializers.SerializerMethodField()
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(), many=True, required=False,
        write_only=True, source='tag_objects',
        help_text="Optional Tag IDs (from Academic Management > Tags) for search/filtering.",
    )

    def get_tag_objects(self, obj):
        tags = sorted(obj.tag_objects.all(), key=lambda t: t.name)
        return [{'id': t.id, 'name': t.name, 'slug': t.slug, 'color': t.color, 'is_active': t.is_active} for t in tags]

    topic_name = serializers.SerializerMethodField()
    chapter_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    position_name = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    
    chapter_id = serializers.SerializerMethodField()
    subject_id = serializers.SerializerMethodField()
    position_id = serializers.SerializerMethodField()
    category_id = serializers.SerializerMethodField()
    
    usage_count = serializers.SerializerMethodField()

    def get_usage_count(self, obj):
        annotated = getattr(obj, 'usage_count_computed', None)
        return annotated if annotated is not None else obj.usage_count

    def get_topic_name(self, obj):
        try:
            return obj.topic.name if obj.topic else None
        except:
            return None

    def get_chapter_name(self, obj):
        try:
            if obj.chapter:
                return obj.chapter.title or obj.chapter.name
            if obj.topic and obj.topic.chapter:
                return obj.topic.chapter.title or obj.topic.chapter.name
            return None
        except:
            return None

    def get_subject_name(self, obj):
        try:
            if obj.subject:
                return obj.subject.name
            if obj.chapter and obj.chapter.subject:
                return obj.chapter.subject.name
            if obj.topic and obj.topic.chapter and obj.topic.chapter.subject:
                return obj.topic.chapter.subject.name
            return None
        except:
            return None

    def _question_exam(self, obj):
        try:
            if getattr(obj, 'exam_id', None) and obj.exam:
                return obj.exam
            subject = (
                obj.subject or
                (obj.chapter.subject if obj.chapter else None) or
                (obj.topic.chapter.subject if obj.topic and obj.topic.chapter else None)
            )
            if subject and subject.paper_id and subject.paper:
                return subject.paper.exam
            return None
        except Exception:
            return None

    def get_position_name(self, obj):
        try:
            if getattr(obj, 'exam_id', None) and obj.exam:
                return obj.exam.name
            exam = self._question_exam(obj)
            return exam.name if exam else None
        except:
            return None

    def get_category_name(self, obj):
        try:
            if getattr(obj, 'category_id', None) and obj.category:
                return obj.category.name
            if getattr(obj, 'exam_id', None) and obj.exam and obj.exam.category:
                return obj.exam.category.name
            exam = self._question_exam(obj)
            return exam.category.name if exam and exam.category_id else None
        except:
            return None

    def get_chapter_id(self, obj):
        try:
            if obj.chapter_id:
                return obj.chapter_id
            return obj.topic.chapter_id if obj.topic and obj.topic.chapter_id else None
        except:
            return None
            
    def get_subject_id(self, obj):
        try:
            if obj.subject_id:
                return obj.subject_id
            if obj.chapter and obj.chapter.subject_id:
                return obj.chapter.subject_id
            return obj.topic.chapter.subject_id if obj.topic and obj.topic.chapter and obj.topic.chapter.subject_id else None
        except:
            return None
            
    def get_position_id(self, obj):
        try:
            if getattr(obj, 'exam_id', None):
                return obj.exam_id
            exam = self._question_exam(obj)
            return exam.id if exam else None
        except:
            return None
            
    def get_category_id(self, obj):
        try:
            if getattr(obj, 'category_id', None):
                return obj.category_id
            if getattr(obj, 'exam_id', None) and obj.exam and obj.exam.category_id:
                return obj.exam.category_id
            exam = self._question_exam(obj)
            return exam.category_id if exam and exam.category_id else None
        except:
            return None
    
    class Meta:
        model = Question
        fields = [
            'id', 'question_id', 'question_type', 'status',
            'course', 'course_id', 'course_title', 'mapping_status', 'mapping_status_display',
            'subject', 'chapter', 'topic',
            'topic_name', 'chapter_name', 'subject_name', 'position_name', 'category_name', 
            'chapter_id', 'subject_id', 'position_id', 'category_id',
            'category', 'position',
            'text', 'option_a', 
            'option_b', 'option_c', 'option_d', 'correct_option', 'model_answer',
            'marks', 'negative_marks', 'expected_time_minutes', 'explanation', 'hint',
            'difficulty', 'tags', 'usage_count', 'created_at', 'updated_at',
            'collections', 'collection_ids', 'tag_objects', 'tag_ids',
        ]
        read_only_fields = ['question_id']

    def validate(self, data):
        """
        Validate question rules based on type and academic hierarchy.
        Subject is optional; Category and Position/Level are accepted and auto-inferred.
        Enforces strict course-level validity and rejects mismatched academic combinations.
        """
        # Academic hierarchy validation
        course = data.get('course')
        subject = data.get('subject') or (self.instance.subject if self.instance else None)
        chapter = data.get('chapter') if 'chapter' in data else (self.instance.chapter if self.instance else None)
        topic = data.get('topic') if 'topic' in data else (self.instance.topic if self.instance else None)
        position = data.get('exam') or (self.instance.exam if self.instance else None)
        category = data.get('category') or (self.instance.category if self.instance else None)

        # Course-level validation
        if course:
            course_exam_ids = CourseAccessService.get_course_exam_ids(course)
            if not course_exam_ids:
                raise serializers.ValidationError({
                    "course": f"Course '{course.title}' has no associated academic exams or levels."
                })
            
            # Default position to course exam if not explicitly provided
            if not position and course.exam:
                position = course.exam
                data['exam'] = position
                if not category and course.exam.category:
                    category = course.exam.category
                    data['category'] = category

            if position and position.id not in course_exam_ids:
                raise serializers.ValidationError({
                    "position": f"Selected level/position '{position.name}' does not belong to course '{course.title}'."
                })

            if subject:
                sub_exam_id = subject.paper.exam_id if (subject.paper_id and subject.paper) else None
                if sub_exam_id and sub_exam_id not in course_exam_ids:
                    raise serializers.ValidationError({
                        "subject": f"Selected subject '{subject.name}' does not belong to course '{course.title}'."
                    })

        # Auto-infer parents from topic/chapter if needed
        if topic:
            if not chapter and topic.chapter:
                chapter = topic.chapter
                data['chapter'] = chapter
            if not subject and chapter and chapter.subject:
                subject = chapter.subject
                data['subject'] = subject

        if chapter and not subject and chapter.subject:
            subject = chapter.subject
            data['subject'] = subject

        if subject:
            if not position and subject.paper and subject.paper.exam:
                position = subject.paper.exam
                data['exam'] = position
            if not category and position and position.category:
                category = position.category
                data['category'] = category

        if position and not category and position.category:
            category = position.category
            data['category'] = category

        # 1. Topic must belong to Chapter if both are present
        if topic and chapter and topic.chapter_id != chapter.id:
            raise serializers.ValidationError({
                "topic": f"Topic '{topic.name}' does not belong to chapter '{chapter.title}'."
            })

        # 2. Chapter must belong to Subject if both are present
        if chapter and subject and chapter.subject_id != subject.id:
            raise serializers.ValidationError({
                "chapter": f"Chapter '{chapter.title}' does not belong to subject '{subject.name}'."
            })

        # 3. Subject must belong to Position/Level if position is provided
        if position and subject:
            subject_exam_id = subject.paper.exam_id if (subject.paper_id and subject.paper) else None
            is_valid_exam = (
                subject_exam_id == position.id or
                (subject.paper and subject.paper.exam and subject.paper.exam.parent_id == position.id)
            )
            if not is_valid_exam:
                raise serializers.ValidationError({
                    "subject": f"Subject '{subject.name}' does not belong to level/position '{position.name}'."
                })

        # 4. Position must belong to Category if category is provided
        if category and position:
            if position.category_id != category.id:
                raise serializers.ValidationError({
                    "position": f"Position/Level '{position.name}' does not belong to category '{category.name}'."
                })

        # 5. Validate that approved questions map to an active published course
        target_status = data.get('status') or (self.instance.status if self.instance else 'draft')
        if target_status == 'approved':
            resolved_exam_id = None
            if position:
                resolved_exam_id = position.id
            elif subject and getattr(subject, 'paper_id', None) and subject.paper:
                resolved_exam_id = subject.paper.exam_id
            elif chapter and chapter.subject and chapter.subject.paper:
                resolved_exam_id = chapter.subject.paper.exam_id
            elif topic and topic.chapter and topic.chapter.subject and topic.chapter.subject.paper:
                resolved_exam_id = topic.chapter.subject.paper.exam_id

            all_course_exam_ids = CourseAccessService.get_all_course_exam_ids()
            if not resolved_exam_id or resolved_exam_id not in all_course_exam_ids:
                raise serializers.ValidationError({
                    "course": "Approved questions intended for student practice must map to an active published course."
                })

        # Type-specific validation
        q_type = data.get('question_type') or (self.instance.question_type if self.instance else 'mcq')

        if q_type == 'mcq':
            if not data.get('option_a') or not data.get('option_b') or not data.get('option_c') or not data.get('option_d'):
                raise serializers.ValidationError("MCQ questions require all 4 options.")
            if not data.get('correct_option'):
                raise serializers.ValidationError("MCQ questions require a correct option.")
        elif q_type == 'true_false':
            if not data.get('correct_option'):
                raise serializers.ValidationError("True/False questions require a correct option (A or B).")
        elif q_type in ['subjective', 'short_answer', 'long_answer']:
            if not data.get('model_answer'):
                raise serializers.ValidationError("Subjective-type questions require a model answer.")

        return data
