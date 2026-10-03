"""
Comprehensive tests for Student Examination & Practice Access Control.

Verifies:
1. Student enrolled in Course A (Civil) sees ONLY Course A exams.
2. Student enrolled in Course A CANNOT retrieve, start, view paper, or view attempts for Course B (Computer) exams (IDOR protection).
3. Student enrolled in Course B (Computer) sees ONLY Course B exams.
4. Multi-course student enrolled in Course A + B sees both, and ?course_id= scopes correctly. Unrelated course returns empty.
5. Student with expired/unverified enrollment cannot access premium exams.
6. Admin retains access.
7. Upcoming mock exam countdown respects student course authorization.
8. Subjective practice sets and model exams respect student course authorization.
"""
from datetime import timedelta
from django.utils import timezone
from rest_framework.test import APITestCase
from core.models import User, AdminSettings
from courses.models import Course, Enrollment
from exams.models import (
    ExamCategory, Exam, Paper, Subject, Chapter, Topic, Question,
    Examination, ExaminationQuestion, ExaminationAttempt, SubjectivePracticeSet,
    ExaminationRequest, QuestionMastery, Bookmark,
)
from subscriptions.models import Subscription, SubscriptionPlan


class StudentExamAccessControlTestCase(APITestCase):
    def setUp(self):
        # 1. Academic Structure
        self.category = ExamCategory.objects.create(name='PSC Technical')
        self.level_5 = Exam.objects.create(category=self.category, name='5th Level Exam', is_active=True, status='active')

        # Exam A: Civil Sub Engineer
        self.exam_civil = Exam.objects.create(
            category=self.category, name='Civil Sub Engineer', parent=self.level_5, is_active=True, status='active'
        )
        self.paper_civil = Paper.objects.create(exam=self.exam_civil, name='Civil Paper 1')
        self.subject_civil = Subject.objects.create(paper=self.paper_civil, name='Structural Engineering')
        self.chapter_civil = Chapter.objects.create(subject=self.subject_civil, title='Concrete Technology')
        self.topic_civil = Topic.objects.create(chapter=self.chapter_civil, name='Mix Design')

        # Exam B: Computer Operator
        self.exam_computer = Exam.objects.create(
            category=self.category, name='Computer Operator', parent=self.level_5, is_active=True, status='active'
        )
        self.paper_computer = Paper.objects.create(exam=self.exam_computer, name='Computer Paper 1')
        self.subject_computer = Subject.objects.create(paper=self.paper_computer, name='Operating Systems')
        self.chapter_computer = Chapter.objects.create(subject=self.subject_computer, title='Process Management')
        self.topic_computer = Topic.objects.create(chapter=self.chapter_computer, name='Deadlocks')

        # Exam C: Geomatic Engineer (Unrelated)
        self.exam_geomatic = Exam.objects.create(
            category=self.category, name='Geomatic Engineer', parent=self.level_5, is_active=True, status='active'
        )
        self.paper_geomatic = Paper.objects.create(exam=self.exam_geomatic, name='Survey Paper 1')
        self.subject_geomatic = Subject.objects.create(paper=self.paper_geomatic, name='GIS')
        self.chapter_geomatic = Chapter.objects.create(subject=self.subject_geomatic, title='Coordinates')
        self.topic_geomatic = Topic.objects.create(chapter=self.chapter_geomatic, name='Projections')

        # 2. Courses
        self.course_civil = Course.objects.create(
            title='PSC 5th Level Civil Engineering', slug='psc-5th-civil', status='published', exam=self.exam_civil
        )
        self.course_computer = Course.objects.create(
            title='PSC 5th Level Computer Operator', slug='psc-5th-computer', status='published', exam=self.exam_computer
        )
        self.course_geomatic = Course.objects.create(
            title='PSC 5th Level Geomatic Engineering', slug='psc-5th-geomatic', status='published', exam=self.exam_geomatic
        )

        # 3. Questions
        self.q_civil = Question.objects.create(
            topic=self.topic_civil, question_type='mcq', status='approved', text='Civil Q1',
            option_a='A', option_b='B', option_c='C', option_d='D', correct_option='A', marks=1
        )
        self.q_computer = Question.objects.create(
            topic=self.topic_computer, question_type='mcq', status='approved', text='Computer Q1',
            option_a='A', option_b='B', option_c='C', option_d='D', correct_option='B', marks=1
        )
        self.q_geomatic = Question.objects.create(
            topic=self.topic_geomatic, question_type='mcq', status='approved', text='Geomatic Q1',
            option_a='A', option_b='B', option_c='C', option_d='D', correct_option='C', marks=1
        )

        # 4. Examinations
        self.civil_exam = Examination.objects.create(
            title='Civil Mock Exam 1',
            exam_type='mock',
            objective_category='model',
            category=self.category,
            exam=self.exam_civil,
            course=self.course_civil,
            status='published',
            time_limit=60,
            total_marks=50,
            passing_marks=20
        )
        ExaminationQuestion.objects.create(examination=self.civil_exam, question=self.q_civil, order=1, marks=1)

        self.computer_exam = Examination.objects.create(
            title='Computer / IT Model Exam',
            exam_type='mock',
            objective_category='model',
            category=self.category,
            exam=self.exam_computer,
            course=self.course_computer,
            status='published',
            time_limit=60,
            total_marks=50,
            passing_marks=20
        )
        ExaminationQuestion.objects.create(examination=self.computer_exam, question=self.q_computer, order=1, marks=1)

        self.geomatic_exam = Examination.objects.create(
            title='Geomatic Survey Model Exam',
            exam_type='mock',
            objective_category='model',
            category=self.category,
            exam=self.exam_geomatic,
            course=self.course_geomatic,
            status='published',
            time_limit=60,
            total_marks=50,
            passing_marks=20
        )
        ExaminationQuestion.objects.create(examination=self.geomatic_exam, question=self.q_geomatic, order=1, marks=1)

        # 5. Users
        self.student_civil = User.objects.create_user(username='civil_stu', password='pw', role='student')
        self.student_computer = User.objects.create_user(username='comp_stu', password='pw', role='student')
        self.student_multi = User.objects.create_user(username='multi_stu', password='pw', role='student')
        self.student_expired = User.objects.create_user(username='expired_stu', password='pw', role='student')
        self.admin_user = User.objects.create_user(username='admin_boss', password='pw', role='admin')

        # 6. Plan & Subscriptions
        self.plan = SubscriptionPlan.objects.create(name='Standard Plan', duration=30, price='1000')

        # Enrollments
        now = timezone.now()
        # Civil student
        Enrollment.objects.create(student=self.student_civil, course=self.course_civil, status='active', expires_at=now + timedelta(days=30))
        Subscription.objects.create(student=self.student_civil, plan=self.plan, status='ACTIVE', start_date=now, expiry_date=now + timedelta(days=30))

        # Computer student
        Enrollment.objects.create(student=self.student_computer, course=self.course_computer, status='active', expires_at=now + timedelta(days=30))
        Subscription.objects.create(student=self.student_computer, plan=self.plan, status='ACTIVE', start_date=now, expiry_date=now + timedelta(days=30))

        # Multi-course student (Civil + Computer)
        Enrollment.objects.create(student=self.student_multi, course=self.course_civil, status='active', expires_at=now + timedelta(days=30))
        Enrollment.objects.create(student=self.student_multi, course=self.course_computer, status='active', expires_at=now + timedelta(days=30))
        Subscription.objects.create(student=self.student_multi, plan=self.plan, status='ACTIVE', start_date=now, expiry_date=now + timedelta(days=30))

        # Expired student
        Enrollment.objects.create(student=self.student_expired, course=self.course_civil, status='active', expires_at=now - timedelta(days=5))
        Subscription.objects.create(student=self.student_expired, plan=self.plan, status='EXPIRED', start_date=now - timedelta(days=35), expiry_date=now - timedelta(days=5))

        # Enforce subscription access
        s = AdminSettings.get_settings()
        s.enforce_subscription_access = True
        s.save()

    def test_civil_student_sees_only_civil_exams(self):
        """Civil student must see Civil mock exams and NOT Computer or Geomatic exams."""
        self.client.force_authenticate(self.student_civil)
        res = self.client.get('/api/student/exams/')
        self.assertEqual(res.status_code, 200)
        exam_ids = [e['id'] for e in res.data]
        self.assertIn(self.civil_exam.id, exam_ids)
        self.assertNotIn(self.computer_exam.id, exam_ids)
        self.assertNotIn(self.geomatic_exam.id, exam_ids)

    def test_civil_student_cannot_access_computer_exam_by_id(self):
        """Civil student attempting to retrieve Computer exam directly must be blocked (404/403)."""
        self.client.force_authenticate(self.student_civil)
        # Detail
        res = self.client.get(f'/api/student/exams/{self.computer_exam.id}/')
        self.assertIn(res.status_code, (403, 404))

        # Start
        res = self.client.post(f'/api/student/exams/{self.computer_exam.id}/start/')
        self.assertIn(res.status_code, (403, 404))

        # Question Paper
        res = self.client.get(f'/api/student/exams/{self.computer_exam.id}/question_paper/')
        self.assertIn(res.status_code, (403, 404))

    def test_computer_student_sees_only_computer_exams(self):
        """Computer student must see Computer mock exams and NOT Civil exams."""
        self.client.force_authenticate(self.student_computer)
        res = self.client.get('/api/student/exams/')
        self.assertEqual(res.status_code, 200)
        exam_ids = [e['id'] for e in res.data]
        self.assertIn(self.computer_exam.id, exam_ids)
        self.assertNotIn(self.civil_exam.id, exam_ids)
        self.assertNotIn(self.geomatic_exam.id, exam_ids)

    def test_multi_course_student_can_see_both_and_switch_context(self):
        """Multi-course student sees both, and filtering with ?course_id= scopes correctly."""
        self.client.force_authenticate(self.student_multi)
        
        # Unfiltered or all authorized
        res = self.client.get('/api/student/exams/')
        self.assertEqual(res.status_code, 200)
        exam_ids = [e['id'] for e in res.data]
        self.assertIn(self.civil_exam.id, exam_ids)
        self.assertIn(self.computer_exam.id, exam_ids)
        self.assertNotIn(self.geomatic_exam.id, exam_ids)

        # Scoped to Civil course
        res_civil = self.client.get(f'/api/student/exams/?course_id={self.course_civil.id}')
        self.assertEqual(res_civil.status_code, 200)
        civil_ids = [e['id'] for e in res_civil.data]
        self.assertIn(self.civil_exam.id, civil_ids)
        self.assertNotIn(self.computer_exam.id, civil_ids)

        # Scoped to Computer course
        res_comp = self.client.get(f'/api/student/exams/?course_id={self.course_computer.id}')
        self.assertEqual(res_comp.status_code, 200)
        comp_ids = [e['id'] for e in res_comp.data]
        self.assertIn(self.computer_exam.id, comp_ids)
        self.assertNotIn(self.civil_exam.id, comp_ids)

    def test_practice_exam_tree_respects_course_scope(self):
        """The practice syllabus tree must honor the active course filter, not all authorized exams."""
        self.client.force_authenticate(self.student_multi)

        res = self.client.get(f'/api/exams/?course_id={self.course_civil.id}')
        self.assertEqual(res.status_code, 200)

        tree_exam_ids = [item['id'] for item in res.data]
        self.assertIn(self.exam_civil.id, tree_exam_ids)
        self.assertNotIn(self.exam_computer.id, tree_exam_ids)

        civil_exam = next(item for item in res.data if item['id'] == self.exam_civil.id)
        subject_names = [subject['name'] for subject in civil_exam.get('subjects', [])]
        self.assertIn(self.subject_civil.name, subject_names)
        self.assertNotIn(self.subject_computer.name, subject_names)

        # Attempting to request unauthorized course (Geomatic) returns 0 exams (empty list)
        res_geo = self.client.get(f'/api/student/exams/?course_id={self.course_geomatic.id}')
        self.assertEqual(res_geo.status_code, 200)
        self.assertEqual(len(res_geo.data), 0)

    def test_weak_topic_quick_start_excludes_other_revision_signals(self):
        """Weak Topic is a focused Master Bank draw, not the mixed revision queue."""
        now = timezone.now()
        QuestionMastery.objects.create(
            user=self.student_multi,
            question=self.q_civil,
            times_answered=3,
            times_incorrect=3,
            consecutive_incorrect=3,
            last_attempted_at=now,
            next_review_at=now + timedelta(days=1),
        )
        QuestionMastery.objects.create(
            user=self.student_multi,
            question=self.q_computer,
            times_answered=1,
            times_incorrect=1,
            consecutive_incorrect=1,
            last_attempted_at=now,
            next_review_at=now + timedelta(days=1),
        )

        self.client.force_authenticate(self.student_multi)
        response = self.client.post(
            '/api/practice-sessions/start_revision/',
            {'focus': 'weak_topics'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        question_ids = [question['id'] for question in response.data['questions']]
        self.assertEqual(question_ids, [self.q_civil.id])

    def test_topicwise_test_list_is_published_and_course_scoped(self):
        civil_test = Examination.objects.create(
            title='Civil Topic Test', exam_type='subject', category=self.category,
            exam=self.exam_civil, course=self.course_civil, subject=self.subject_civil,
            topic=self.topic_civil, status='published', total_questions=1,
            time_limit=15, total_marks=1,
        )
        Examination.objects.create(
            title='Computer Topic Test', exam_type='subject', category=self.category,
            exam=self.exam_computer, course=self.course_computer, subject=self.subject_computer,
            topic=self.topic_computer, status='published', total_questions=1,
            time_limit=15, total_marks=1,
        )
        Examination.objects.create(
            title='Civil Draft Topic Test', exam_type='subject', category=self.category,
            exam=self.exam_civil, course=self.course_civil, subject=self.subject_civil,
            topic=self.topic_civil, status='draft', total_questions=1,
            time_limit=15, total_marks=1,
        )

        self.client.force_authenticate(self.student_civil)
        response = self.client.get(
            f'/api/student/exams/?course_id={self.course_civil.id}&topicwise=true'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([exam['id'] for exam in response.data], [civil_test.id])
        self.assertEqual(response.data[0]['topic_id'], self.topic_civil.id)

    def test_mock_exam_requires_admin_approval_before_attempt_creation(self):
        self.client.force_authenticate(self.student_civil)
        request_url = '/api/student/exam-requests/'
        first = self.client.post(request_url, {'examination': self.civil_exam.id}, format='json')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.data['status'], 'pending')

        duplicate = self.client.post(request_url, {'examination': self.civil_exam.id}, format='json')
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(ExaminationRequest.objects.filter(student=self.student_civil, examination=self.civil_exam).count(), 1)

        blocked = self.client.post(f'/api/student/exams/{self.civil_exam.id}/start/')
        self.assertEqual(blocked.status_code, 403)
        self.assertFalse(ExaminationAttempt.objects.filter(student=self.student_civil, examination=self.civil_exam).exists())

        self.client.force_authenticate(self.admin_user)
        approved = self.client.post(f'/api/admin/exam-requests/{first.data["id"]}/approve/')
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data['status'], 'approved')

        self.client.force_authenticate(self.student_civil)
        started = self.client.post(f'/api/student/exams/{self.civil_exam.id}/start/')
        self.assertEqual(started.status_code, 201)
        self.assertTrue(ExaminationAttempt.objects.filter(student=self.student_civil, examination=self.civil_exam).exists())

    def test_admin_rejection_reason_is_persisted_and_student_cannot_review_requests(self):
        self.client.force_authenticate(self.student_civil)
        created = self.client.post(
            '/api/student/exam-requests/', {'examination': self.civil_exam.id}, format='json'
        )
        request_id = created.data['id']
        self.assertEqual(self.client.post(f'/api/admin/exam-requests/{request_id}/approve/').status_code, 403)

        self.client.force_authenticate(self.admin_user)
        rejected = self.client.post(
            f'/api/admin/exam-requests/{request_id}/reject/',
            {'rejection_reason': 'Please select the next scheduled session.'},
            format='json',
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data['status'], 'rejected')
        self.assertEqual(rejected.data['rejection_reason'], 'Please select the next scheduled session.')

        self.client.force_authenticate(self.student_civil)
        listed = self.client.get('/api/student/exam-requests/')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data[0]['rejection_reason'], 'Please select the next scheduled session.')

    def test_subjective_exam_request_requires_admin_approval_before_start(self):
        from exams.models import ExaminationRequest

        subjective_exam = Examination.objects.create(
            title='Civil Subjective Live Exam', exam_type='subjective',
            category=self.category, exam=self.exam_civil, course=self.course_civil,
            status='published', time_limit=90, total_marks=10,
        )
        from django.core.files.base import ContentFile
        subjective_exam.question_paper_pdf.save("test_paper.pdf", ContentFile(b"%PDF-1.4 dummy pdf"))
        ExaminationQuestion.objects.create(
            examination=subjective_exam,
            question=Question.objects.create(
                topic=self.topic_civil, question_type='subjective', status='approved',
                text='Explain reinforced concrete.', model_answer='Reference.', marks=10,
            ),
            order=1, marks=10,
        )
        self.client.force_authenticate(self.student_civil)

        request = self.client.post(
            '/api/student/exam-requests/', {'examination': subjective_exam.id}, format='json'
        )
        self.assertEqual(request.status_code, 201)
        blocked = self.client.post(f'/api/student/exams/{subjective_exam.id}/start/')
        self.assertEqual(blocked.status_code, 403)

        self.client.force_authenticate(self.admin_user)
        approved = self.client.post(f'/api/admin/exam-requests/{request.data["id"]}/approve/')
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(ExaminationRequest.objects.get(pk=request.data['id']).status, 'approved')

        self.client.force_authenticate(self.student_civil)
        started = self.client.post(f'/api/student/exams/{subjective_exam.id}/start/')
        self.assertEqual(started.status_code, 201)
        self.assertTrue(ExaminationAttempt.objects.filter(
            student=self.student_civil, examination=subjective_exam
        ).exists())

    def test_student_can_request_subjective_live_exam_before_examination_exists(self):
        self.client.force_authenticate(self.student_civil)
        payload = {
            'request_type': 'subjective_live',
            'academic_exam': self.exam_civil.id,
            'course': self.course_civil.id,
            'subject': self.subject_civil.id,
            'topic': self.topic_civil.id,
        }

        created = self.client.post('/api/student/exam-requests/', payload, format='json')

        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['request_type'], 'subjective_live')
        self.assertIsNone(created.data['examination'])
        self.assertEqual(created.data['academic_exam'], self.exam_civil.id)
        repeated = self.client.post('/api/student/exam-requests/', payload, format='json')
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.data['id'], created.data['id'])

        unauthorized = self.client.post(
            '/api/student/exam-requests/',
            {**payload, 'course': self.course_computer.id, 'academic_exam': self.exam_computer.id},
            format='json',
        )
        self.assertEqual(unauthorized.status_code, 403)

    def test_expert_solution_uses_real_question_data_and_is_hidden_during_live_attempts(self):
        self.client.force_authenticate(self.student_civil)
        solution_url = f'/api/student/exams/{self.civil_exam.id}/expert-solution/'
        solution = self.client.get(solution_url)
        self.assertEqual(solution.status_code, 200)
        self.assertEqual(solution.data['solutions'][0]['correct_option'], 'A')

        ExaminationAttempt.objects.create(
            examination=self.civil_exam, student=self.student_civil, status='in-progress'
        )
        active_solution = self.client.get(solution_url)
        self.assertEqual(active_solution.status_code, 403)

        live_exam = Examination.objects.create(
            title='Scheduled Civil Live Exam', exam_type='mock', objective_category='live',
            category=self.category, exam=self.exam_civil, course=self.course_civil, status='published',
        )
        live_solution = self.client.get(f'/api/student/exams/{live_exam.id}/expert-solution/')
        self.assertEqual(live_solution.status_code, 403)

    def test_saved_practice_and_bookmarks_respect_the_selected_course(self):
        civil_bookmark = Bookmark.objects.create(user=self.student_multi, question=self.q_civil)
        Bookmark.objects.create(user=self.student_multi, question=self.q_computer)
        Bookmark.objects.create(user=self.student_multi, question=self.q_geomatic)
        self.client.force_authenticate(self.student_multi)

        list_response = self.client.get(f'/api/bookmarks/?course_id={self.course_civil.id}')
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([item['id'] for item in list_response.data], [civil_bookmark.id])
        bookmark_question = list_response.data[0]['question_detail']
        self.assertNotIn('correct_option', bookmark_question)
        self.assertNotIn('explanation', bookmark_question)

        session_response = self.client.post(
            '/api/practice-sessions/saved/',
            {'course_id': self.course_civil.id},
            format='json',
        )
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_response.data['session']['mode'], 'saved')
        self.assertEqual(session_response.data['total_questions'], 1)
        self.assertEqual([question['id'] for question in session_response.data['questions']], [self.q_civil.id])

    def test_recently_incorrect_uses_latest_persisted_exam_answers_and_course_scope(self):
        from exams.models import StudentAnswer

        now = timezone.now()
        civil_wrong = ExaminationAttempt.objects.create(
            examination=self.civil_exam,
            student=self.student_multi,
            status='submitted',
            submitted_at=now - timedelta(minutes=2),
        )
        StudentAnswer.objects.create(
            attempt=civil_wrong,
            question=self.q_civil,
            selected_option='A',
            is_correct=False,
        )
        computer_wrong = ExaminationAttempt.objects.create(
            examination=self.computer_exam,
            student=self.student_multi,
            status='submitted',
            submitted_at=now - timedelta(minutes=1),
        )
        StudentAnswer.objects.create(
            attempt=computer_wrong,
            question=self.q_computer,
            selected_option='A',
            is_correct=False,
        )

        self.client.force_authenticate(self.student_multi)
        first = self.client.post(
            '/api/practice-sessions/start_revision/',
            {'focus': 'recent_mistakes', 'course_id': self.course_civil.id},
            format='json',
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual([q['id'] for q in first.data['questions']], [self.q_civil.id])

        civil_correct = ExaminationAttempt.objects.create(
            examination=self.civil_exam,
            student=self.student_multi,
            status='submitted',
            submitted_at=now,
        )
        StudentAnswer.objects.create(
            attempt=civil_correct,
            question=self.q_civil,
            selected_option='B',
            is_correct=True,
        )
        second = self.client.post(
            '/api/practice-sessions/start_revision/',
            {'focus': 'recent_mistakes', 'course_id': self.course_civil.id},
            format='json',
        )
        self.assertEqual(second.status_code, 400)

    def test_topicwise_active_attempt_hides_answers_and_refresh_keeps_server_deadline(self):
        self.client.force_authenticate(self.student_civil)
        ExaminationRequest.objects.create(
            student=self.student_civil,
            examination=self.civil_exam,
            status='approved',
            reviewed_by=self.admin_user,
            reviewed_at=timezone.now(),
        )

        started = self.client.post(f'/api/student/exams/{self.civil_exam.id}/start/')
        self.assertEqual(started.status_code, 201)
        attempt_id = started.data['id']
        questions = self.client.get(f'/api/student/exam-attempts/{attempt_id}/questions/')
        self.assertEqual(questions.status_code, 200)
        self.assertNotIn('correct_option', questions.data[0])
        self.assertNotIn('explanation', questions.data[0])

        started_at = timezone.now() - timedelta(seconds=30)
        ExaminationAttempt.objects.filter(pk=attempt_id).update(started_at=started_at)
        first_state = self.client.get(f'/api/student/exam-attempts/{attempt_id}/state/')
        second_state = self.client.get(f'/api/student/exam-attempts/{attempt_id}/state/')

        self.assertEqual(first_state.status_code, 200)
        self.assertEqual(second_state.status_code, 200)
        self.assertLessEqual(second_state.data['remaining_seconds'], first_state.data['remaining_seconds'])
        self.assertLessEqual(first_state.data['remaining_seconds'] - second_state.data['remaining_seconds'], 2)
        self.assertEqual(ExaminationAttempt.objects.get(pk=attempt_id).started_at, started_at)

    def test_attempt_access_control(self):
        """A student cannot access an attempt on an exam they are not authorized for."""
        # Create an attempt for Computer exam by Computer student
        comp_attempt = ExaminationAttempt.objects.create(
            examination=self.computer_exam,
            student=self.student_computer,
            status='in-progress'
        )

        # Civil student tries to read or modify Computer attempt
        self.client.force_authenticate(self.student_civil)
        res = self.client.get(f'/api/student/exam-attempts/{comp_attempt.id}/')
        self.assertIn(res.status_code, (403, 404))

        res_ans = self.client.post(f'/api/student/exam-attempts/{comp_attempt.id}/answer/', {'question': self.q_computer.id, 'selected_option': 'B'})
        self.assertIn(res_ans.status_code, (403, 404))

    def test_expired_student_cannot_access_exams(self):
        """Student with expired subscription gets 403 or empty list."""
        self.client.force_authenticate(self.student_expired)
        res = self.client.get('/api/student/exams/')
        # With HasActiveSubscription permission, it returns 403
        self.assertEqual(res.status_code, 403)

    def test_upcoming_mock_exam_schedule_isolation(self):
        """Upcoming mock countdown endpoint returns only exams for the student's authorized course."""
        # Create an upcoming live mock exam for Computer / IT
        now = timezone.now()
        upcoming_comp_exam = Examination.objects.create(
            title='Upcoming IT Live Exam',
            exam_type='mock',
            objective_category='live',
            category=self.category,
            exam=self.exam_computer,
            course=self.course_computer,
            status='published',
            start_time=now + timedelta(days=2),
            end_time=now + timedelta(days=3),
            time_limit=60,
            total_marks=50,
            passing_marks=20
        )

        # Civil student queries upcoming mock exam
        self.client.force_authenticate(self.student_civil)
        res_civil = self.client.get('/api/student/mock-exams/upcoming/')
        self.assertEqual(res_civil.status_code, 200)
        # Should NOT return any computer exam
        mock_exam_civil = res_civil.data.get('mock_exam')
        if mock_exam_civil:
            self.assertNotEqual(mock_exam_civil.get('id'), upcoming_comp_exam.id)
            self.assertNotEqual(mock_exam_civil.get('id'), self.computer_exam.id)
            self.assertEqual(mock_exam_civil.get('id'), self.civil_exam.id)

        # Computer student queries upcoming mock exam
        self.client.force_authenticate(self.student_computer)
        res_comp = self.client.get('/api/student/mock-exams/upcoming/')
        self.assertEqual(res_comp.status_code, 200)
        self.assertIn(res_comp.data.get('status'), ('LIVE', 'UPCOMING'))
        self.assertIsNotNone(res_comp.data.get('mock_exam'))
        # Must be a computer exam, never a civil exam
        self.assertIn(res_comp.data.get('mock_exam', {}).get('id'), (upcoming_comp_exam.id, self.computer_exam.id))
        self.assertNotEqual(res_comp.data.get('mock_exam', {}).get('id'), self.civil_exam.id)

    def test_subjective_practice_set_isolation(self):
        """Subjective practice sets must only be returned for authorized exams."""
        ps_civil = SubjectivePracticeSet.objects.create(
            title='Civil Subjective Practice Set',
            exam=self.exam_civil,
            subject=self.subject_civil,
            status='published'
        )
        ps_comp = SubjectivePracticeSet.objects.create(
            title='Computer Subjective Practice Set',
            exam=self.exam_computer,
            subject=self.subject_computer,
            status='published'
        )

        self.client.force_authenticate(self.student_civil)
        res = self.client.get('/api/subjective-practice-sets/')
        self.assertEqual(res.status_code, 200)
        ids = [p['id'] for p in res.data]
        self.assertIn(ps_civil.id, ids)
        self.assertNotIn(ps_comp.id, ids)

    def test_custom_exam_excluded_from_mock_banner_and_list(self):
        """A personal custom exam generated on-demand must NEVER appear in the
        mock exam list or the LIVE NOW countdown banner."""
        # Create an on-demand custom exam created by student_civil
        custom_exam = Examination.objects.create(
            title='Custom Exam - 2026-09-24 15:57',
            exam_type='custom',
            objective_category='custom',
            category=self.category,
            exam=self.exam_civil,
            course=self.course_civil,
            status='published',
            created_by=self.student_civil,
            time_limit=10,
            total_marks=10,
            passing_marks=4
        )

        # 1. Upcoming mock banner should NEVER return a custom exam
        self.client.force_authenticate(self.student_civil)
        res_upcoming = self.client.get('/api/student/mock-exams/upcoming/')
        self.assertEqual(res_upcoming.status_code, 200)
        mock_data = res_upcoming.data.get('mock_exam')
        if mock_data:
            self.assertNotEqual(mock_data.get('id'), custom_exam.id)
            self.assertNotEqual(mock_data.get('exam_type'), 'custom')

        # 2. Student mock exam list should NEVER list custom exams in the public catalog
        res_list = self.client.get('/api/student/exams/')
        self.assertEqual(res_list.status_code, 200)
        list_ids = [e['id'] for e in res_list.data]
        self.assertNotIn(custom_exam.id, list_ids)

        # 3. Creator CAN still fetch single detail (for taking the attempt / review)
        res_detail = self.client.get(f'/api/student/exams/{custom_exam.id}/')
        self.assertEqual(res_detail.status_code, 200)
        self.assertEqual(res_detail.data['id'], custom_exam.id)

        # 4. Another student CANNOT fetch detail of this custom exam (IDOR)
        self.client.force_authenticate(self.student_computer)
        res_detail_other = self.client.get(f'/api/student/exams/{custom_exam.id}/')
        self.assertEqual(res_detail_other.status_code, 404)

    def test_academic_hierarchy_scoped_to_enrolled_course(self):
        """The custom-builder academic hierarchy endpoint must return ONLY exams
        for which the student has an active course enrollment."""
        self.client.force_authenticate(self.student_civil)
        res = self.client.get('/api/student/exams/academic-hierarchy/')
        self.assertEqual(res.status_code, 200)

        # Flatten all exams returned in the hierarchy
        returned_exam_ids = []
        for cat in res.data:
            for ex in cat.get('exams', []):
                returned_exam_ids.append(ex['id'])

        # Must include Civil Sub Engineer (enrolled course exam)
        self.assertIn(self.exam_civil.id, returned_exam_ids)
        # Must NOT include Computer Operator or Geomatic Engineer
        self.assertNotIn(self.exam_computer.id, returned_exam_ids)
        self.assertNotIn(self.exam_geomatic.id, returned_exam_ids)

        # Testing with explicit course_id parameter
        res_scoped = self.client.get(f'/api/student/exams/academic-hierarchy/?course_id={self.course_civil.id}')
        self.assertEqual(res_scoped.status_code, 200)
        scoped_ids = [ex['id'] for cat in res_scoped.data for ex in cat.get('exams', [])]
        self.assertIn(self.exam_civil.id, scoped_ids)
        self.assertNotIn(self.exam_computer.id, scoped_ids)

        # Testing with unauthorized course_id returns empty
        res_unauth = self.client.get(f'/api/student/exams/academic-hierarchy/?course_id={self.course_computer.id}')
        self.assertEqual(res_unauth.status_code, 200)
        self.assertEqual(res_unauth.data, [])

