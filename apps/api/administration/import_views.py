import csv
import io
from openpyxl import Workbook, load_workbook
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .permissions import IsAdminUser
from django.http import HttpResponse
from django.db import transaction
from administration.models import CSVImport, AuditLog
from exams.models import Question, Topic, QuestionCollection, ExamCategory, Exam, Subject, Chapter
from core.models import Tag
from ai_tutor.services import AdminAILogic

from exams.services.question_import_service import (
    CSV_COLUMNS, ROW_FIELDS,
    EXCEL_HEADERS_OBJECTIVE, EXCEL_HEADERS_TRUE_FALSE, EXCEL_HEADERS_SUBJECTIVE,
    OBJECTIVE_TYPES, SUBJECTIVE_TYPES, ALL_TYPES,
    EXCEL_HEADER_MAP, VALID_ANSWERS, ANSWER_NUMBER_MAP,
    _normalize_answer, _parse_xlsx_rows, _parse_csv_rows,
    _analyse_row, _missing_detail, _existing_question_ids,
    _build_report, _recount, generate_excel_template,
)



def _response_payload(import_record):
    counts = _recount(import_record.report_data)
    return {
        'import_id': import_record.id,
        'category_id': import_record.category_id,
        'position_id': import_record.exam_id,
        'subject_id': import_record.subject_id,
        'chapter_id': import_record.chapter_id,
        'topic_id': import_record.topic_id,
        'question_type': import_record.question_type,
        'difficulty': import_record.difficulty,
        'collection_id': import_record.collection_id,
        'tag_ids': list(import_record.tag_objects.values_list('id', flat=True)),
        'total_rows': counts['total'],
        'valid_rows': counts['valid'],
        'incomplete_rows': counts['incomplete'],
        'duplicate_rows': counts['duplicate'],
        'error_rows': counts['error'],
        'report_data': import_record.report_data,
    }


class QuestionImportViewSet(viewsets.ModelViewSet):
    queryset = CSVImport.objects.all().order_by('-created_at')
    permission_classes = [IsAdminUser]

    @action(detail=False, methods=['get'])
    def template(self, request):
        """Download the Excel (.xlsx) import template for a question type.

        ?type=mcq (default) | true_false | subjective. The data sheet holds
        headers only, so nothing sample-shaped can be imported by accident;
        examples and rules live on a separate "Instructions" sheet.
        """
        qtype = (request.query_params.get('type') or 'mcq').strip().lower()
        if qtype in SUBJECTIVE_TYPES:
            qtype = 'subjective'
        if qtype not in ('mcq', 'true_false', 'subjective'):
            return Response({'error': f'Unsupported template type: {qtype}'}, status=400)

        buf, title = generate_excel_template(qtype)
        response = HttpResponse(
            buf.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{title}.xlsx"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return response

    @action(detail=False, methods=['post'])
    def upload(self, request):
        """Parse and validate a CSV/Excel file against a syllabus target chosen in the UI.

        Nothing is written to the Question table here.
        """
        if 'file' not in request.FILES:
            return Response({'error': 'No file provided'}, status=400)

        file = request.FILES['file']
        name = file.name.lower()
        is_excel = name.endswith('.xlsx') or name.endswith('.xls')
        is_csv = name.endswith('.csv')
        if not (is_excel or is_csv):
            return Response({'error': 'Please upload a valid Excel (.xlsx) or CSV file.'}, status=400)

        category = None
        category_id = request.data.get('category') or request.data.get('category_id')
        if category_id and str(category_id) not in ('null', 'undefined', ''):
            try:
                category = ExamCategory.objects.get(pk=category_id)
            except (ExamCategory.DoesNotExist, ValueError, TypeError):
                return Response({'error': 'The selected category no longer exists.'}, status=400)

        exam = None
        position_id = request.data.get('position') or request.data.get('position_id') or request.data.get('exam') or request.data.get('exam_id')
        if position_id and str(position_id) not in ('null', 'undefined', ''):
            try:
                exam = Exam.objects.select_related('category').get(pk=position_id)
            except (Exam.DoesNotExist, ValueError, TypeError):
                return Response({'error': 'The selected level/position no longer exists.'}, status=400)

        subject = None
        subject_id = request.data.get('subject') or request.data.get('subject_id')
        if subject_id and str(subject_id) not in ('null', 'undefined', ''):
            try:
                subject = Subject.objects.select_related('paper__exam__category').get(pk=subject_id)
            except (Subject.DoesNotExist, ValueError, TypeError):
                return Response({'error': 'The selected subject no longer exists.'}, status=400)

        chapter = None
        chapter_id = request.data.get('chapter') or request.data.get('chapter_id')
        if chapter_id and str(chapter_id) not in ('null', 'undefined', ''):
            try:
                chapter = Chapter.objects.select_related('subject__paper__exam__category').get(pk=chapter_id)
            except (Chapter.DoesNotExist, ValueError, TypeError):
                return Response({'error': 'The selected chapter no longer exists.'}, status=400)

        topic = None
        topic_id = request.data.get('topic') or request.data.get('topic_id')
        if topic_id and str(topic_id) not in ('null', 'undefined', ''):
            try:
                topic = Topic.objects.select_related('chapter__subject__paper__exam__category').get(pk=topic_id)
            except (Topic.DoesNotExist, ValueError, TypeError):
                return Response({'error': 'The selected topic no longer exists.'}, status=400)

        # Auto-infer parents upwards
        if topic:
            if not chapter and topic.chapter:
                chapter = topic.chapter
            if not subject and chapter and chapter.subject:
                subject = chapter.subject
        if chapter:
            if not subject and chapter.subject:
                subject = chapter.subject
        if subject:
            if not exam and subject.paper and subject.paper.exam:
                exam = subject.paper.exam
            if not category and exam and exam.category:
                category = exam.category
        if exam and not category and exam.category:
            category = exam.category

        course = None
        course_id = request.data.get('course') or request.data.get('course_id')
        if course_id and str(course_id) not in ('null', 'undefined', ''):
            from courses.models import Course
            try:
                course = Course.objects.get(pk=course_id)
            except (Course.DoesNotExist, ValueError, TypeError):
                return Response({'error': 'The selected course no longer exists.'}, status=400)

        # Academic consistency checks:
        if course:
            from courses.services.course_access_service import CourseAccessService
            course_exam_ids = CourseAccessService.get_course_exam_ids(course)
            if not exam and course.exam:
                exam = course.exam
                if not category and course.exam.category:
                    category = course.exam.category
            elif exam and exam.id not in course_exam_ids:
                return Response({'error': f"Level/Position '{exam.name}' does not belong to course '{course.title}'."}, status=400)
            if subject:
                sub_exam_id = subject.paper.exam_id if (subject.paper_id and subject.paper) else None
                if sub_exam_id and sub_exam_id not in course_exam_ids:
                    return Response({'error': f"Subject '{subject.name}' does not belong to course '{course.title}'."}, status=400)

        if exam and category and exam.category_id != category.id:
            return Response({'error': f"Position/Level '{exam.name}' does not belong to category '{category.name}'."}, status=400)
        if subject and exam:
            subject_exam_id = subject.paper.exam_id if (subject.paper_id and subject.paper) else None
            is_valid_exam = (
                subject_exam_id == exam.id or
                (subject.paper and subject.paper.exam and subject.paper.exam.parent_id == exam.id)
            )
            if not is_valid_exam:
                return Response({'error': f"Subject '{subject.name}' does not belong to level/position '{exam.name}'."}, status=400)
        if chapter and subject and chapter.subject_id != subject.id:
            return Response({'error': f"Chapter '{chapter.title}' does not belong to subject '{subject.name}'."}, status=400)
        if topic and chapter and topic.chapter_id != chapter.id:
            return Response({'error': f"Topic '{topic.name}' does not belong to chapter '{chapter.title}'."}, status=400)

        question_type = (request.data.get('question_type') or 'mcq').strip().lower() or 'mcq'
        if question_type not in ALL_TYPES:
            question_type = 'mcq'

        raw_difficulty = (request.data.get('difficulty') or '').strip().lower()
        difficulty = raw_difficulty if raw_difficulty in ('easy', 'medium', 'hard') else 'medium'

        collection = None
        collection_id = request.data.get('collection_id')
        if collection_id:
            try:
                collection = QuestionCollection.objects.get(pk=collection_id)
            except (QuestionCollection.DoesNotExist, ValueError, TypeError):
                return Response({'error': 'The selected collection no longer exists.'}, status=400)

        tag_ids = request.data.getlist('tag_ids') if hasattr(request.data, 'getlist') else (request.data.get('tag_ids') or [])
        tags = list(Tag.objects.filter(pk__in=tag_ids)) if tag_ids else []

        try:
            if is_excel:
                rows, found_headers = _parse_xlsx_rows(file)
            else:
                rows, found_headers = _parse_csv_rows(file)
        except Exception as exc:
            return Response({'error': f'Failed to parse the file: {exc}'}, status=400)

        if not rows:
            return Response({'error': 'The file has no data rows.'}, status=400)

        if 'question' not in found_headers:
            return Response(
                {'error': "The file must have a 'Questions' column. Download the template for the expected format."},
                status=400,
            )

        # Guard against uploading the wrong template for the chosen type.
        if question_type in SUBJECTIVE_TYPES and 'model_answer' not in found_headers:
            return Response(
                {'error': "This file has no 'Model Answer' column. Subjective questions need the Subjective "
                          "template (SN, Questions, Mark, Model Answer, Explanation, Hint)."},
                status=400,
            )
        if question_type in OBJECTIVE_TYPES and 'model_answer' in found_headers \
                and 'correct_answer' not in found_headers:
            return Response(
                {'error': "This file looks like the Subjective template (it has a 'Model Answer' column and no "
                          "'Correct Answer'). Choose Question Type = Subjective, or download the Objective template."},
                status=400,
            )

        report_data, counts = _build_report(rows, question_type, allow_blank_explanation=True)

        import_record = CSVImport.objects.create(
            admin=request.user,
            file_name=file.name,
            status='validated',
            category=category,
            exam=exam,
            subject=subject,
            chapter=chapter,
            topic=topic,
            question_type=question_type,
            difficulty=difficulty,
            collection=collection,
            total_rows=counts['total'],
            valid_rows=counts['valid'],
            duplicate_rows=counts['duplicate'],
            error_rows=counts['error'],
            report_data=report_data,
        )
        if tags:
            import_record.tag_objects.set(tags)
        return Response(_response_payload(import_record))

    @action(detail=True, methods=['post'], url_path='ai-fill')
    def ai_fill(self, request, pk=None):
        """Fill the gaps the AI can handle (options, correct answer, explanation)."""
        try:
            import_record = CSVImport.objects.select_related(
                'topic', 'topic__chapter', 'topic__chapter__subject'
            ).get(pk=pk, status='validated')
        except CSVImport.DoesNotExist:
            return Response({'error': 'Import not found or already processed.'}, status=404)

        if import_record.question_type in SUBJECTIVE_TYPES:
            return Response(
                {'error': 'AI fill applies to objective questions only. Subjective rows must include a Model Answer.'},
                status=400,
            )

        incomplete = [r for r in import_record.report_data if r['status'] == 'incomplete']
        if not incomplete:
            return Response(_response_payload(import_record))

        needs_options = any('options' in r['missing'] or 'correct_answer' in r['missing']
                            for r in incomplete)
        needs_explanations = any('explanation' in r['missing'] for r in incomplete)

        subject = 'General'
        if import_record.topic_id:
            subject = import_record.topic.chapter.subject.name

        payload = [{
            'id': str(r['row_index']),
            'question': r['data']['question'],
            'option_a': r['data']['option_a'],
            'option_b': r['data']['option_b'],
            'option_c': r['data']['option_c'],
            'option_d': r['data']['option_d'],
        } for r in incomplete]

        generated = AdminAILogic().generate_bulk_content(
            payload, needs_options, needs_explanations, subject
        )
        if not generated:
            return Response({'error': 'The AI could not generate the missing content. Try again.'}, status=502)

        by_row = {str(item.get('id')): item for item in generated}

        for row in incomplete:
            item = by_row.get(str(row['row_index']))
            if not item:
                continue

            if 'options' in row['missing']:
                for key in ('option_a', 'option_b', 'option_c', 'option_d'):
                    if item.get(key):
                        row['data'][key] = item[key]
            if 'correct_answer' in row['missing'] and item.get('correct_answer'):
                row['data']['correct_answer'] = item['correct_answer']
            if 'explanation' in row['missing'] and item.get('explanation'):
                row['data']['explanation'] = item['explanation']

            row['ai_filled'] = list(row['missing'])
            errors, missing = _analyse_row(row['data'], import_record.question_type, allow_blank_explanation=True)
            row['errors'] = errors
            row['missing'] = missing
            row['missing_detail'] = _missing_detail(row['data'], import_record.question_type) if missing else []
            row['status'] = 'error' if errors else ('incomplete' if missing else 'valid')

        counts = _recount(import_record.report_data)
        import_record.valid_rows = counts['valid']
        import_record.error_rows = counts['error']
        import_record.save(update_fields=['report_data', 'valid_rows', 'error_rows'])

        return Response(_response_payload(import_record))

    @action(detail=True, methods=['post'])
    def commit(self, request, pk=None):
        """Insert the rows that are fully valid. Incomplete and error rows are skipped."""
        try:
            import_record = CSVImport.objects.get(pk=pk, status='validated')
        except CSVImport.DoesNotExist:
            return Response({'error': 'Import not found or already processed.'}, status=404)

        # Re-check duplicates at commit time: another import or an admin may
        # have added the same question since this file was analysed. Existing
        # questions are never overwritten - a row that has become a duplicate
        # is skipped and reported.
        valid_rows = [r for r in import_record.report_data if r['status'] == 'valid']
        existing_ids = _existing_question_ids(r['data']['question'].strip().lower() for r in valid_rows)

        is_subjective = import_record.question_type in SUBJECTIVE_TYPES
        questions_to_create = []
        skipped_duplicates = []
        for row in valid_rows:
            data = row['data']
            lowered = data['question'].strip().lower()
            if lowered in existing_ids:
                skipped_duplicates.append({
                    'row_index': row['row_index'],
                    'existing_question_id': existing_ids[lowered]['code'],
                    'existing_id': existing_ids[lowered]['id'],
                })
                continue
            marks_raw = (data.get('marks') or '').strip()
            questions_to_create.append(Question(
                category=import_record.category or (import_record.exam.category if import_record.exam else None),
                exam=import_record.exam,
                subject=import_record.subject or (import_record.chapter.subject if import_record.chapter else (import_record.topic.chapter.subject if import_record.topic and import_record.topic.chapter else None)),
                chapter=import_record.chapter or (import_record.topic.chapter if import_record.topic else None),
                topic=import_record.topic,
                question_type=import_record.question_type or 'mcq',
                text=data['question'],
                # Objective-only fields stay empty for subjective questions.
                option_a='' if is_subjective else (data.get('option_a') or ''),
                option_b='' if is_subjective else (data.get('option_b') or ''),
                option_c='' if is_subjective else (data.get('option_c') or ''),
                option_d='' if is_subjective else (data.get('option_d') or ''),
                correct_option=None if is_subjective else ((data.get('correct_answer') or '').upper() or None),
                model_answer=(data.get('model_answer') or '') if is_subjective else '',
                explanation=data.get('explanation') or '',
                hint=data.get('hint') or '',
                marks=float(marks_raw) if marks_raw else 1,
                difficulty=import_record.difficulty or 'medium',
                status='approved' if (import_record.exam_id or import_record.subject_id) else 'draft',
                created_by=request.user,
            ))

        with transaction.atomic():
            created = Question.objects.bulk_create(questions_to_create)

            # bulk_create skips Model.save(), so the Q-000001 style id is never
            # generated. Backfill it for the rows this import just created.
            for q in created:
                q.question_id = f"Q-{q.pk:06d}"
            if created:
                Question.objects.bulk_update(created, ['question_id'])

            if created and import_record.collection_id:
                import_record.collection.questions.add(*created)

            tag_list = list(import_record.tag_objects.all())
            if created and tag_list:
                for q in created:
                    q.tag_objects.set(tag_list)

        import_record.status = 'imported'
        import_record.save(update_fields=['status'])

        # Collect existing canonical question IDs for rows that were marked duplicate during analysis
        duplicate_rows = [r for r in import_record.report_data if r['status'] == 'duplicate']
        dup_texts = [r['data']['question'].strip().lower() for r in duplicate_rows if r.get('data', {}).get('question')]
        dup_map = _existing_question_ids(dup_texts) if dup_texts else {}

        analysis_duplicates = []
        for row in duplicate_rows:
            lowered = row.get('data', {}).get('question', '').strip().lower()
            if lowered in dup_map:
                analysis_duplicates.append({
                    'row_index': row['row_index'],
                    'existing_question_id': dup_map[lowered]['code'],
                    'existing_id': dup_map[lowered]['id'],
                })

        all_skipped = skipped_duplicates + analysis_duplicates
        existing_canonical_ids = list(dict.fromkeys(
            d['existing_id'] for d in all_skipped if 'existing_id' in d
        ))
        new_ids = [q.pk for q in created]
        all_ids = new_ids + existing_canonical_ids

        AuditLog.objects.create(
            actor=request.user, action='CSV_IMPORT', entity_type='Question', entity_id=None,
            details={
                'import_id': import_record.id,
                'file_name': import_record.file_name,
                'imported_count': len(created),
                'topic_id': import_record.topic_id,
                'collection_id': import_record.collection_id,
                'reused_duplicates_count': len(existing_canonical_ids),
            },
        )
        return Response({
            'success': True,
            'imported_count': len(created),
            'question_ids': new_ids,
            'skipped_duplicates': all_skipped,
            'existing_question_ids': existing_canonical_ids,
            'all_question_ids': all_ids,
        })

    @action(detail=True, methods=['get'], url_path='error-report')
    def error_report(self, request, pk=None):
        """Download an Excel report of only the error/duplicate rows, for correction."""
        try:
            import_record = CSVImport.objects.get(pk=pk)
        except CSVImport.DoesNotExist:
            return Response({'error': 'Import not found.'}, status=404)

        wb = Workbook()
        ws = wb.active
        ws.title = 'Errors'
        ws.append(['Row', 'SN', 'Question', 'Error'])
        for row in import_record.report_data:
            if row['status'] not in ('error', 'duplicate'):
                continue
            ws.append([
                row['row_index'], row.get('sn', ''), row['data'].get('question', ''),
                '; '.join(row['errors']),
            ])

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        response = HttpResponse(
            buf.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="import_{pk}_errors.xlsx"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return response
