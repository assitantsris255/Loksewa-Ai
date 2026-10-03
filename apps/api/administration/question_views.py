from rest_framework import viewsets, filters, status
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.response import Response
from .permissions import IsAdminUser
from django.db.models import Count, F
from exams.models import Question
from rest_framework.pagination import PageNumberPagination
from .question_serializers import AdminQuestionSerializer
from .safe_delete_service import SafeDeleteService


class QuestionBankPagination(PageNumberPagination):
    # A data table, not cards - a bigger default page than the platform's
    # standard card-grid pagination reads better here. max_page_size is high
    # because QuestionSelector.tsx relies on `page_size=500` to pull an
    # entire syllabus-scoped pool for its random-draw mode, not a UI page.
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 1000

class AdminQuestionViewSet(viewsets.ModelViewSet):
    # Performance: without these, every row in the list triggers its own
    # round trip - Question.usage_count alone ran 2 COUNT queries per row,
    # and the serializer's collections/tags fields each ran another. For a
    # 100-row page that was 400+ extra queries. Annotating usage_count and
    # prefetching the M2M relations collapses all of that into a handful of
    # queries total, independent of how many rows are returned.
    # .distinct() guards against duplicate rows once tag_objects/collections
    # (both M2M) are joined into search/filter - without it, a question that
    # matches on two tags would otherwise appear twice in the list.
    queryset = Question.objects.select_related(
        'subject', 'chapter', 'topic',
        'chapter__subject', 'topic__chapter', 'topic__chapter__subject',
        'topic__chapter__subject__paper', 'topic__chapter__subject__paper__exam',
        'topic__chapter__subject__paper__exam__category',
    ).prefetch_related('collections', 'tag_objects').annotate(
        question_sets_count=Count('question_sets', distinct=True),
        examinations_count=Count('examinations_set', distinct=True),
    ).annotate(
        usage_count_computed=F('question_sets_count') + F('examinations_count'),
    ).order_by('-created_at').distinct()
    serializer_class = AdminQuestionSerializer
    permission_classes = [IsAdminUser]
    pagination_class = QuestionBankPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    # Enable filtering by syllabus hierarchy, collections and tags.
    filterset_fields = {
        'question_type': ['exact'],
        'status': ['exact'],
        'ai_status': ['exact'],
        'difficulty': ['exact'],
        'subject': ['exact'],
        'chapter': ['exact'],
        'topic': ['exact'],
        'collections': ['exact'],
        'tag_objects': ['exact'],
        'topic__chapter': ['exact'],
        'topic__chapter__subject': ['exact'],
        'topic__chapter__subject__paper': ['exact'],
        'topic__chapter__subject__paper__exam': ['exact'],
        'topic__chapter__subject__paper__exam__category': ['exact'],
    }
    # Tags, Collection name, and the syllabus hierarchy are all searchable
    # alongside question text, so e.g. searching "PYQ" or "Constitution"
    # finds questions tagged that way even if the text doesn't mention it.
    search_fields = [
        'text', 'explanation', 'model_answer', 'tags',
        'tag_objects__name', 'collections__name',
        'topic__name', 'topic__chapter__title', 'topic__chapter__subject__name',
    ]
    ordering_fields = ['created_at', 'marks', 'difficulty']

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        reason = request.data.get('reason', '') if isinstance(request.data, dict) else ''
        trash_item = SafeDeleteService.soft_delete(instance, request.user, reason=reason)
        return Response({
            'success': True,
            'message': f"Question '{trash_item.title}' has been moved to Trash.",
            'trash_item_id': trash_item.id,
        }, status=status.HTTP_200_OK)

    def get_queryset(self):
        # Multi-tag filter: matches ANY of the selected tags, per the product
        # convention documented on the frontend Tag filter dropdown.
        # Implemented manually (django-filter's auto-generated `in` lookup for
        # a ManyToMany field errors on valid CSV input - a library gotcha,
        # not a data problem) rather than via filterset_fields.
        qs = super().get_queryset()
        raw_ids = self.request.query_params.get('tag_objects__in')
        if raw_ids:
            tag_ids = [int(v) for v in raw_ids.split(',') if v.strip().isdigit()]
            if tag_ids:
                qs = qs.filter(tag_objects__id__in=tag_ids).distinct()

        # Authoritative mapping filter: all | mapped | needs_mapping | incomplete | unassigned | invalid
        mapping = self.request.query_params.get('mapping')
        if mapping:
            from courses.services.course_access_service import CourseAccessService
            qs = CourseAccessService.filter_admin_questions_by_mapping(qs, mapping)

        course_param = self.request.query_params.get('course')
        if course_param:
            from courses.models import Course
            from courses.services.course_access_service import CourseAccessService
            c_obj = Course.objects.filter(id=course_param).first()
            if c_obj:
                c_exam_ids = list(CourseAccessService.get_course_exam_ids(c_obj))
                qs = qs.filter(
                    Q(exam_id__in=c_exam_ids) |
                    Q(subject__paper__exam_id__in=c_exam_ids) |
                    Q(chapter__subject__paper__exam_id__in=c_exam_ids) |
                    Q(topic__chapter__subject__paper__exam_id__in=c_exam_ids)
                )

        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Return summary statistics for the question bank.
        """
        qs = self.get_queryset()
        
        total = qs.count()
        mcq_count = qs.filter(question_type='mcq').count()
        subjective_count = qs.filter(question_type='subjective').count()
        active_count = qs.filter(status__in=['approved', 'pending_review']).count()
        draft_count = qs.filter(status='draft').count()
        ai_pending_count = qs.filter(ai_status='pending').count()
        
        # Mapping breakdown
        from courses.services.course_access_service import CourseAccessService
        mapped_count = CourseAccessService.filter_admin_questions_by_mapping(qs, 'mapped').count()
        needs_mapping_count = CourseAccessService.filter_admin_questions_by_mapping(qs, 'needs_mapping').count()
        incomplete_count = CourseAccessService.filter_admin_questions_by_mapping(qs, 'incomplete').count()
        unassigned_count = CourseAccessService.filter_admin_questions_by_mapping(qs, 'unassigned').count()
        invalid_count = CourseAccessService.filter_admin_questions_by_mapping(qs, 'invalid').count()

        # Difficulty breakdown
        difficulty_counts = list(qs.values('difficulty').annotate(count=Count('id')))
        
        return Response({
            'total': total,
            'mcq': mcq_count,
            'subjective': subjective_count,
            'active': active_count,
            'draft': draft_count,
            'ai_pending': ai_pending_count,
            'mapped': mapped_count,
            'needs_mapping': needs_mapping_count,
            'incomplete': incomplete_count,
            'unassigned': unassigned_count,
            'invalid': invalid_count,
            'by_difficulty': difficulty_counts
        })

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """
        Duplicate a question. The duplicate will be placed in 'draft' status.
        """
        question = self.get_object()
        
        # Create a copy
        question.pk = None
        question.question_id = "" # Will be auto-generated on save
        question.status = 'draft'
        question.text = f"[COPY] {question.text}"
        question.save()
        
        from administration.models import AuditLog
        AuditLog.objects.create(
            actor=request.user, action='DUPLICATE_QUESTION', entity_type='Question', entity_id=question.question_id,
            details={"original_pk": pk, "new_pk": question.pk}
        )
        
        serializer = self.get_serializer(question)
        return Response(serializer.data, status=201)

    @action(detail=True, methods=['get'])
    def usage(self, request, pk=None):
        """Returns how many sets/exams reference this question."""
        question = self.get_object()
        return Response({"usage_count": question.usage_count})

    @action(detail=False, methods=['post'])
    def bulk_action(self, request):
        """
        Perform a bulk action on a list of question IDs.
        Payload: { action: 'approve'|'draft'|'archive'|'delete'|'add_to_collection'|'remove_from_collection'|'add_tags'|'remove_tags', ids: [1, 2, 3], collection_ids: [1,2], tag_ids: [1,2] }
        """
        action_type = request.data.get('action')
        ids = request.data.get('ids', [])

        if not action_type or not ids:
            return Response({"error": "action and ids are required"}, status=400)

        questions = Question.objects.filter(id__in=ids)
        count = questions.count()

        from administration.models import AuditLog

        if action_type == 'delete':
            # Check usage before bulk delete
            for q in questions:
                if q.usage_count > 0:
                    return Response({"error": f"Cannot delete Question {q.question_id} because it is referenced in an exam or set."}, status=400)
            questions.delete()
            AuditLog.objects.create(
                actor=request.user, action='BULK_DELETE', entity_type='Question', entity_id=None,
                details={"ids": ids, "count": count}
            )
        elif action_type in ['approve', 'draft', 'archive']:
            if action_type == 'approve':
                for q in questions:
                    if q.created_by == request.user:
                        return Response({"error": "You cannot approve your own question."}, status=403)

            status_map = {'approve': 'approved', 'draft': 'draft', 'archive': 'archived'}
            new_status = status_map[action_type]
            questions.update(status=new_status)
            AuditLog.objects.create(
                actor=request.user, action=f'BULK_{action_type.upper()}', entity_type='Question', entity_id=None,
                details={"ids": ids, "count": count, "new_status": new_status}
            )
        elif action_type in ['add_to_collection', 'remove_from_collection']:
            collection_ids = request.data.get('collection_ids', [])
            if not collection_ids:
                return Response({"error": "collection_ids required for this action"}, status=400)
            
            from exams.models import QuestionCollection
            collections = QuestionCollection.objects.filter(id__in=collection_ids)
            
            for q in questions:
                if action_type == 'add_to_collection':
                    q.collections.add(*collections)
                else:
                    q.collections.remove(*collections)
            
            AuditLog.objects.create(
                actor=request.user, action=f'BULK_{action_type.upper()}', entity_type='Question', entity_id=None,
                details={"ids": ids, "count": count, "collection_ids": collection_ids}
            )
        elif action_type in ['add_tags', 'remove_tags']:
            tag_ids = request.data.get('tag_ids', [])
            if not tag_ids:
                return Response({"error": "tag_ids required for this action"}, status=400)

            from core.models import Tag
            tag_qs = Tag.objects.filter(id__in=tag_ids)

            for q in questions:
                if action_type == 'add_tags':
                    q.tag_objects.add(*tag_qs)
                else:
                    q.tag_objects.remove(*tag_qs)

            AuditLog.objects.create(
                actor=request.user, action=f'BULK_{action_type.upper()}', entity_type='Question', entity_id=None,
                details={"ids": ids, "count": count, "tag_ids": tag_ids}
            )
        elif action_type == 'map_academic':
            from courses.models import Course
            from exams.models import Exam, Subject, Chapter, Topic
            from courses.services.course_access_service import CourseAccessService
            from django.db import transaction

            course_id = request.data.get('course_id')
            exam_id = request.data.get('exam_id')
            subject_id = request.data.get('subject_id')
            chapter_id = request.data.get('chapter_id')
            topic_id = request.data.get('topic_id')

            course = None
            if course_id:
                course = Course.objects.filter(id=course_id).first()
                if not course:
                    return Response({"error": "Selected course does not exist."}, status=400)
                if not exam_id and course.exam_id:
                    exam_id = course.exam_id

            exam = None
            if exam_id:
                exam = Exam.objects.filter(id=exam_id).first()
                if not exam:
                    return Response({"error": "Selected level/position does not exist."}, status=400)

            if course and exam:
                course_exam_ids = CourseAccessService.get_course_exam_ids(course)
                if exam.id not in course_exam_ids:
                    return Response({"error": f"Level/Position '{exam.name}' does not belong to course '{course.title}'."}, status=400)

            subject = None
            if subject_id:
                subject = Subject.objects.filter(id=subject_id).select_related('paper__exam').first()
                if not subject:
                    return Response({"error": "Selected subject does not exist."}, status=400)
                if exam:
                    sub_exam_id = subject.paper.exam_id if (subject.paper_id and subject.paper) else None
                    if sub_exam_id != exam.id and getattr(subject.paper.exam, 'parent_id', None) != exam.id:
                        return Response({"error": f"Subject '{subject.name}' does not belong to level/position '{exam.name}'."}, status=400)

            chapter = None
            if chapter_id:
                chapter = Chapter.objects.filter(id=chapter_id).first()
                if not chapter:
                    return Response({"error": "Selected chapter does not exist."}, status=400)
                if subject and chapter.subject_id != subject.id:
                    return Response({"error": f"Chapter '{chapter.title}' does not belong to subject '{subject.name}'."}, status=400)

            topic = None
            if topic_id:
                topic = Topic.objects.filter(id=topic_id).first()
                if not topic:
                    return Response({"error": "Selected topic does not exist."}, status=400)
                if chapter and topic.chapter_id != chapter.id:
                    return Response({"error": f"Topic '{topic.name}' does not belong to chapter '{chapter.title}'."}, status=400)

            category_id = exam.category_id if exam else (exam.parent.category_id if (exam and exam.parent) else None)

            update_fields = {}
            if exam:
                update_fields['exam'] = exam
            if category_id:
                update_fields['category_id'] = category_id
            if subject_id is not None:
                update_fields['subject'] = subject
            if chapter_id is not None:
                update_fields['chapter'] = chapter
            if topic_id is not None:
                update_fields['topic'] = topic

            if not update_fields:
                return Response({"error": "No academic mapping provided to apply."}, status=400)

            with transaction.atomic():
                questions.update(**update_fields)

            AuditLog.objects.create(
                actor=request.user, action='BULK_MAP_ACADEMIC', entity_type='Question', entity_id=None,
                details={
                    "ids": ids,
                    "count": count,
                    "course_id": course_id,
                    "exam_id": exam_id,
                    "subject_id": subject_id,
                    "chapter_id": chapter_id,
                    "topic_id": topic_id,
                }
            )
            return Response({
                "success": True,
                "count": count,
                "message": f"Successfully mapped {count} questions to academic scope."
            })
        else:
            return Response({"error": "Invalid action"}, status=400)
            
        return Response({"success": True, "count": count})

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        Bulk create a list of questions.
        Payload: [ { question_type: 'mcq', text: '...', ... }, ... ]
        """
        questions_data = request.data
        if not isinstance(questions_data, list):
            return Response({"error": "Expected a list of questions"}, status=400)
            
        serializer = self.get_serializer(data=questions_data, many=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "count": len(serializer.data), "data": serializer.data}, status=201)
        return Response(serializer.errors, status=400)
