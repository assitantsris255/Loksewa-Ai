"""Question-selection endpoints for the Admin Exam Builder (Step 3).

Everything here reads from the canonical Master Question Bank (`Question`) and
writes through the canonical assignment model (`ExaminationQuestion`). Automated
selection always delegates to `QuestionSelectionService` — there is no second
selection algorithm.
"""
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response

from exams.models import Examination, ExaminationQuestion, Question
from exams.selection_service import QuestionSelectionService
from .models import AuditLog


class BankQuestionSerializer(serializers.ModelSerializer):
    """One card in the Master Question Bank list."""
    subject_name = serializers.SerializerMethodField()
    chapter_name = serializers.SerializerMethodField()
    topic_name = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            'id', 'question_id', 'text', 'question_type', 'difficulty', 'status',
            'marks', 'subject_name', 'chapter_name', 'topic_name',
        ]

    def get_subject_name(self, obj):
        try:
            return obj.topic.chapter.subject.name
        except AttributeError:
            return None

    def get_chapter_name(self, obj):
        try:
            return obj.topic.chapter.title
        except AttributeError:
            return None

    def get_topic_name(self, obj):
        try:
            return obj.topic.name
        except AttributeError:
            return None


class AssignedQuestionSerializer(BankQuestionSerializer):
    """A question already attached to the examination, with its exam-local order."""
    order = serializers.IntegerField()
    exam_marks = serializers.FloatField()

    class Meta(BankQuestionSerializer.Meta):
        fields = BankQuestionSerializer.Meta.fields + ['order', 'exam_marks']


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _selection_kwargs(request, examination):
    """Build QuestionSelectionService filters from the request, falling back to
    the examination's own academic targeting so the bank is scoped sensibly
    even before the admin narrows it further."""
    params = request.query_params if request.method == 'GET' else request.data
    requested_topic_id = _int_or_none(params.get('topic'))
    topic_id = (
        examination.topic_id
        if examination.exam_type == 'subject' and examination.topic_id
        else requested_topic_id
    )
    return {
        'exam_id': _int_or_none(params.get('exam')) or examination.exam_id,
        'paper_id': _int_or_none(params.get('paper')),
        'subject_id': _int_or_none(params.get('subject')) or examination.subject_id,
        'chapter_id': _int_or_none(params.get('chapter')),
        'topic_id': topic_id,
        'question_type': (params.get('question_type') or '').strip() or None,
        'tags': (params.get('tags') or '').strip() or None,
        # "Use in Mock Exam" from the admin Collections page - narrows the
        # bank to one QuestionCollection, same approval gate as everything else.
        'collection_id': _int_or_none(params.get('collection')),
        # Optional structured-Tag filter (search/discovery metadata, not a
        # question source the way collection_id is).
        'tag_id': _int_or_none(params.get('tag')),
    }


def _recalculate_totals(examination):
    """Keep the examination's headline numbers in step with its questions."""
    rows = examination.examination_questions.all()
    examination.total_questions = rows.count()
    examination.total_marks = sum(r.marks for r in rows) or 0
    examination.save(update_fields=['total_questions', 'total_marks', 'updated_at'])


class ExaminationQuestionMixin:
    """Adds Step-3 question-selection actions to the admin ExaminationViewSet."""

    @action(detail=True, methods=['get'], url_path='available-questions')
    def available_questions(self, request, pk=None):
        """Paginated Master Question Bank for this examination.

        Only approved questions, already-assigned ones excluded, filtered by the
        academic scope and free-text search.
        """
        examination = self.get_object()
        service = QuestionSelectionService()

        assigned_ids = list(
            examination.examination_questions.values_list('question_id', flat=True)
        )

        qs = service.apply_filters(
            service.get_base_queryset(),
            exclude_ids=assigned_ids,
            **_selection_kwargs(request, examination),
        )

        difficulty = (request.query_params.get('difficulty') or '').strip()
        if difficulty:
            qs = qs.filter(difficulty=difficulty)

        search = (request.query_params.get('search') or '').strip()
        if search:
            # Server-side search so the browser never pulls the whole bank.
            qs = qs.filter(
                Q(text__icontains=search) |
                Q(question_id__icontains=search) |
                Q(tags__icontains=search) |
                Q(topic__name__icontains=search) |
                Q(topic__chapter__title__icontains=search) |
                Q(topic__chapter__subject__name__icontains=search)
            )

        qs = qs.order_by('-created_at', 'id')

        page_size = min(max(_int_or_none(request.query_params.get('page_size')) or 20, 1), 100)
        paginator = Paginator(qs, page_size)
        page_number = _int_or_none(request.query_params.get('page')) or 1
        page = paginator.get_page(page_number)

        return Response({
            'results': BankQuestionSerializer(page.object_list, many=True).data,
            'count': paginator.count,
            'page': page.number,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
            'has_next': page.has_next(),
            'has_previous': page.has_previous(),
        })

    @action(detail=True, methods=['get'], url_path='question-availability')
    def question_availability(self, request, pk=None):
        """Counts for the "Question Collections" summary above the bank.

        Reuses QuestionSelectionService.check_availability so these numbers can
        never drift from what generation would actually draw.
        """
        examination = self.get_object()
        service = QuestionSelectionService()
        kwargs = _selection_kwargs(request, examination)

        assigned_ids = list(
            examination.examination_questions.values_list('question_id', flat=True)
        )
        selected = len(assigned_ids)

        # Pool excluding what is already on the exam — this is what remains
        # addable, which is what the admin is deciding against.
        remaining = service.check_availability(exclude_ids=assigned_ids, **kwargs)
        # Pool ignoring the exam's current selection — the true scope size.
        total_scope = service.check_availability(**kwargs)

        by_type_qs = service.apply_filters(
            service.get_base_queryset(), exclude_ids=assigned_ids, **kwargs
        )
        by_type = {
            'mcq': by_type_qs.filter(question_type='mcq').count(),
            'true_false': by_type_qs.filter(question_type='true_false').count(),
            'subjective': by_type_qs.filter(question_type='subjective').count(),
        }

        return Response({
            'total_in_scope': total_scope['total'],
            'total_available': remaining['total'],
            'by_difficulty': remaining['by_difficulty'],
            'by_type': by_type,
            'selected': selected,
            'remaining_to_target': max(0, (examination.total_questions or 0) - selected),
        })

    @action(detail=True, methods=['get'], url_path='questions')
    def questions(self, request, pk=None):
        """Questions currently assigned to this examination, in exam order."""
        examination = self.get_object()
        rows = examination.examination_questions.select_related(
            'question', 'question__topic', 'question__topic__chapter',
            'question__topic__chapter__subject',
        ).order_by('order', 'id')

        payload = []
        for row in rows:
            data = BankQuestionSerializer(row.question).data
            data['order'] = row.order
            data['exam_marks'] = row.marks
            payload.append(data)

        return Response({
            'results': payload,
            'count': len(payload),
            'total_marks': sum(r.marks for r in rows),
        })

    @action(detail=True, methods=['post'], url_path='add-questions')
    def add_questions(self, request, pk=None):
        """Attach questions to the examination, skipping duplicates."""
        examination = self.get_object()
        ids = request.data.get('question_ids') or []
        if not isinstance(ids, list) or not ids:
            return Response({'error': 'question_ids must be a non-empty list.'},
                            status=status.HTTP_400_BAD_REQUEST)

        approved_qs = Question.objects.filter(
            id__in=ids, status=QuestionSelectionService.APPROVED_STATUS
        )
        if examination.exam_type == 'subject' and examination.topic_id:
            approved_qs = approved_qs.filter(
                topic_id=examination.topic_id,
                question_type__in=Question.OBJECTIVE_TYPES,
            )
        approved = list(approved_qs)
        approved_by_id = {q.id: q for q in approved}

        rejected = [i for i in ids if i not in approved_by_id]
        already = set(examination.examination_questions.values_list('question_id', flat=True))

        next_order = (
            examination.examination_questions.order_by('-order')
            .values_list('order', flat=True).first() or 0
        )

        created = []
        with transaction.atomic():
            for qid in ids:
                question = approved_by_id.get(qid)
                if not question or question.id in already:
                    continue
                next_order += 1
                ExaminationQuestion.objects.create(
                    examination=examination,
                    question=question,
                    order=next_order,
                    marks=question.marks or examination.marks_per_question or 1,
                )
                already.add(question.id)
                created.append(question.id)
            _recalculate_totals(examination)

        AuditLog.objects.create(
            actor=request.user, action='EXAM_ADD_QUESTIONS',
            entity_type='Examination', entity_id=str(examination.id),
            details={'added': len(created), 'requested': len(ids)},
        )

        return Response({
            'success': True,
            'added_count': len(created),
            'skipped_duplicates': len([i for i in ids if i in approved_by_id]) - len(created),
            'not_approved_or_missing': rejected,
            'total_questions': examination.total_questions,
            'total_marks': examination.total_marks,
        })

    @action(detail=True, methods=['post'], url_path='remove-questions')
    def remove_questions(self, request, pk=None):
        """Detach questions from the examination.

        This only removes the ExaminationQuestion link — the question itself
        stays in the Master Question Bank.
        """
        examination = self.get_object()
        ids = request.data.get('question_ids') or []
        if not isinstance(ids, list) or not ids:
            return Response({'error': 'question_ids must be a non-empty list.'},
                            status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            removed, _ = examination.examination_questions.filter(question_id__in=ids).delete()
            _recalculate_totals(examination)

        AuditLog.objects.create(
            actor=request.user, action='EXAM_REMOVE_QUESTIONS',
            entity_type='Examination', entity_id=str(examination.id),
            details={'removed': removed},
        )

        return Response({
            'success': True,
            'removed_count': removed,
            'total_questions': examination.total_questions,
            'total_marks': examination.total_marks,
        })

    @action(detail=True, methods=['post'], url_path='reorder-questions')
    def reorder_questions(self, request, pk=None):
        """Persist a new question order. Payload: [{question_id, order}, ...]."""
        examination = self.get_object()
        order_data = request.data.get('order_data') or []
        if not isinstance(order_data, list) or not order_data:
            return Response({'error': 'order_data must be a non-empty list.'},
                            status=status.HTTP_400_BAD_REQUEST)

        rows = {r.question_id: r for r in examination.examination_questions.all()}
        updated = []
        for item in order_data:
            qid = _int_or_none(item.get('question_id'))
            order = _int_or_none(item.get('order'))
            if qid is None or order is None or qid not in rows:
                continue
            row = rows[qid]
            row.order = order
            updated.append(row)

        if updated:
            ExaminationQuestion.objects.bulk_update(updated, ['order'])

        return Response({'success': True, 'reordered_count': len(updated)})

    @action(detail=True, methods=['post'], url_path='generate-questions')
    def generate_questions(self, request, pk=None):
        """Automatic selection through QuestionSelectionService.

        Modes:
          preview=true   → report what would be selected, write nothing
          replace=true   → clear the current selection first (Regenerate)
        An unsatisfied request is reported, never silently truncated.
        """
        examination = self.get_object()
        service = QuestionSelectionService()

        preview = str(request.data.get('preview', '')).lower() in ('1', 'true', 'yes')
        replace = str(request.data.get('replace', '')).lower() in ('1', 'true', 'yes')

        count = _int_or_none(request.data.get('count')) or 0
        distribution = request.data.get('difficulty_distribution') or None
        if distribution:
            if not isinstance(distribution, dict):
                return Response({'error': 'difficulty_distribution must be an object.'},
                                status=status.HTTP_400_BAD_REQUEST)
            cleaned = {}
            for key, value in distribution.items():
                key = str(key).lower()
                if key not in ('easy', 'medium', 'hard'):
                    return Response({'error': f'Unknown difficulty: {key}'},
                                    status=status.HTTP_400_BAD_REQUEST)
                parsed = _int_or_none(value)
                if parsed is None or parsed < 0:
                    return Response({'error': f'difficulty_distribution.{key} must be a number.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                cleaned[key] = parsed
            distribution = {k: v for k, v in cleaned.items() if v > 0} or None

        if not distribution and count < 1:
            return Response(
                {'error': 'Provide either a question count or a difficulty distribution.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # On replace, the current selection is about to go, so it should not be
        # excluded from the draw. Otherwise never re-pick what is already on.
        assigned_ids = list(examination.examination_questions.values_list('question_id', flat=True))
        exclude_ids = [] if replace else assigned_ids

        result = service.select(
            count=count,
            difficulty_distribution=distribution,
            randomize=True,
            exclude_ids=exclude_ids,
            **_selection_kwargs(request, examination),
        )

        payload = {
            'requested': result['requested'],
            'selected': result['selected'],
            'available': result['available'],
            'satisfied': result['satisfied'],
            'warnings': result['warnings'],
            'preview': preview,
            'questions': BankQuestionSerializer(result['questions'], many=True).data,
        }

        if preview:
            # Nothing is written; the admin confirms from this report.
            return Response(payload)

        if not result['satisfied']:
            # Never quietly build a short exam — hand the decision back.
            payload['error'] = (
                'Not enough approved questions for this configuration. '
                'Adjust the count, the difficulty split, or the academic scope.'
            )
            return Response(payload, status=status.HTTP_409_CONFLICT)

        with transaction.atomic():
            if replace:
                examination.examination_questions.all().delete()
                order = 0
            else:
                order = (
                    examination.examination_questions.order_by('-order')
                    .values_list('order', flat=True).first() or 0
                )
            existing = set(examination.examination_questions.values_list('question_id', flat=True))
            for question in result['questions']:
                if question.id in existing:
                    continue
                order += 1
                ExaminationQuestion.objects.create(
                    examination=examination,
                    question=question,
                    order=order,
                    marks=question.marks or examination.marks_per_question or 1,
                )
                existing.add(question.id)
            _recalculate_totals(examination)

        AuditLog.objects.create(
            actor=request.user, action='EXAM_GENERATE_QUESTIONS',
            entity_type='Examination', entity_id=str(examination.id),
            details={
                'requested': result['requested'],
                'selected': result['selected'],
                'replaced': replace,
            },
        )

        payload['total_questions'] = examination.total_questions
        payload['total_marks'] = examination.total_marks
        return Response(payload, status=status.HTTP_201_CREATED)
