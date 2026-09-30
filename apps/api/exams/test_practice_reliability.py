"""Student Practice: pagination, answer persistence, duplicate protection,
score/XP correctness, access control and query cost - through the real
endpoints and models (no mocked questions)."""
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from core.models import User
from exams.models import (
    ExamCategory, Exam, Paper, Subject, Chapter, Topic, Question,
    PracticeSession, QuestionAttempt, QuestionMastery, Bookmark,
)

STUDY = '/api/practice-sessions/study/'


class PracticeBase(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='stu', password='pw', role='student')
        self.other = User.objects.create_user(username='stu2', password='pw', role='student')
        cat = ExamCategory.objects.create(name='Loksewa')
        self.exam = Exam.objects.create(category=cat, name='Kharidar')
        paper = Paper.objects.create(exam=self.exam, name='First')
        self.subject = Subject.objects.create(paper=paper, name='GK')
        chapter = Chapter.objects.create(subject=self.subject, title='Geo')
        self.topic = Topic.objects.create(chapter=chapter, name='Mountains')
        # The student owns the course for this exam, so its practice is authorised.
        from courses.models import Course, Enrollment
        self.owned_course = Course.objects.create(title='Kharidar', slug='kharidar', status='published', exam=self.exam)
        Enrollment.objects.create(student=self.student, course=self.owned_course)
        self.client.force_authenticate(self.student)

    def make_questions(self, n, **kw):
        out = []
        for i in range(n):
            out.append(Question.objects.create(
                topic=self.topic, question_type='mcq', status=kw.get('status', 'approved'),
                text=f'Question {i + 1}', option_a='a', option_b='b', option_c='c', option_d='d',
                correct_option='B', explanation=f'Because {i + 1}', hint=kw.get('hint', ''), marks=1,
            ))
        return out

    def start(self, **extra):
        data = {'topic': self.topic.id, 'subject': self.subject.id, 'exam': self.exam.id}
        data.update(extra)
        return self.client.post(STUDY, data, format='json')

    def answer(self, session_id, question_id, option, client=None):
        return (client or self.client).post(
            f'/api/practice-sessions/{session_id}/answer/',
            {'question_id': question_id, 'selected_option': option, 'is_marked_for_review': False},
            format='json',
        )


class TopicPaginationTests(PracticeBase):
    def test_first_page_holds_only_twenty_questions(self):
        self.make_questions(45)
        data = self.start().json()
        self.assertEqual(len(data['questions']), 20)
        self.assertEqual(data['total_questions'], 45)
        self.assertEqual(data['total_pages'], 3)
        self.assertEqual(data['page'], 1)
        self.assertEqual(len(data['attempts']), 20)

    def test_page_size_ten_is_supported_and_junk_falls_back_to_twenty(self):
        self.make_questions(45)
        self.assertEqual(len(self.start(page_size=10).json()['questions']), 10)
        sid = self.start().json()['session']['id']
        r = self.client.get(f'/api/practice-sessions/{sid}/questions/?page=1&page_size=500').json()
        self.assertEqual(r['page_size'], 20)
        self.assertEqual(len(r['questions']), 20)

    def test_pages_do_not_overlap_and_cover_the_whole_set_in_stable_order(self):
        self.make_questions(45)
        first = self.start().json()
        sid = first['session']['id']
        seen = [q['id'] for q in first['questions']]
        for page in (2, 3):
            seen += [q['id'] for q in self.client.get(f'/api/practice-sessions/{sid}/questions/?page={page}').json()['questions']]
        self.assertEqual(len(seen), 45)
        self.assertEqual(len(set(seen)), 45)  # no duplicates, none missing
        self.assertEqual(sorted(seen), sorted(Question.objects.values_list('id', flat=True)))
        # Asking again returns the same questions in the same order - no reshuffle.
        again = [q['id'] for q in self.client.get(f'/api/practice-sessions/{sid}/questions/?page=1').json()['questions']]
        self.assertEqual(again, seen[:20])

    def test_last_page_is_short_and_out_of_range_page_is_clamped(self):
        self.make_questions(45)
        sid = self.start().json()['session']['id']
        last = self.client.get(f'/api/practice-sessions/{sid}/questions/?page=3').json()
        self.assertEqual(len(last['questions']), 5)
        beyond = self.client.get(f'/api/practice-sessions/{sid}/questions/?page=99').json()
        self.assertEqual(beyond['page'], 3)

    def test_starting_again_resumes_the_same_session_and_selects_nothing_new(self):
        self.make_questions(30)
        a = self.start().json()
        b = self.start().json()
        self.assertEqual(a['session']['id'], b['session']['id'])
        self.assertTrue(b['resumed'])
        self.assertEqual(PracticeSession.objects.filter(user=self.student, mode='study').count(), 1)
        self.assertEqual(QuestionAttempt.objects.filter(session_id=a['session']['id']).count(), 30)

    def test_resume_lands_on_the_page_of_the_first_untouched_question(self):
        qs = self.make_questions(45)
        sid = self.start().json()['session']['id']
        ids = list(QuestionAttempt.objects.filter(session_id=sid).order_by('id').values_list('question_id', flat=True))
        for qid in ids[:25]:                       # answer through question 25
            self.answer(sid, qid, 'b')
        resumed = self.start().json()
        self.assertEqual(resumed['page'], 2)       # question 26 lives on page 2
        self.assertEqual(resumed['resume_index'], 25)
        self.assertEqual(resumed['stats']['answered'], 25)

    def test_stats_cover_the_whole_session_not_just_the_loaded_page(self):
        self.make_questions(45)
        first = self.start().json()
        sid = first['session']['id']
        page3 = self.client.get(f'/api/practice-sessions/{sid}/questions/?page=3').json()
        self.answer(sid, page3['questions'][0]['id'], 'b')      # correct, on page 3
        self.answer(sid, page3['questions'][1]['id'], 'a')      # wrong, on page 3
        stats = self.client.get(f'/api/practice-sessions/{sid}/questions/?page=1').json()['stats']
        self.assertEqual((stats['answered'], stats['correct'], stats['wrong'], stats['accuracy']), (2, 1, 1, 50))

    def test_unanswered_questions_never_reveal_their_answer_key(self):
        self.make_questions(3)
        data = self.start().json()
        for q in data['questions']:
            self.assertNotIn('correct_option', q)
            self.assertNotIn('explanation', q)
        for a in data['attempts']:
            self.assertNotIn('correct_option', a)

    def test_study_can_reveal_a_hint_without_answer_or_explanation(self):
        self.make_questions(1, hint='Recall the river source.')

        question = self.start().json()['questions'][0]

        self.assertEqual(question['hint'], 'Recall the river source.')
        self.assertNotIn('correct_option', question)
        self.assertNotIn('explanation', question)

    def test_only_approved_objective_questions_are_offered(self):
        self.make_questions(2)
        self.make_questions(2, status='draft')
        self.make_questions(1, status='pending_review')
        Question.objects.create(topic=self.topic, question_type='subjective', status='approved',
                                text='Explain', model_answer='x', marks=5)
        data = self.start().json()
        self.assertEqual(data['total_questions'], 2)
        for q in data['questions']:
            self.assertTrue(q['option_a'])

    def test_no_questions_gives_a_clear_400(self):
        r = self.start()
        self.assertEqual(r.status_code, 400)
        self.assertIn('No approved questions', r.json()['detail'])

    def test_starting_a_big_topic_costs_a_bounded_number_of_queries(self):
        """The attempts must be created in bulk: one INSERT each took ~20s on
        a 100-question topic against the hosted database."""
        self.make_questions(60)
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.start().status_code, 200)
        self.assertLess(len(ctx), 25, [q['sql'][:80] for q in ctx.captured_queries])


class TopicStudyShuffleTests(PracticeBase):
    def test_shuffle_is_persisted_per_session_and_keeps_options_and_canonical_numbers(self):
        questions = self.make_questions(4)
        with mock.patch('random.shuffle', side_effect=lambda items: items.reverse()):
            first = self.start(shuffle_questions=True).json()

        self.assertTrue(first['session']['shuffle_questions'])
        self.assertEqual([q['id'] for q in first['questions']], [q.id for q in reversed(questions)])
        self.assertEqual([q['canonical_number'] for q in first['questions']], [4, 3, 2, 1])
        self.assertEqual(
            [(q['option_a'], q['option_b'], q['option_c'], q['option_d']) for q in first['questions']],
            [('a', 'b', 'c', 'd')] * 4,
        )

        resumed = self.start(shuffle_questions=False).json()
        self.assertEqual(resumed['session']['id'], first['session']['id'])
        self.assertTrue(resumed['session']['shuffle_questions'])
        self.assertEqual([q['id'] for q in resumed['questions']], [q.id for q in reversed(questions)])

    def test_topic_study_is_not_capped_at_five_hundred_questions(self):
        Question.objects.bulk_create([
            Question(
                topic=self.topic, question_type='mcq', status='approved',
                text=f'Question {index}', option_a='a', option_b='b',
                option_c='c', option_d='d', correct_option='B',
            )
            for index in range(501)
        ])

        response = self.start().json()

        self.assertEqual(response['total_questions'], 501)
        self.assertEqual(QuestionAttempt.objects.filter(session_id=response['session']['id']).count(), 501)


class SavedQuestionOrderingTests(PracticeBase):
    def test_saved_questions_default_to_chronological_custom_order_and_reset(self):
        questions = self.make_questions(3)
        bookmarks = [Bookmark.objects.create(user=self.student, question=question) for question in questions]
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        for offset, bookmark in enumerate(bookmarks):
            Bookmark.objects.filter(pk=bookmark.pk).update(created_at=now + timedelta(minutes=offset))

        url = f'/api/bookmarks/?course_id={self.owned_course.id}'
        initial = self.client.get(url)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual([item['id'] for item in initial.data], [bookmark.id for bookmark in bookmarks])
        self.assertEqual(initial.data[0]['custom_order'], None)
        self.assertEqual(initial.data[0]['saved_at'], initial.data[0]['created_at'])

        order_url = f'/api/bookmarks/order/?course_id={self.owned_course.id}'
        reordered = self.client.patch(order_url, {'bookmark_ids': [b.id for b in reversed(bookmarks)]}, format='json')
        self.assertEqual(reordered.status_code, 200)
        self.assertEqual(
            [item['id'] for item in self.client.get(url).data],
            [bookmark.id for bookmark in reversed(bookmarks)],
        )

        reset = self.client.post(f'/api/bookmarks/reset-order/?course_id={self.owned_course.id}', {}, format='json')
        self.assertEqual(reset.status_code, 200)
        self.assertEqual([item['id'] for item in self.client.get(url).data], [bookmark.id for bookmark in bookmarks])


class AnswerTests(PracticeBase):
    def setUp(self):
        super().setUp()
        self.qs = self.make_questions(5)
        data = self.start().json()
        self.sid = data['session']['id']
        self.qid = data['questions'][0]['id']

    def test_correct_answer_is_persisted_and_scored(self):
        r = self.answer(self.sid, self.qid, 'b').json()
        self.assertTrue(r['is_correct'])
        self.assertEqual(r['correct_option'], 'B')
        self.assertTrue(r['explanation'].startswith('Because'))
        att = QuestionAttempt.objects.get(session_id=self.sid, question_id=self.qid)
        self.assertEqual((att.selected_option, att.is_correct, att.is_viewed), ('b', True, True))
        self.assertIsNotNone(att.viewed_at)
        self.assertEqual(att.session.user_id, self.student.id)

    def test_wrong_answer_reports_the_correct_option(self):
        r = self.answer(self.sid, self.qid, 'a').json()
        self.assertFalse(r['is_correct'])
        self.assertEqual(r['correct_option'], 'B')
        self.assertFalse(QuestionAttempt.objects.get(session_id=self.sid, question_id=self.qid).is_correct)

    def test_uppercase_option_letters_are_accepted(self):
        self.assertTrue(self.answer(self.sid, self.qid, 'B').json()['is_correct'])

    def test_invalid_option_is_rejected_and_nothing_is_saved(self):
        r = self.answer(self.sid, self.qid, 'z')
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(QuestionAttempt.objects.get(session_id=self.sid, question_id=self.qid).selected_option)

    def test_repeating_the_same_answer_does_not_double_count(self):
        for _ in range(3):
            self.assertEqual(self.answer(self.sid, self.qid, 'b').status_code, 200)
        self.assertEqual(QuestionAttempt.objects.filter(session_id=self.sid, question_id=self.qid).count(), 1)
        m = QuestionMastery.objects.get(user=self.student, question_id=self.qid)
        self.assertEqual((m.times_answered, m.times_correct), (1, 1))

    def test_first_answer_wins_in_an_instant_feedback_session(self):
        self.answer(self.sid, self.qid, 'a')                  # wrong
        r = self.answer(self.sid, self.qid, 'b').json()       # a second tab tries to change it
        self.assertTrue(r['already_answered'])
        self.assertFalse(r['is_correct'])                     # still the stored result
        att = QuestionAttempt.objects.get(session_id=self.sid, question_id=self.qid)
        self.assertEqual(att.selected_option, 'a')
        m = QuestionMastery.objects.get(user=self.student, question_id=self.qid)
        self.assertEqual((m.times_answered, m.times_incorrect), (1, 1))

    def test_unknown_question_and_junk_ids_are_a_404_not_a_500(self):
        self.assertEqual(self.answer(self.sid, 999999, 'a').status_code, 404)
        self.assertEqual(self.answer(self.sid, 'abc', 'a').status_code, 404)

    def test_view_answer_works_without_answering_and_is_not_an_attempt(self):
        r = self.client.post(f'/api/practice-sessions/{self.sid}/reveal/', {'question_id': self.qid}, format='json')
        self.assertEqual(r.json()['correct_option'], 'B')
        self.assertTrue(r.json()['explanation'])
        att = QuestionAttempt.objects.get(session_id=self.sid, question_id=self.qid)
        self.assertIsNone(att.selected_option)
        self.assertTrue(att.is_viewed)
        self.assertFalse(QuestionMastery.objects.filter(user=self.student).exists())

    def test_answered_state_survives_a_reload(self):
        self.answer(self.sid, self.qid, 'a')
        state = {a['question_id']: a for a in self.start().json()['attempts']}[self.qid]
        self.assertEqual((state['selected_option'], state['is_correct'], state['correct_option']), ('a', False, 'B'))

    def test_flexible_session_never_leaks_the_answer_key(self):
        r = self.client.post('/api/practice-sessions/', {
            'exam': self.exam.id, 'subject': self.subject.id, 'topic': self.topic.id,
            'mode': 'flexible', 'total_questions': 5,
        }, format='json')
        self.assertEqual(r.status_code, 200)
        sid, qid = r.json()['session']['id'], r.json()['questions'][0]['id']
        res = self.answer(sid, qid, 'a').json()
        self.assertEqual(res, {'status': 'success'})
        # ...and a flexible answer may be changed until submit.
        self.answer(sid, qid, 'b')
        self.assertEqual(QuestionAttempt.objects.get(session_id=sid, question_id=qid).selected_option, 'b')

    def test_answering_a_completed_session_is_refused(self):
        self.client.post(f'/api/practice-sessions/{self.sid}/submit/', {'time_taken_seconds': 5}, format='json')
        r = self.answer(self.sid, self.qid, 'b')
        self.assertEqual(r.status_code, 400)
        self.assertIn('already completed', r.json()['detail'])


class SubmitTests(PracticeBase):
    def setUp(self):
        super().setUp()
        self.make_questions(4)
        data = self.start().json()
        self.sid = data['session']['id']
        self.ids = [q['id'] for q in data['questions']]

    def submit(self):
        return self.client.post(f'/api/practice-sessions/{self.sid}/submit/', {'time_taken_seconds': 12}, format='json')

    def test_result_is_calculated_from_persisted_attempts(self):
        self.answer(self.sid, self.ids[0], 'b')   # correct
        self.answer(self.sid, self.ids[1], 'b')   # correct
        self.answer(self.sid, self.ids[2], 'a')   # wrong
        s = self.submit().json()['session']       # 4th skipped
        self.assertEqual((s['correct_count'], s['incorrect_count'], s['unanswered_count']), (2, 1, 1))
        self.assertEqual(s['score'], 2)
        self.assertAlmostEqual(s['accuracy'], 66.666, places=1)
        self.assertTrue(s['completed'])
        self.assertEqual(s['time_taken_seconds'], 12)

    def test_xp_is_awarded_once_however_many_times_submit_is_sent(self):
        self.answer(self.sid, self.ids[0], 'b')
        self.answer(self.sid, self.ids[1], 'b')
        with mock.patch('gamification.services.award_xp') as award:
            for _ in range(3):
                self.assertEqual(self.submit().status_code, 200)
        self.assertEqual(award.call_count, 1)
        self.assertEqual(award.call_args[0][1], 2)

    def test_submit_is_idempotent_and_returns_the_full_result_each_time(self):
        self.answer(self.sid, self.ids[0], 'b')
        first = self.submit().json()
        second = self.submit().json()
        self.assertEqual(first['session'], second['session'])
        self.assertEqual(len(second['attempts']), 4)

    def test_junk_time_taken_is_a_400(self):
        r = self.client.post(f'/api/practice-sessions/{self.sid}/submit/', {'time_taken_seconds': 'abc'}, format='json')
        self.assertEqual(r.status_code, 400)


class AccessControlTests(PracticeBase):
    def setUp(self):
        super().setUp()
        self.make_questions(3)
        data = self.start().json()
        self.sid = data['session']['id']
        self.qid = data['questions'][0]['id']
        self.intruder = APITestCase.client_class()
        self.intruder.force_authenticate(self.other)

    def test_another_student_cannot_read_answer_reveal_or_submit_my_session(self):
        base = f'/api/practice-sessions/{self.sid}'
        self.assertEqual(self.intruder.get(f'{base}/').status_code, 404)
        self.assertEqual(self.intruder.get(f'{base}/questions/').status_code, 404)
        self.assertEqual(self.answer(self.sid, self.qid, 'b', client=self.intruder).status_code, 404)
        self.assertEqual(self.intruder.post(f'{base}/reveal/', {'question_id': self.qid}, format='json').status_code, 404)
        self.assertEqual(self.intruder.post(f'{base}/view/', {'question_id': self.qid}, format='json').status_code, 404)
        self.assertEqual(self.intruder.post(f'{base}/submit/', {}, format='json').status_code, 404)
        # ...and none of it changed my attempt.
        att = QuestionAttempt.objects.get(session_id=self.sid, question_id=self.qid)
        self.assertIsNone(att.selected_option)
        self.assertFalse(PracticeSession.objects.get(id=self.sid).completed)

    def test_session_list_only_contains_my_own_sessions(self):
        ids = [s['id'] for s in self.intruder.get('/api/practice-sessions/').json()['results']
               ] if 'results' in self.intruder.get('/api/practice-sessions/').json() else \
            [s['id'] for s in self.intruder.get('/api/practice-sessions/').json()]
        self.assertNotIn(self.sid, ids)

    def test_a_student_cannot_edit_or_delete_their_own_session_scores(self):
        url = f'/api/practice-sessions/{self.sid}/'
        self.assertEqual(self.client.patch(url, {'accuracy': 100, 'correct_count': 99}, format='json').status_code, 405)
        self.assertEqual(self.client.put(url, {}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(PracticeSession.objects.get(id=self.sid).correct_count, 0)

    def test_anonymous_requests_are_rejected(self):
        anon = APITestCase.client_class()
        self.assertEqual(anon.post(STUDY, {'topic': self.topic.id}, format='json').status_code, 401)
        self.assertEqual(anon.get(f'/api/practice-sessions/{self.sid}/questions/').status_code, 401)


class DailyAndRevisionTests(PracticeBase):
    def test_daily_practice_stays_a_single_session_per_day_and_resumes_with_state(self):
        self.make_questions(25)
        first = self.client.post('/api/practice-sessions/daily/', {}, format='json').json()
        self.assertEqual(len(first['questions']), 20)          # whole set, not paginated
        self.assertNotIn('page', first)
        sid, qid = first['session']['id'], first['questions'][0]['id']
        self.answer(sid, qid, 'a')
        again = self.client.post('/api/practice-sessions/daily/', {}, format='json').json()
        self.assertEqual(again['session']['id'], sid)
        self.assertTrue(again['resumed'])
        state = {a['question_id']: a for a in again['attempts']}[qid]
        self.assertEqual(state['selected_option'], 'a')
        self.assertEqual(PracticeSession.objects.filter(user=self.student, mode='daily').count(), 1)

    def test_revision_with_no_history_says_so(self):
        r = self.client.post('/api/practice-sessions/start_revision/', {}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('No revision questions yet', r.json()['detail'])


class CourseAndSubscriptionAccessTests(PracticeBase):
    def test_practice_for_a_course_requires_an_active_enrollment(self):
        self.make_questions(3)
        from courses.models import Course
        course = Course.objects.create(title='Kharidar Prep', exam=self.exam) if 'exam' in [f.name for f in Course._meta.fields] \
            else Course.objects.create(title='Kharidar Prep')
        r = self.client.post('/api/practice-sessions/', {
            'course': course.id, 'exam': self.exam.id, 'mode': 'flexible', 'total_questions': 3,
        }, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertIn('not enrolled', r.json()['detail'])
        self.assertFalse(PracticeSession.objects.filter(user=self.student).exists())

    def test_package_enforcement_blocks_students_without_a_package_but_not_when_off(self):
        from core.models import AdminSettings
        self.make_questions(3)
        self.assertEqual(self.start().status_code, 200)            # enforcement off (default)
        settings = AdminSettings.get_settings()
        settings.enforce_subscription_access = True
        settings.save()
        r = self.start()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get('code'), 'subscription_required')
        sid = PracticeSession.objects.filter(user=self.student).first().id
        self.assertEqual(self.answer(sid, Question.objects.first().id, 'b').status_code, 403)


class SyllabusListQueryCostTests(PracticeBase):
    """The Practice setup screens load /api/exams/ (exam -> subject -> chapter
    -> topic). It used to run one query per topic, subject and chapter."""

    def test_exam_tree_is_loaded_in_a_bounded_number_of_queries_with_the_same_shape(self):
        from exams.models import UserTopicProgress
        for e in range(3):
            exam = Exam.objects.create(category=self.exam.category, name=f'Exam {e}')
            from courses.models import Course, Enrollment
            Enrollment.objects.create(student=self.student, course=Course.objects.create(
                title=f'Course {e}', slug=f'course-tree-{e}', status='published', exam=exam))
            paper = Paper.objects.create(exam=exam, name='P1')
            for s in range(2):
                subject = Subject.objects.create(paper=paper, name=f'Subject {e}-{s}')
                for c in range(2):
                    chapter = Chapter.objects.create(subject=subject, title=f'Unit {c}')
                    for t in range(3):
                        topic = Topic.objects.create(chapter=chapter, name=f'Topic {e}-{s}-{c}-{t}')
                        if t == 0:
                            UserTopicProgress.objects.create(user=self.student, topic=topic, status='in-progress',
                                                             progress=40, accuracy=75)
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get('/api/exams/')
        self.assertEqual(r.status_code, 200)
        self.assertLess(len(ctx), 17, [q['sql'][:70] for q in ctx.captured_queries])   # tree prefetch + exam authorisation reads
        rows = r.json()['results'] if isinstance(r.json(), dict) else r.json()
        exam0 = next(x for x in rows if x['title'] == 'Exam 0')
        self.assertEqual(len(exam0['subjects']), 2)
        topics = [t for u in exam0['subjects'][0]['units'] for t in u['topics']]
        self.assertEqual(len(topics), 6)
        first = next(t for t in topics if t['name'].endswith('-0-0-0'))
        self.assertEqual((first['status'], first['progress'], first['accuracy']), ('in-progress', 40, 75))
        untouched = next(t for t in topics if t['name'].endswith('-0-0-1'))
        self.assertEqual((untouched['status'], untouched['progress'], untouched['accuracy']), ('not-started', 0, None))
