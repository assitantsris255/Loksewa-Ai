"""
Master Question Bank — Centralized Question Selection Engine
============================================================

This module provides the single source of truth for all question selection
across the LoksewaAI platform:

  MASTER QUESTION BANK
          │
  QuestionSelectionService
          │
  ┌───────┼───────────┐
  │       │           │
PRACTICE GAMES   MOCK EXAMS

Usage:
    service = QuestionSelectionService()
    result = service.select(
        exam_id=1,
        subject_id=5,
        difficulty_distribution={"easy": 6, "medium": 10, "hard": 4},
        question_type="mcq",
        randomize=True,
        exclude_ids=[101, 205],
    )
    if result["satisfied"]:
        questions = result["questions"]
    else:
        warnings = result["warnings"]
"""

import random
from typing import Optional
from django.db.models import QuerySet, Q


class QuestionSelectionService:
    """
    Reusable service for selecting approved questions from the Master Question Bank.

    All student-facing content (Practice, Games, Mock Exams) must go through
    this service to ensure:
      - Only APPROVED questions are returned
      - Difficulty distribution is respected
      - Randomization is server-side only
      - Insufficient question pools are handled gracefully
    """

    APPROVED_STATUS = "approved"

    def get_base_queryset(self) -> QuerySet:
        """Returns the base queryset of all approved questions mapped to courses."""
        from .models import Question
        from courses.services.course_access_service import CourseAccessService

        all_course_exam_ids = list(CourseAccessService.get_all_course_exam_ids())
        qs = Question.objects.filter(status=self.APPROVED_STATUS).select_related(
            "topic", "topic__chapter", "topic__chapter__subject",
            "topic__chapter__subject__paper", "topic__chapter__subject__paper__exam"
        )
        academic_mapped = (
            Q(subject_id__isnull=False) |
            Q(topic_id__isnull=False) |
            Q(chapter_id__isnull=False)
        )
        if all_course_exam_ids:
            qs = qs.filter(academic_mapped).filter(
                Q(exam_id__in=all_course_exam_ids) |
                Q(subject__paper__exam_id__in=all_course_exam_ids) |
                Q(chapter__subject__paper__exam_id__in=all_course_exam_ids) |
                Q(topic__chapter__subject__paper__exam_id__in=all_course_exam_ids)
            )
        else:
            return qs.none()
        return qs

    def apply_filters(
        self,
        qs: QuerySet,
        *,
        course_id: Optional[int] = None,
        exam_id: Optional[int] = None,
        paper_id: Optional[int] = None,
        subject_id: Optional[int] = None,
        chapter_id: Optional[int] = None,
        topic_id: Optional[int] = None,
        category_id: Optional[int] = None,
        topic_ids: Optional[list] = None,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        tags: Optional[str] = None,
        collection_id: Optional[int] = None,
        collection_ids: Optional[list] = None,
        tag_id: Optional[int] = None,
        tag_ids: Optional[list] = None,
        exclude_ids: Optional[list] = None,
        exam_ids: Optional[list] = None,
    ) -> QuerySet:
        """Apply academic-hierarchy and metadata filters to a queryset.

        `exam_ids` restricts the pool to a SET of exams - the exams a student
        is authorised for (courses.access.authorized_exam_ids). It composes
        with `exam_id` (both must hold), so a caller can never widen access by
        also passing a specific exam.
        """
        if course_id:
            from courses.models import Course
            from courses.services.course_access_service import CourseAccessService
            course = Course.objects.filter(id=course_id).first()
            if course:
                c_exam_ids = list(CourseAccessService.get_course_exam_ids(course))
                if c_exam_ids:
                    academic_mapped = (
                        Q(subject_id__isnull=False) |
                        Q(topic_id__isnull=False) |
                        Q(chapter_id__isnull=False)
                    )
                    qs = qs.filter(academic_mapped).filter(
                        Q(exam_id__in=c_exam_ids) |
                        Q(subject__paper__exam_id__in=c_exam_ids) |
                        Q(chapter__subject__paper__exam_id__in=c_exam_ids) |
                        Q(topic__chapter__subject__paper__exam_id__in=c_exam_ids)
                    )
                else:
                    return qs.none()
            else:
                return qs.none()

        if exam_ids is not None:
            qs = qs.filter(
                Q(exam_id__in=list(exam_ids)) |
                Q(subject__paper__exam_id__in=list(exam_ids)) |
                Q(chapter__subject__paper__exam_id__in=list(exam_ids)) |
                Q(topic__chapter__subject__paper__exam_id__in=list(exam_ids))
            )
        if exam_id:
            qs = qs.filter(
                Q(exam_id=exam_id) |
                Q(subject__paper__exam_id=exam_id) |
                Q(topic__chapter__subject__paper__exam_id=exam_id)
            )
        if paper_id:
            qs = qs.filter(
                Q(subject__paper_id=paper_id) |
                Q(topic__chapter__subject__paper_id=paper_id)
            )
        if subject_id:
            qs = qs.filter(
                Q(subject_id=subject_id) |
                Q(topic__chapter__subject_id=subject_id)
            )
        if chapter_id:
            qs = qs.filter(
                Q(chapter_id=chapter_id) |
                Q(topic__chapter_id=chapter_id)
            )
        if topic_id:
            qs = qs.filter(topic_id=topic_id)
        if category_id:
            qs = qs.filter(
                Q(category_id=category_id) |
                Q(exam__category_id=category_id) |
                Q(subject__paper__exam__category_id=category_id) |
                Q(topic__chapter__subject__paper__exam__category_id=category_id)
            )
        if topic_ids:
            qs = qs.filter(topic_id__in=topic_ids)
        if difficulty:
            qs = qs.filter(difficulty=difficulty)
        if question_type:
            from .models import Question
            # 'objective' / 'subjective' select a whole family using
            # Question.OBJECTIVE_TYPES / SUBJECTIVE_TYPES (the single source
            # of truth for the split); anything else is an exact type.
            if question_type == 'objective':
                qs = qs.filter(question_type__in=Question.OBJECTIVE_TYPES)
            elif question_type == 'subjective':
                qs = qs.filter(question_type__in=Question.SUBJECTIVE_TYPES)
            else:
                qs = qs.filter(question_type=question_type)
        if tags:
            # Tags are stored comma-separated; filter by any matching tag
            for tag in [t.strip() for t in tags.split(",") if t.strip()]:
                qs = qs.filter(tags__icontains=tag)
        if collection_id:
            qs = qs.filter(collections__id=collection_id)
        if collection_ids:
            qs = qs.filter(collections__id__in=collection_ids)
        # Structured Tag (core.Tag, via Question.tag_objects) - search/filter
        # metadata, never a reusable question group the way collection_id is.
        if tag_id:
            qs = qs.filter(tag_objects__id=tag_id)
        if tag_ids:
            qs = qs.filter(tag_objects__id__in=tag_ids)
        if exclude_ids:
            qs = qs.exclude(id__in=exclude_ids)
        return qs.distinct()

    def check_availability(
        self,
        *,
        course_id=None,
        exam_id=None,
        exam_ids=None,
        paper_id=None,
        subject_id=None,
        chapter_id=None,
        topic_id=None,
        category_id=None,
        topic_ids=None,
        difficulty=None,
        question_type=None,
        tags=None,
        collection_id=None,
        collection_ids=None,
        tag_id=None,
        tag_ids=None,
        exclude_ids=None,
    ) -> dict:
        """
        Returns availability counts for the given criteria WITHOUT selecting.
        Used by the /questions/availability/ endpoint so teachers/admins can
        verify pool size before generating an exam.

        Returns:
            {
                "total": int,
                "by_difficulty": {"easy": int, "medium": int, "hard": int},
            }
        """
        qs = self.apply_filters(
            self.get_base_queryset(),
            course_id=course_id,
            exam_id=exam_id,
            exam_ids=exam_ids,
            paper_id=paper_id,
            subject_id=subject_id,
            chapter_id=chapter_id,
            topic_id=topic_id,
            category_id=category_id,
            topic_ids=topic_ids,
            difficulty=difficulty,
            question_type=question_type,
            tags=tags,
            collection_id=collection_id,
            collection_ids=collection_ids,
            tag_id=tag_id,
            tag_ids=tag_ids,
            exclude_ids=exclude_ids,
        )
        total = qs.count()
        by_diff = {
            "easy": qs.filter(difficulty="easy").count(),
            "medium": qs.filter(difficulty="medium").count(),
            "hard": qs.filter(difficulty="hard").count(),
        }
        return {"total": total, "by_difficulty": by_diff}

    def select_ids(self, *, limit: Optional[int] = None, **filters) -> list:
        """IDs of the approved questions matching `filters`, oldest first.

        Same pool as select() - it is built from the same base queryset and
        apply_filters(), so approval status and question-type rules cannot
        drift - but it returns bare ids. Callers that only need to FIX a
        question set (a Topic-wise session records its questions as
        QuestionAttempt rows) shouldn't load, join and de-duplicate every
        full question row just to read the ids back out.
        """
        qs = self.apply_filters(self.get_base_queryset(), **filters)
        ids = qs.order_by("id").values_list("id", flat=True)
        return list(ids[:limit] if limit is not None else ids)

    def select(
        self,
        *,
        # Academic hierarchy filters
        course_id=None,
        exam_id=None,
        paper_id=None,
        subject_id=None,
        chapter_id=None,
        topic_id=None,
        category_id=None,
        topic_ids=None,
        difficulty=None,
        # Content filters
        question_type=None,
        tags=None,
        collection_id=None,
        collection_ids=None,
        tag_id=None,
        tag_ids=None,
        # Selection config
        count: int = 0,
        difficulty_distribution: Optional[dict] = None,
        topic_distribution: Optional[dict] = None,
        randomize: bool = True,
        exclude_ids: Optional[list] = None,
        exam_ids: Optional[list] = None,
    ) -> dict:
        """
        Select approved questions from the Master Question Bank.

        Args:
            course_id: Filter by course (Loksewa preparation course)
            exam_id: Filter by exam (Loksewa level)
            paper_id: Filter by paper
            subject_id: Filter by subject
            chapter_id: Filter by chapter
            topic_id: Filter by specific topic
            question_type: 'mcq', 'true_false', ... or the family names
                'objective' (mcq + true_false) / 'subjective' (all written-answer types)
            tags: Comma-separated tags to filter by
            collection_id / collection_ids: Restrict to question(s) that belong to
                a QuestionCollection (or any of several). Collection membership is
                a pool filter only - it never bypasses the approved-status gate
                already enforced by get_base_queryset().
            tag_id / tag_ids: Restrict to question(s) carrying a structured Tag
                (or any of several) - search/discovery metadata, same "pool
                filter only" rule as collections. Not a substitute for
                collection_id as a Practice/Mock question *source*.
            count: Total number of questions to select (used when no distribution given)
            difficulty_distribution: Dict mapping difficulty → count.
                e.g. {"easy": 6, "medium": 10, "hard": 4}
                Takes priority over `count`.
            topic_distribution: Dict mapping topic_id (str/int) → count.
                e.g. {"1": 10, "2": 5, "3": 5}
                Applied before difficulty distribution.
            randomize: Whether to randomize selection order
            exclude_ids: List of question IDs to exclude from selection

        Returns:
            {
                "questions": [Question, ...],   # ORM objects
                "available": int,               # Total matching approved questions
                "requested": int,               # Total questions requested
                "selected": int,                # Total actually selected
                "satisfied": bool,              # True if selected == requested
                "warnings": [str, ...],         # Human-readable warnings
            }
        """
        warnings = []
        exclude_ids = list(exclude_ids or [])

        base_qs = self.apply_filters(
            self.get_base_queryset(),
            course_id=course_id,
            exam_id=exam_id,
            paper_id=paper_id,
            subject_id=subject_id,
            chapter_id=chapter_id,
            topic_id=topic_id,
            category_id=category_id,
            topic_ids=topic_ids,
            difficulty=difficulty,
            question_type=question_type,
            tags=tags,
            collection_id=collection_id,
            collection_ids=collection_ids,
            tag_id=tag_id,
            tag_ids=tag_ids,
            exclude_ids=exclude_ids,
            exam_ids=exam_ids,
        )
        total_available = base_qs.count()

        # ── Strategy 1: Topic Distribution ───────────────────────────────────
        if topic_distribution:
            return self._select_by_topic_distribution(
                base_qs=base_qs,
                topic_distribution=topic_distribution,
                randomize=randomize,
                total_available=total_available,
                warnings=warnings,
            )

        # ── Strategy 2: Difficulty Distribution ──────────────────────────────
        if difficulty_distribution:
            return self._select_by_difficulty_distribution(
                base_qs=base_qs,
                difficulty_distribution=difficulty_distribution,
                randomize=randomize,
                total_available=total_available,
                warnings=warnings,
            )

        # ── Strategy 3: Simple Count ──────────────────────────────────────────
        return self._select_by_count(
            base_qs=base_qs,
            count=count,
            randomize=randomize,
            total_available=total_available,
            warnings=warnings,
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _select_by_count(self, *, base_qs, count, randomize, total_available, warnings):
        requested = count
        if total_available < count:
            warnings.append(
                f"Only {total_available} approved question(s) are available for the "
                f"selected criteria, but {count} were requested."
            )
            count = total_available

        if randomize:
            ids = list(base_qs.values_list("id", flat=True))
            selected_ids = random.sample(ids, count) if len(ids) >= count else ids
            from .models import Question
            questions = list(Question.objects.filter(id__in=selected_ids))
            # Shuffle to avoid consistent ordering by id
            random.shuffle(questions)
        else:
            questions = list(base_qs[:count])

        return {
            "questions": questions,
            "available": total_available,
            "requested": requested,
            "selected": len(questions),
            "satisfied": len(questions) == requested,
            "warnings": warnings,
        }

    def _select_by_difficulty_distribution(
        self, *, base_qs, difficulty_distribution, randomize, total_available, warnings
    ):
        requested = sum(difficulty_distribution.values())
        selected_questions = []

        for difficulty, needed in difficulty_distribution.items():
            if needed <= 0:
                continue
            diff_qs = base_qs.filter(difficulty=difficulty)
            available_ids = list(diff_qs.values_list("id", flat=True))
            available_count = len(available_ids)

            if available_count < needed:
                warnings.append(
                    f"Only {available_count} approved '{difficulty}' question(s) available "
                    f"but {needed} were requested."
                )
                selected_ids = available_ids
            else:
                selected_ids = (
                    random.sample(available_ids, needed) if randomize else available_ids[:needed]
                )

            selected_questions.extend(selected_ids)

        from .models import Question
        questions = list(Question.objects.filter(id__in=selected_questions))
        if randomize:
            random.shuffle(questions)

        return {
            "questions": questions,
            "available": total_available,
            "requested": requested,
            "selected": len(questions),
            "satisfied": len(questions) == requested,
            "warnings": warnings,
        }

    def _select_by_topic_distribution(
        self, *, base_qs, topic_distribution, randomize, total_available, warnings
    ):
        requested = sum(topic_distribution.values())
        selected_ids = []

        for topic_id, needed in topic_distribution.items():
            if needed <= 0:
                continue
            topic_qs = base_qs.filter(topic_id=int(topic_id))
            available_ids = list(topic_qs.values_list("id", flat=True))
            available_count = len(available_ids)

            if available_count < needed:
                warnings.append(
                    f"Topic {topic_id}: only {available_count} approved question(s) available "
                    f"but {needed} were requested."
                )
                selected_ids.extend(available_ids)
            else:
                selected_ids.extend(
                    random.sample(available_ids, needed) if randomize else available_ids[:needed]
                )

        from .models import Question
        questions = list(Question.objects.filter(id__in=selected_ids))
        if randomize:
            random.shuffle(questions)

        return {
            "questions": questions,
            "available": total_available,
            "requested": requested,
            "selected": len(questions),
            "satisfied": len(questions) == requested,
            "warnings": warnings,
        }
