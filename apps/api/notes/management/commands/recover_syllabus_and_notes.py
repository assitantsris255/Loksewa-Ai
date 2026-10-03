import os
import sys
import json
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from core.models import User
from exams.models import ExamCategory, Exam, Paper, Subject, Chapter, Topic
from courses.models import Course
from notes.models import StudyMaterial

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Safe metadata reconstruction and recovery process using surviving Google Drive PDFs as evidence."

    def add_arguments(self, parser):
        parser.add_argument(
            '--execute',
            action='store_true',
            help="Actually perform the database recovery (default is READ-ONLY dry-run mode)",
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=0,
            help="Limit the number of records to recover (e.g. 10 for small-batch test)",
        )
        parser.add_argument(
            '--input-file',
            type=str,
            default='',
            help="Path to recovery_candidates.json",
        )
        parser.add_argument(
            '--report-file',
            type=str,
            default='',
            help="Path to save recovery report markdown",
        )

    def handle(self, *args, **options):
        execute = options['execute']
        batch_size = options['batch_size']
        input_file = options['input_file']
        report_file = options['report_file']

        self.stdout.write(self.style.MIGRATE_HEADING("=================================================="))
        self.stdout.write(self.style.MIGRATE_HEADING("   LoksewaAI Syllabus & Notes Data Recovery"))
        self.stdout.write(self.style.MIGRATE_HEADING(f"   Mode: {'EXECUTE (LIVE DB WRITES)' if execute else 'READ-ONLY (DRY RUN)'}"))
        if batch_size > 0:
            self.stdout.write(self.style.WARNING(f"   Batch limit: {batch_size} records (Small-Batch Test Mode)"))
        self.stdout.write(self.style.MIGRATE_HEADING("=================================================="))

        # Default paths
        base_scratch = os.path.join(
            os.path.expanduser("~"),
            ".gemini", "antigravity-ide", "brain",
            "f2776365-8dda-4e68-a415-42e622f49e2b", "scratch"
        )
        if not input_file:
            input_file = os.path.join(base_scratch, "recovery_candidates.json")
        if not report_file:
            report_file = os.path.join(base_scratch, "recovery_execution_report.json")

        if not os.path.exists(input_file):
            self.stderr.write(self.style.ERROR(f"Input file not found: {input_file}"))
            return

        with open(input_file, "r", encoding="utf-8") as f:
            candidates = json.load(f)

        self.stdout.write(f"Loaded {len(candidates)} total candidate records from Drive discovery.")

        # Ensure canonical hierarchy nodes exist (read-only lookup / safe get_or_create)
        admin_user = User.objects.filter(role__in=['admin', 'super-admin']).first()
        if not admin_user:
            admin_user = User.objects.filter(is_superuser=True).first()

        # Step 1: Filter recoverable candidates
        recoverable_candidates = [
            c for c in candidates if c.get('status') in ('AUTO_RECOVERABLE', 'REVIEW_REQUIRED')
        ]
        review_candidates = [
            c for c in candidates if c.get('status') == 'ADMIN_REVIEW'
        ]
        skipped_candidates = [
            c for c in candidates if c.get('status') in ('SKIPPED_TEST_MOCK', 'SKIPPED_NON_ACADEMIC')
        ]

        self.stdout.write(f"Recoverable candidates found: {len(recoverable_candidates)}")
        self.stdout.write(f"Admin review candidates (question papers): {len(review_candidates)}")
        self.stdout.write(f"Non-academic / mock files to skip: {len(skipped_candidates)}")

        # Step 2: Deduplication
        unique_candidates = []
        skipped_duplicates = []
        seen_keys = set()

        for c in recoverable_candidates:
            key = (c.get('original_id'), c.get('detected_title'), c.get('classification'))
            if key in seen_keys:
                skipped_duplicates.append(c)
            else:
                seen_keys.add(key)
                unique_candidates.append(c)

        self.stdout.write(f"Unique distinct academic items to recover: {len(unique_candidates)}")
        self.stdout.write(f"Duplicate Drive files safely retained in Drive: {len(skipped_duplicates)}")

        # Apply batch size limit if set (for small-batch test: 5 syllabus + 5 notes)
        if batch_size > 0:
            syllabi = [c for c in unique_candidates if c.get('classification') == 'SYLLABUS']
            notes = [c for c in unique_candidates if c.get('classification') != 'SYLLABUS']
            
            # Take up to batch_size // 2 of each
            half = batch_size // 2
            items_to_process = syllabi[:half] + notes[:(batch_size - len(syllabi[:half]))]
            if len(items_to_process) < batch_size:
                items_to_process = unique_candidates[:batch_size]
        else:
            items_to_process = unique_candidates

        self.stdout.write(f"\nProcessing batch of {len(items_to_process)} records...")

        # Setup canonical academic hierarchy references
        cat_cache = {c.name.lower(): c for c in ExamCategory.objects.all()}
        exam_cache = {e.name.lower(): e for e in Exam.objects.all()}
        course_cache = {c.title.lower(): c for c in Course.objects.all()}

        # Stats counters
        stats = {
            'total_drive_pdfs': len(candidates),
            'syllabus_pdfs': sum(1 for c in candidates if c.get('classification') == 'SYLLABUS'),
            'notes_pdfs': sum(1 for c in candidates if c.get('classification') in ('NOTE', 'STUDY_MATERIAL')),
            'other_pdfs': sum(1 for c in candidates if c.get('classification') in ('OTHER', 'SOLUTION', 'QUESTION_PAPER')),
            'high_confidence': sum(1 for c in candidates if c.get('confidence') == 'HIGH'),
            'medium_confidence': sum(1 for c in candidates if c.get('confidence') == 'MEDIUM'),
            'needs_review': len(review_candidates),
            'skipped_duplicates': len(skipped_duplicates),
            'processed_in_batch': len(items_to_process),
            'existing_records_matched': 0,
            'records_recreated_with_orig_id': 0,
            'new_records_created': 0,
            'failures': 0,
            'recovered_items': []
        }

        # Helper to ensure subjects exist
        def resolve_subject(exam_obj, subject_name):
            if not exam_obj or not subject_name:
                return None
            sub = Subject.objects.filter(name__iexact=subject_name).first()
            if not sub and execute:
                paper = Paper.objects.filter(exam=exam_obj).first()
                if not paper:
                    paper = Paper.objects.create(
                        exam=exam_obj,
                        name=f"{exam_obj.name} Technical Paper",
                        paper_number="1",
                        is_active=True
                    )
                sub = Subject.objects.create(
                    paper=paper,
                    name=subject_name,
                    is_active=True,
                    order=1
                )
            return sub

        with transaction.atomic():
            for idx, c in enumerate(items_to_process, 1):
                fname = c['file_name']
                fid = c['drive_file_id']
                orig_id = c.get('original_id')
                if orig_id == "UNKNOWN":
                    orig_id = None
                else:
                    try:
                        orig_id = int(orig_id)
                    except (ValueError, TypeError):
                        orig_id = None

                title = c['detected_title']
                cat_name = c.get('detected_category')
                lvl_name = c.get('detected_level')
                exam_name = c.get('detected_exam')
                course_name = c.get('detected_course')
                subject_name = c.get('detected_subject')
                classification = c.get('classification')
                content_cat = c.get('content_category', 'syllabus' if classification == 'SYLLABUS' else 'subjective_topicwise')

                # Format file path according to GoogleDriveStorage convention:
                # "study_materials/pdfs/{file_id}__{clean_basename}"
                clean_fname = fname.replace('__', '_')
                storage_file_path = f"study_materials/pdfs/{fid}__{clean_fname}"

                # Resolve Category
                cat_obj = None
                if cat_name:
                    cat_obj = ExamCategory.objects.filter(name__iexact=cat_name).first()

                # Resolve Exam
                exam_obj = None
                if exam_name:
                    exam_obj = Exam.objects.filter(name__iexact=exam_name).first()
                    if not exam_obj and lvl_name:
                        exam_obj = Exam.objects.filter(name__iexact=exam_name, parent__name__icontains=lvl_name).first()

                # Fallback exam resolution
                if not exam_obj:
                    if lvl_name:
                        exam_obj = Exam.objects.filter(name__icontains=lvl_name).first()
                    elif cat_obj:
                        exam_obj = Exam.objects.filter(category=cat_obj).first()
                    else:
                        exam_obj = Exam.objects.first()

                # Resolve Course (for Notes)
                course_obj = None
                if classification in ('NOTE', 'STUDY_MATERIAL'):
                    if exam_obj:
                        course_obj = Course.objects.filter(exam=exam_obj).first()
                    if not course_obj and course_name:
                        course_obj = Course.objects.filter(title__icontains=course_name).first()

                # Resolve Subject (for Notes)
                subject_obj = None
                if subject_name and exam_obj:
                    subject_obj = resolve_subject(exam_obj, subject_name)

                # Check if already exists in StudyMaterial
                existing_sm = None
                if orig_id:
                    existing_sm = StudyMaterial.objects.filter(id=orig_id).first()
                if not existing_sm:
                    existing_sm = StudyMaterial.objects.filter(file__icontains=fid).first()
                if not existing_sm and exam_obj:
                    existing_sm = StudyMaterial.objects.filter(title__iexact=title, exam=exam_obj).first()

                access_type = 'free' if classification == 'SYLLABUS' else 'premium'

                action_taken = "DRY_RUN"
                recovered_id = orig_id

                if execute:
                    try:
                        if existing_sm:
                            # Reconnect existing record
                            existing_sm.file = storage_file_path
                            existing_sm.title = title
                            existing_sm.content_category = content_cat
                            existing_sm.access_type = access_type
                            existing_sm.status = 'published'
                            if exam_obj:
                                existing_sm.exam = exam_obj
                            if course_obj:
                                existing_sm.course = course_obj
                            if subject_obj:
                                existing_sm.subject = subject_obj
                            existing_sm.save()
                            action_taken = "RECONNECTED"
                            recovered_id = existing_sm.id
                            stats['existing_records_matched'] += 1
                        elif orig_id:
                            # Recreate with original ID preserved
                            slug = f"{slugify(title)[:200]}-{str(orig_id)}"
                            sm = StudyMaterial(
                                id=orig_id,
                                title=title,
                                slug=slug,
                                exam=exam_obj,
                                course=course_obj,
                                subject=subject_obj,
                                content_category=content_cat,
                                material_type='pdf',
                                access_type=access_type,
                                status='published',
                                file=storage_file_path,
                                teacher=admin_user,
                                is_downloadable=True
                            )
                            sm.save(force_insert=True)
                            action_taken = "RECREATED_ORIGINAL_ID"
                            recovered_id = orig_id
                            stats['records_recreated_with_orig_id'] += 1
                        else:
                            # Create new record
                            slug = f"{slugify(title)[:200]}-{fid[:8]}"
                            sm = StudyMaterial.objects.create(
                                title=title,
                                slug=slug,
                                exam=exam_obj,
                                course=course_obj,
                                subject=subject_obj,
                                content_category=content_cat,
                                material_type='pdf',
                                access_type=access_type,
                                status='published',
                                file=storage_file_path,
                                teacher=admin_user,
                                is_downloadable=True
                            )
                            action_taken = "CREATED_NEW"
                            recovered_id = sm.id
                            stats['new_records_created'] += 1

                    except Exception as err:
                        self.stderr.write(self.style.ERROR(f"Error recovering {fname}: {err}"))
                        stats['failures'] += 1
                        action_taken = f"FAILED: {err}"
                else:
                    if existing_sm:
                        action_taken = "WOULD_RECONNECT"
                        recovered_id = existing_sm.id
                        stats['existing_records_matched'] += 1
                    elif orig_id:
                        action_taken = "WOULD_RECREATE_ORIGINAL_ID"
                        stats['records_recreated_with_orig_id'] += 1
                    else:
                        action_taken = "WOULD_CREATE_NEW"
                        stats['new_records_created'] += 1

                self.stdout.write(
                    f"[{idx:2d}/{len(items_to_process)}] [{classification:8s}] {action_taken:24s} | "
                    f"ID: {recovered_id} | {title} | Exam: {exam_obj.name if exam_obj else 'None'} | "
                    f"File: {fname}"
                )

                stats['recovered_items'].append({
                    'index': idx,
                    'recovered_id': recovered_id,
                    'original_id': orig_id if orig_id else "UNKNOWN",
                    'title': title,
                    'classification': classification,
                    'category': cat_name,
                    'level': lvl_name,
                    'exam': exam_obj.name if exam_obj else None,
                    'course': course_obj.title if course_obj else None,
                    'subject': subject_obj.name if subject_obj else None,
                    'file_name': fname,
                    'drive_file_id': fid,
                    'action': action_taken,
                    'confidence': c.get('confidence'),
                    'evidence': c.get('evidence')
                })

            if not execute:
                # In dry-run mode, roll back transaction
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS("\nRecovery run completed successfully!"))
        self.stdout.write(f"Matched Existing: {stats['existing_records_matched']}")
        self.stdout.write(f"Recreated with Original ID: {stats['records_recreated_with_orig_id']}")
        self.stdout.write(f"New Recreated: {stats['new_records_created']}")
        self.stdout.write(f"Failures: {stats['failures']}")

        # Save stats and report
        with open(report_file, "w", encoding="utf-8") as rf:
            json.dump(stats, rf, indent=2, ensure_ascii=False)

        self.stdout.write(self.style.SUCCESS(f"Saved execution report to {report_file}"))
