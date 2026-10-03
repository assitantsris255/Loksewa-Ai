from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from administration.permissions import IsAdminUser
from django.db.models import Q, ProtectedError
from exams.models import ExamCategory, Exam, Paper, Subject, Chapter, Topic, Question, Examination
from notes.models import StudyMaterial
from .syllabus_serializers import (
    ExamCategorySerializer, ExamSerializer, PaperSerializer, SubjectSerializer, 
    ChapterSerializer, TopicSerializer, ReorderSerializer
)
from .safe_delete_service import SafeDeleteService

def get_node_dependencies(instance):
    counts = {
        'notes': 0,
        'questions': 0,
        'exams': 0,
        'children': 0,
    }
    model_name = instance.__class__.__name__

    if isinstance(instance, ExamCategory):
        counts['children'] = instance.exams.count()
        counts['notes'] = StudyMaterial.objects.filter(exam__category=instance).count()
        counts['questions'] = Question.objects.filter(topic__chapter__subject__paper__exam__category=instance).count()
        counts['exams'] = Examination.objects.filter(category=instance).count()
    elif isinstance(instance, Exam):
        counts['children'] = instance.children.count() + instance.papers.count()
        counts['notes'] = StudyMaterial.objects.filter(exam=instance).count()
        counts['questions'] = Question.objects.filter(topic__chapter__subject__paper__exam=instance).count()
        counts['exams'] = Examination.objects.filter(exam=instance).count()
    elif isinstance(instance, Paper):
        counts['children'] = instance.subjects.count()
        counts['notes'] = StudyMaterial.objects.filter(subject__paper=instance).count()
        counts['questions'] = Question.objects.filter(topic__chapter__subject__paper=instance).count()
        counts['exams'] = Examination.objects.filter(subject__paper=instance).count()
    elif isinstance(instance, Subject):
        counts['children'] = instance.chapters.count()
        counts['notes'] = StudyMaterial.objects.filter(
            Q(subject=instance) | Q(chapter__subject=instance) | Q(topic__chapter__subject=instance)
        ).distinct().count()
        counts['questions'] = Question.objects.filter(topic__chapter__subject=instance).count()
        counts['exams'] = Examination.objects.filter(
            Q(subject=instance) | Q(questions__topic__chapter__subject=instance)
        ).distinct().count()
    elif isinstance(instance, Chapter):
        counts['children'] = instance.topics.count()
        counts['notes'] = StudyMaterial.objects.filter(
            Q(chapter=instance) | Q(topic__chapter=instance)
        ).distinct().count()
        counts['questions'] = Question.objects.filter(topic__chapter=instance).count()
        counts['exams'] = Examination.objects.filter(questions__topic__chapter=instance).distinct().count()
    elif isinstance(instance, Topic):
        counts['children'] = 0
        counts['notes'] = StudyMaterial.objects.filter(topic=instance).count()
        counts['questions'] = Question.objects.filter(topic=instance).count()
        counts['exams'] = Examination.objects.filter(questions__topic=instance).distinct().count()

    total_dependents = counts['notes'] + counts['questions'] + counts['exams'] + counts['children']
    has_dependencies = total_dependents > 0
    name = getattr(instance, 'name', getattr(instance, 'title', str(instance)))
    
    parts = []
    if counts['notes']:
        parts.append(f"{counts['notes']} notes")
    if counts['questions']:
        parts.append(f"{counts['questions']} questions")
    if counts['exams']:
        parts.append(f"{counts['exams']} exams")
    if counts['children']:
        parts.append(f"{counts['children']} child items")

    if parts:
        message = f"This {model_name.lower()} '{name}' is currently used by: {', '.join(parts)}. Deleting it may affect existing content."
    else:
        message = f"This {model_name.lower()} has no dependent content."

    return {
        'model': model_name,
        'id': instance.id,
        'name': name,
        'has_dependencies': has_dependencies,
        'counts': counts,
        'message': message,
        'is_active': getattr(instance, 'is_active', True),
    }

class BaseSyllabusViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminUser]

    @action(detail=False, methods=['patch'])
    def reorder(self, request):
        serializer = ReorderSerializer(data=request.data, many=True)
        if serializer.is_valid():
            objects_to_update = []
            for item in serializer.validated_data:
                obj = self.get_queryset().model.objects.get(id=item['id'])
                obj.order = item['order']
                objects_to_update.append(obj)
            
            self.get_queryset().model.objects.bulk_update(objects_to_update, ['order'])
            return Response({'status': 'reordered'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def dependencies(self, request, pk=None):
        instance = self.get_object()
        return Response(get_node_dependencies(instance))

    @action(detail=True, methods=['patch', 'post'])
    def archive(self, request, pk=None):
        instance = self.get_object()
        new_active = request.data.get('is_active')
        if new_active is None:
            instance.is_active = not instance.is_active
        else:
            instance.is_active = bool(new_active)
        if hasattr(instance, 'status'):
            instance.status = 'active' if instance.is_active else 'inactive'
        instance.save()
        return Response({
            'id': instance.id,
            'is_active': instance.is_active,
            'status': getattr(instance, 'status', 'active' if instance.is_active else 'inactive'),
            'message': f"{instance} is now {'active' if instance.is_active else 'archived'}."
        })

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if request.query_params.get('force') == 'true':
            deps = get_node_dependencies(instance)
            return Response({
                'error': 'Deletion of master academic records is disabled.',
                'detail': 'Direct force deletion of syllabus records is blocked to protect shared academic data. Use safe archiving or Trash.',
                'dependencies': deps,
            }, status=status.HTTP_409_CONFLICT)
        reason = request.data.get('reason', '') if isinstance(request.data, dict) else ''
        trash_item = SafeDeleteService.soft_delete(instance, request.user, reason=reason)
        return Response({
            'success': True,
            'message': f"{trash_item.item_type} '{trash_item.title}' has been moved to Trash.",
            'trash_item_id': trash_item.id,
            'can_restore': True,
        }, status=status.HTTP_200_OK)

class ExamCategoryViewSet(BaseSyllabusViewSet):
    queryset = ExamCategory.objects.all().order_by('order', 'id')
    serializer_class = ExamCategorySerializer

class ExamViewSet(BaseSyllabusViewSet):
    serializer_class = ExamSerializer
    
    def get_queryset(self):
        queryset = Exam.objects.all().order_by('order', 'id')
        category_id = self.request.query_params.get('category', None)
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        return queryset

class PaperViewSet(BaseSyllabusViewSet):
    serializer_class = PaperSerializer
    
    def get_queryset(self):
        queryset = Paper.objects.all().order_by('order', 'id')
        exam_id = self.request.query_params.get('exam', None)
        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)
        return queryset

class SubjectViewSet(BaseSyllabusViewSet):
    serializer_class = SubjectSerializer
    
    def get_queryset(self):
        queryset = Subject.objects.all().order_by('order', 'id')
        paper_id = self.request.query_params.get('paper', None)
        if paper_id:
            queryset = queryset.filter(paper_id=paper_id)
        # A Subject belongs to an Exam through its Paper. The UI calls an Exam a
        # "Position", so allow narrowing straight to one without picking a Paper.
        exam_id = self.request.query_params.get('exam', None)
        if exam_id:
            queryset = queryset.filter(paper__exam_id=exam_id)
        return queryset

class ChapterViewSet(BaseSyllabusViewSet):
    serializer_class = ChapterSerializer
    
    def get_queryset(self):
        queryset = Chapter.objects.all().order_by('order', 'id')
        subject_id = self.request.query_params.get('subject', None)
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        return queryset

class TopicViewSet(BaseSyllabusViewSet):
    serializer_class = TopicSerializer
    
    def get_queryset(self):
        queryset = Topic.objects.all().order_by('order', 'id')
        chapter_id = self.request.query_params.get('chapter', None)
        if chapter_id:
            queryset = queryset.filter(chapter_id=chapter_id)
        return queryset

from rest_framework.views import APIView

class SyllabusTreeView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        categories = ExamCategory.objects.prefetch_related(
            'exams__children__children__papers__subjects__chapters__topics',
            'exams__papers__subjects__chapters__topics',
        ).order_by('order', 'id')

        # Chaining .order_by()/.filter() onto an already-prefetched relation
        # manager (e.g. `paper.subjects.all().order_by(...)`) builds a brand
        # new queryset that bypasses prefetch_related's cache entirely,
        # silently turning this back into an N+1 - one query per subject,
        # chapter, topic, exam and paper. Sorting/filtering the already-cached
        # list in Python instead reads from that cache, keeping the whole
        # tree at the handful of queries the prefetch_related above set up.
        def _sorted(items):
            return sorted(items, key=lambda o: (o.order, o.id))

        def build_paper(paper):
            paper_data = {
                'id': paper.id,
                'name': paper.name,
                'is_active': paper.is_active,
                'subjects': [],
            }
            for sub in _sorted(paper.subjects.all()):
                sub_data = {
                    'id': sub.id,
                    'name': sub.name,
                    'is_active': sub.is_active,
                    'chapters': [],
                }
                for chap in _sorted(sub.chapters.all()):
                    chap_data = {
                        'id': chap.id,
                        'name': chap.title,
                        'is_active': chap.is_active,
                        'topics': [
                            {'id': topic.id, 'name': topic.name, 'is_active': topic.is_active}
                            for topic in _sorted(chap.topics.all())
                        ],
                    }
                    sub_data['chapters'].append(chap_data)
                paper_data['subjects'].append(sub_data)
            return paper_data

        # Exam is self-nesting (see exams.models.Exam): a "Level" (4th/5th/7th
        # Level) is a parent-less Exam row, and its child Exam rows are the
        # "Preparation/Service" underneath it (e.g. Civil Engineering). Build
        # that nesting recursively instead of flattening every Exam row in
        # the category onto one list, which mixed Levels and Services
        # together as siblings.
        def build_exam(exam):
            return {
                'id': exam.id,
                'name': exam.name,
                'status': exam.status,
                'is_active': exam.is_active,
                'category_id': exam.category_id,
                'children': [
                    build_exam(child) for child in _sorted(exam.children.all())
                ],
                'papers': [
                    build_paper(paper) for paper in _sorted(exam.papers.all())
                ],
            }

        tree_data = []
        for cat in categories:
            cat_data = {
                'id': cat.id,
                'name': cat.name,
                'is_active': cat.is_active,
                'positions': [
                    build_exam(exam)
                    for exam in _sorted(cat.exams.all())
                    if exam.parent_id is None
                ],
            }
            tree_data.append(cat_data)

        return Response(tree_data)

class SyllabusStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        return Response({
            'categories': ExamCategory.objects.count(),
            'exams': Exam.objects.count(),
            'papers': Paper.objects.count(),
            'subjects': Subject.objects.count(),
            'chapters': Chapter.objects.count(),
            'topics': Topic.objects.count()
        })
