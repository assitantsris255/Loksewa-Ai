from rest_framework import viewsets, permissions, status
from administration.permissions import IsAdminUser
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from .models import StudyMaterial, StudentMaterialProgress, StudentMaterialBookmark
from .serializers import StudyMaterialListSerializer, StudyMaterialDetailSerializer, with_student_state
from subscriptions.access import has_active_subscription


class PublicStudyMaterialListView(APIView):
    """GET /api/notes/public/ - a small, anonymous-friendly preview of free
    published study materials for the homepage. Unlike StudyMaterialViewSet,
    this deliberately excludes premium/course-locked materials and never
    checks enrollment, since there is no logged-in student to check it against."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            limit = min(int(request.query_params.get('limit', 6)), 100)
        except (TypeError, ValueError):
            limit = 6
        materials = StudyMaterial.objects.filter(
            status='published', access_type='free', course__isnull=True,
        ).select_related('subject', 'exam').order_by('-created_at')[:limit]

        data = [{
            'id': m.id,
            'title': m.title,
            'description': m.description,
            'material_type': m.material_type,
            'difficulty': m.difficulty,
            'estimated_reading_time': m.estimated_reading_time,
            'subject_name': m.subject.name if m.subject else None,
            'exam_name': m.exam.name if m.exam else None,
        } for m in materials]

        return Response(data)


class StudyMaterialViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from courses.services.course_access_service import CourseAccessService

        queryset = StudyMaterial.objects.filter(status='published').select_related(
            'subject', 'chapter', 'topic', 'exam', 'exam__parent', 'exam__category', 'course'
        )

        user = self.request.user

        # 1. Authoritative course-level and academic-scope filtering via CourseAccessService
        queryset = CourseAccessService.filter_notes_queryset(user, queryset, allow_public_free=False)

        # 2. Specific query param filtering with strict validation against authorized scope
        course_param = self.request.query_params.get('course')
        if course_param:
            try:
                c_id = int(course_param)
                if not CourseAccessService.has_course_access(user, c_id):
                    return queryset.none()
                queryset = queryset.filter(course_id=c_id)
            except (ValueError, TypeError):
                return queryset.none()

        exam_param = self.request.query_params.get('exam')
        if exam_param:
            try:
                e_id = int(exam_param)
                scope = CourseAccessService.get_accessible_exam_ids(user)
                if scope is not None and e_id not in scope:
                    return queryset.none()
                queryset = queryset.filter(exam_id=e_id)
            except (ValueError, TypeError):
                return queryset.none()

        subject = self.request.query_params.get('subject')
        chapter = self.request.query_params.get('chapter')
        topic = self.request.query_params.get('topic')
        material_type = self.request.query_params.get('material_type')
        content_category = self.request.query_params.get('content_category')
        note_type = self.request.query_params.get('note_type')
        search = self.request.query_params.get('search')

        if subject:
            queryset = queryset.filter(subject_id=subject)
        if chapter:
            queryset = queryset.filter(chapter_id=chapter)
        if topic:
            queryset = queryset.filter(topic_id=topic)
        if material_type:
            queryset = queryset.filter(material_type=material_type)
        if content_category:
            queryset = queryset.filter(content_category=content_category)
        if note_type:
            queryset = queryset.filter(note_type=note_type)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(content__icontains=search)
            )

        return with_student_state(queryset, user)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return StudyMaterialDetailSerializer
        return StudyMaterialListSerializer

    def retrieve(self, request, *args, **kwargs):
        from courses.services.course_access_service import CourseAccessService
        material = self.get_object()
        if not CourseAccessService.has_note_access(request.user, material):
            return Response(
                {"detail": "You do not have access to this study material."},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = self.get_serializer(material)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Secure download action enforcing course authorization and download permission."""
        from courses.services.course_access_service import CourseAccessService
        from django.http import FileResponse

        material = self.get_object()
        if not CourseAccessService.has_note_access(request.user, material):
            return Response(
                {"detail": "You do not have access to this study material."},
                status=status.HTTP_403_FORBIDDEN
            )
        disposition = request.query_params.get('disposition', 'attachment').lower()
        is_inline = disposition == 'inline'
        if not material.is_downloadable and not is_inline:
            return Response(
                {"detail": "Downloads are disabled for this study material."},
                status=status.HTTP_403_FORBIDDEN
            )
        if not material.file:
            return Response(
                {"detail": "No file attached to this material."},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            response = FileResponse(
                material.file.open('rb'),
                as_attachment=not is_inline,
                filename=f"{material.slug or 'material'}.pdf"
            )
            response['Access-Control-Expose-Headers'] = 'Content-Disposition'
            return response
        except Exception as e:
            return Response({"detail": f"Could not read file: {e}"}, status=status.HTTP_404_NOT_FOUND)


    @action(detail=True, methods=['post', 'delete'])
    def bookmark(self, request, pk=None):
        material = self.get_object()
        if request.method == 'POST':
            StudentMaterialBookmark.objects.get_or_create(student=request.user, material=material)
            return Response({"status": "bookmarked"})
        elif request.method == 'DELETE':
            StudentMaterialBookmark.objects.filter(student=request.user, material=material).delete()
            return Response({"status": "unbookmarked"})

    @action(detail=True, methods=['post'])
    def progress(self, request, pk=None):
        material = self.get_object()
        progress_val = request.data.get('progress', 0)

        try:
            progress_val = int(progress_val)
        except ValueError:
            return Response({"error": "Invalid progress value"}, status=status.HTTP_400_BAD_REQUEST)

        prog, _ = StudentMaterialProgress.objects.get_or_create(student=request.user, material=material)

        if progress_val > prog.progress:
            prog.progress = progress_val
            if progress_val >= 100:
                prog.completed = True
            prog.save()

        return Response({"status": "progress updated", "progress": prog.progress})

    @action(detail=False, methods=['get'])
    def bookmarks(self, request):
        from courses.services.course_access_service import CourseAccessService
        bookmarks = StudentMaterialBookmark.objects.filter(student=request.user).values_list('material_id', flat=True)
        queryset = StudyMaterial.objects.filter(id__in=bookmarks, status='published')
        queryset = CourseAccessService.filter_notes_queryset(request.user, queryset)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def recent(self, request):
        from courses.services.course_access_service import CourseAccessService
        recent_progress = StudentMaterialProgress.objects.filter(student=request.user).order_by('-last_viewed_at')[:5]
        material_ids = [rp.material_id for rp in recent_progress]

        queryset = StudyMaterial.objects.filter(id__in=material_ids, status='published')
        queryset = CourseAccessService.filter_notes_queryset(request.user, queryset)

        materials_dict = {m.id: m for m in queryset}
        ordered_materials = [materials_dict[mid] for mid in material_ids if mid in materials_dict]

        serializer = self.get_serializer(ordered_materials, many=True)
        return Response(serializer.data)



class StudentPortalSyllabusNotesView(APIView):
    """GET /api/notes/student/portal/
    Returns the student's authorized preparations and full structured content
    for the selected preparation:
      - Syllabus (PDFs)
      - Subjective Topicwise Notes [Detailed] (Standard, AI)
      - Objective Topicwise Notes [Detailed] (Standard, AI)
      - Revision Notes (Subjective, Objective)
    Enforces strict preparation isolation.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from exams.models import Exam
        from courses.models import Enrollment

        user = request.user
        is_staff_or_teacher = user.is_staff or user.is_superuser or user.role in ('admin', 'super-admin', 'teacher')

        authorized_prep_dict = {}

        if is_staff_or_teacher:
            all_preps = Exam.objects.filter(
                parent__isnull=False, is_active=True
            ).select_related('parent', 'category').prefetch_related('courses')
            for prep in all_preps:
                courses_list = list(prep.courses.all())
                c = courses_list[0] if courses_list else None
                authorized_prep_dict[prep.id] = {
                    'exam': prep,
                    'course': c
                }
        else:
            from courses.access import authorized_courses
            auth_courses = authorized_courses(user).select_related('exam', 'exam__parent', 'exam__category')
            for c in auth_courses:
                if c.exam:
                    prep = c.exam
                    authorized_prep_dict[prep.id] = {
                        'exam': prep,
                        'course': c
                    }

        authorized_preps_list = []
        for prep_id, info in authorized_prep_dict.items():
            prep = info['exam']
            c = info['course']
            authorized_preps_list.append({
                "id": prep.id,
                "name": prep.name,
                "levelId": prep.parent_id,
                "levelName": prep.parent.name if prep.parent else None,
                "categoryId": prep.category_id,
                "categoryName": prep.category.name if prep.category else None,
                "courseId": c.id if c else None,
                "courseTitle": c.title if c else None,
            })

        req_course_id = request.query_params.get('course_id')
        req_exam_id = request.query_params.get('exam') or request.query_params.get('exam_id')
        selected_prep_id = None

        if req_course_id:
            try:
                c_id = int(req_course_id)
                matched = next((info for info in authorized_prep_dict.values() if info['course'] and info['course'].id == c_id), None)
                if matched:
                    selected_prep_id = matched['exam'].id
                elif is_staff_or_teacher:
                    from courses.models import Course
                    c = Course.objects.filter(id=c_id).first()
                    if c and c.exam_id:
                        selected_prep_id = c.exam_id
                    else:
                        return Response({"error": "Course not found or has no linked syllabus."}, status=status.HTTP_404_NOT_FOUND)
                else:
                    return Response(
                        {"error": "You are not authorized to view content for this course."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            except (ValueError, TypeError):
                return Response({"error": "Invalid course_id"}, status=status.HTTP_400_BAD_REQUEST)

        elif req_exam_id:
            try:
                candidate_id = int(req_exam_id)
                if candidate_id in authorized_prep_dict or is_staff_or_teacher:
                    selected_prep_id = candidate_id
                else:
                    return Response(
                        {"error": "You are not authorized to view content for this preparation."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            except (ValueError, TypeError):
                return Response({"error": "Invalid exam_id"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            if not is_staff_or_teacher:
                from courses.access import get_student_course_context
                ctx = get_student_course_context(user)
                active_c = ctx.get('active_course')
                if active_c and active_c.get('exam_id') in authorized_prep_dict:
                    selected_prep_id = active_c['exam_id']
                elif authorized_preps_list:
                    selected_prep_id = authorized_preps_list[0]['id']
            elif authorized_preps_list:
                selected_prep_id = authorized_preps_list[0]['id']

        if not selected_prep_id:
            return Response({
                "authorizedPreparations": [],
                "selectedPreparation": None,
                "counts": {"syllabus": 0, "subjective_topicwise": 0, "objective_topicwise": 0, "revision_notes": 0, "total": 0},
                "sections": {
                    "syllabus": [],
                    "subjective_topicwise": {"standard": [], "ai": []},
                    "objective_topicwise": {"standard": [], "ai": []},
                    "revision_notes": {"subjective": [], "objective": []}
                }
            })

        selected_info = authorized_prep_dict.get(selected_prep_id)
        if not selected_info:
            prep_obj = Exam.objects.filter(pk=selected_prep_id).select_related('parent', 'category').first()
            if not prep_obj:
                return Response({"error": "Preparation not found"}, status=status.HTTP_404_NOT_FOUND)
            c = prep_obj.courses.first()
            selected_info = {'exam': prep_obj, 'course': c}

        selected_exam = selected_info['exam']
        selected_course = selected_info['course']

        from courses.services.course_access_service import CourseAccessService

        materials_qs = StudyMaterial.objects.filter(
            exam=selected_exam, status='published'
        ).select_related(
            'subject', 'chapter', 'topic', 'course', 'exam', 'exam__parent', 'exam__category'
        ).order_by('-created_at')

        if selected_course:
            materials_qs = materials_qs.filter(Q(course=selected_course) | Q(course__isnull=True))

        materials_qs = CourseAccessService.filter_notes_queryset(user, materials_qs)
        materials_qs = with_student_state(materials_qs, user)


        from core.models import AdminSettings
        if AdminSettings.get_settings().enforce_subscription_access and not is_staff_or_teacher:
            if not has_active_subscription(user):
                materials_qs = materials_qs.filter(access_type='free')

        serializer = StudyMaterialListSerializer(materials_qs, many=True, context={'request': request})
        all_materials = serializer.data

        syllabus_list = []
        subj_standard = []
        subj_ai = []
        obj_standard = []
        obj_ai = []
        rev_subjective = []
        rev_objective = []

        for m in all_materials:
            cat = m.get('content_category')
            nt = m.get('note_type')

            if cat == 'syllabus':
                syllabus_list.append(m)
            elif cat == 'subjective_topicwise':
                if nt == 'ai':
                    subj_ai.append(m)
                else:
                    subj_standard.append(m)
            elif cat == 'objective_topicwise':
                if nt == 'ai':
                    obj_ai.append(m)
                else:
                    obj_standard.append(m)
            elif cat == 'revision_notes':
                if nt == 'objective':
                    rev_objective.append(m)
                else:
                    rev_subjective.append(m)
            else:
                if m.get('material_type') == 'pdf':
                    syllabus_list.append(m)
                else:
                    subj_standard.append(m)

        counts = {
            "syllabus": len(syllabus_list),
            "subjective_topicwise": len(subj_standard) + len(subj_ai),
            "objective_topicwise": len(obj_standard) + len(obj_ai),
            "revision_notes": len(rev_subjective) + len(rev_objective),
            "total": len(all_materials)
        }

        return Response({
            "authorizedPreparations": authorized_preps_list,
            "selectedPreparation": {
                "id": selected_exam.id,
                "name": selected_exam.name,
                "levelId": selected_exam.parent_id if selected_exam.parent else None,
                "levelName": selected_exam.parent.name if selected_exam.parent else None,
                "categoryId": selected_exam.category_id if selected_exam.category else None,
                "categoryName": selected_exam.category.name if selected_exam.category else None,
                "courseId": selected_course.id if selected_course else None,
                "courseTitle": selected_course.title if selected_course else None,
            },
            "counts": counts,
            "sections": {
                "syllabus": syllabus_list,
                "subjective_topicwise": {
                    "standard": subj_standard,
                    "ai": subj_ai
                },
                "objective_topicwise": {
                    "standard": obj_standard,
                    "ai": obj_ai
                },
                "revision_notes": {
                    "subjective": rev_subjective,
                    "objective": rev_objective
                }
            }
        })


# TEACHER / ADMIN WORKFLOW VIEWS
# ==========================================
from .serializers import TeacherStudyMaterialSerializer, AdminStudyMaterialSerializer

class TeacherStudyMaterialViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TeacherStudyMaterialSerializer

    def get_queryset(self):
        from courses.models import TeacherCourseAssignment
        assigned_course_ids = TeacherCourseAssignment.objects.filter(
            teacher=self.request.user
        ).values_list('course_id', flat=True)
        queryset = StudyMaterial.objects.filter(
            Q(teacher=self.request.user) | Q(course_id__in=assigned_course_ids)
        ).distinct()

        status_filter = self.request.query_params.get('status')
        exam = self.request.query_params.get('exam')
        subject = self.request.query_params.get('subject')
        course = self.request.query_params.get('course')
        search = self.request.query_params.get('search')

        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if exam:
            queryset = queryset.filter(exam_id=exam)
        if subject:
            queryset = queryset.filter(subject_id=subject)
        if course:
            queryset = queryset.filter(course_id=course)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )

        return queryset.order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user, status='draft')

    @action(detail=False, methods=['get'])
    def stats(self, request):
        from django.db.models import Count
        qs = StudyMaterial.objects.filter(teacher=request.user)
        counts = qs.values('status').annotate(count=Count('id'))
        result = {item['status']: item['count'] for item in counts}
        return Response({
            'total': qs.count(),
            'draft': result.get('draft', 0),
            'pending_review': result.get('pending_review', 0),
            'published': result.get('published', 0),
            'changes_requested': result.get('changes_requested', 0),
            'rejected': result.get('rejected', 0),
        })

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        material = self.get_object()
        if material.status in ['draft', 'changes_requested', 'rejected']:
            material.status = 'pending_review'
            material.save()

            from core.notification_service import NotificationService
            NotificationService.notify_admins(
                notif_type='material_review',
                title='Study Material Submitted for Review',
                message=f"{request.user.get_full_name() or request.user.username} submitted '{material.title}' for review.",
                action_url='/admin-dashboard/study-materials',
            )

            return Response({"status": "Submitted for review"})
        return Response({"error": "Invalid status for submission"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        material = self.get_object()
        material.pk = None
        material.title = f"{material.title} (Copy)"
        material.status = 'draft'
        material.slug = ""
        material.save()
        return Response(TeacherStudyMaterialSerializer(material).data)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        from django.http import FileResponse
        material = self.get_object()
        if not material.file:
            return Response({"detail": "No file attached to this material."}, status=status.HTTP_404_NOT_FOUND)
        try:
            return FileResponse(
                material.file.open('rb'),
                as_attachment=True,
                filename=f"{material.slug or 'material'}.pdf"
            )
        except Exception as e:
            return Response({"detail": f"Could not read file: {e}"}, status=status.HTTP_404_NOT_FOUND)


class AdminStudyMaterialViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminStudyMaterialSerializer
    queryset = StudyMaterial.objects.all().order_by('-updated_at')

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        from django.http import FileResponse
        material = self.get_object()
        if not material.file:
            return Response({"detail": "No file attached to this material."}, status=status.HTTP_404_NOT_FOUND)
        try:
            return FileResponse(
                material.file.open('rb'),
                as_attachment=True,
                filename=f"{material.slug or 'material'}.pdf"
            )
        except Exception as e:
            return Response({"detail": f"Could not read file: {e}"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        material = self.get_object()
        if material.teacher == request.user:
            return Response({"detail": "You cannot approve your own material."}, status=status.HTTP_403_FORBIDDEN)
        material.status = 'published'
        material.save()
        return Response({"status": "Approved and published"})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        material = self.get_object()
        material.status = 'rejected'
        material.review_note = request.data.get('note', '')
        material.save()
        return Response({"status": "Rejected"})

    @action(detail=True, methods=['post'])
    def request_changes(self, request, pk=None):
        material = self.get_object()
        material.status = 'changes_requested'
        material.review_note = request.data.get('note', 'Please update the material and resubmit.')
        material.save()
        return Response({"status": "Changes requested"})
