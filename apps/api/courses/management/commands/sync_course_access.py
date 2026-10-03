"""Management command to audit and safely synchronize course access, enrollments,
and subscription course selections for existing students.

Usage:
    python manage.py sync_course_access --dry-run
    python manage.py sync_course_access --apply
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = "Audit and safely backfill missing SubscriptionCourseSelection and Enrollment rows for valid students."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate synchronization without writing changes to the database.',
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Apply verified course access updates to the database.',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        apply_changes = options.get('apply', False)

        if not dry_run and not apply_changes:
            self.stdout.write(
                self.style.WARNING("Neither --dry-run nor --apply specified. Defaulting to --dry-run.")
            )
            dry_run = True

        self.stdout.write(self.style.MIGRATE_HEADING("=== LoksewaAI Course Access Audit & Sync ==="))
        now = timezone.now()

        from core.models import User
        from subscriptions.models import Subscription, SubscriptionPayment, SubscriptionCourseSelection
        from courses.models import Course, Enrollment, CourseApplication
        from courses.services.course_access_service import CourseAccessService

        students = User.objects.filter(role='student').order_by('id')
        self.stdout.write(f"Auditing {students.count()} student account(s)...\n")

        proposed_selections = []
        proposed_enrollments = []
        ambiguous_cases = []

        # 1. Inspect Approved Payments
        approved_payments = SubscriptionPayment.objects.filter(status='APPROVED').select_related(
            'student', 'plan', 'plan__course', 'subscription'
        ).prefetch_related('plan__eligible_courses')

        for payment in approved_payments:
            sub = payment.subscription
            plan = payment.plan
            student = payment.student

            courses_to_link = set()

            if plan.package_type == 'SINGLE':
                if plan.course:
                    courses_to_link.add(plan.course)
                elif plan.eligible_courses.count() == 1:
                    courses_to_link.add(plan.eligible_courses.first())

            elif plan.package_type == 'BUNDLE':
                for c in plan.eligible_courses.filter(status='published'):
                    courses_to_link.add(c)

            # Check linked CourseApplications
            apps = CourseApplication.objects.filter(subscription_payment=payment).select_related('course')
            for app in apps:
                courses_to_link.add(app.course)

            if not courses_to_link and plan.package_type != 'ALL_ACCESS':
                ambiguous_cases.append({
                    'student': student.username,
                    'payment_id': payment.id,
                    'plan': plan.name,
                    'reason': 'Payment approved but no linked course could be resolved from plan or applications.'
                })
                continue

            for course in courses_to_link:
                # Check selection on payment
                p_sel_exists = SubscriptionCourseSelection.objects.filter(payment=payment, course=course).exists()
                if not p_sel_exists:
                    proposed_selections.append({
                        'payment': payment,
                        'subscription': sub,
                        'course': course,
                        'reason': f"Backfill payment #{payment.id} selection for {course.title}"
                    })

                # Check selection on subscription
                if sub:
                    s_sel_exists = SubscriptionCourseSelection.objects.filter(subscription=sub, course=course).exists()
                    if not s_sel_exists:
                        proposed_selections.append({
                            'payment': payment,
                            'subscription': sub,
                            'course': course,
                            'reason': f"Backfill subscription #{sub.id} selection for {course.title}"
                        })

                # Check enrollment
                expiry = sub.expiry_date if sub else (now + timezone.timedelta(days=30))
                enrollment = Enrollment.objects.filter(student=student, course=course).first()
                if not enrollment:
                    proposed_enrollments.append({
                        'student': student,
                        'course': course,
                        'status': 'active',
                        'expires_at': expiry,
                        'reason': f"Missing enrollment for approved payment #{payment.id} / sub #{sub.id if sub else 'N/A'}"
                    })
                elif enrollment.status != 'active' or (sub and enrollment.expires_at and sub.expiry_date > enrollment.expires_at):
                    proposed_enrollments.append({
                        'student': student,
                        'course': course,
                        'status': 'active',
                        'expires_at': max(enrollment.expires_at or now, sub.expiry_date) if sub else enrollment.expires_at,
                        'reason': f"Update enrollment #{enrollment.id} expiry to match subscription"
                    })

        # 2. Inspect Active Subscriptions without Payments (e.g. Admin Grants)
        active_subs = Subscription.objects.filter(
            status='ACTIVE', expiry_date__gt=now, payment__isnull=True
        ).select_related('student', 'plan', 'plan__course').prefetch_related('plan__eligible_courses')

        for sub in active_subs:
            plan = sub.plan
            student = sub.student
            courses_to_link = set()

            if plan.package_type == 'SINGLE':
                if plan.course:
                    courses_to_link.add(plan.course)
                elif plan.eligible_courses.count() == 1:
                    courses_to_link.add(plan.eligible_courses.first())
            elif plan.package_type == 'BUNDLE':
                for c in plan.eligible_courses.filter(status='published'):
                    courses_to_link.add(c)

            # Check existing selections on sub
            existing_sels = SubscriptionCourseSelection.objects.filter(subscription=sub).select_related('course')
            for sel in existing_sels:
                courses_to_link.add(sel.course)

            for course in courses_to_link:
                enrollment = Enrollment.objects.filter(student=student, course=course).first()
                if not enrollment:
                    proposed_enrollments.append({
                        'student': student,
                        'course': course,
                        'status': 'active',
                        'expires_at': sub.expiry_date,
                        'reason': f"Missing enrollment for active grant subscription #{sub.id}"
                    })

        # Summary output
        self.stdout.write("--- Audit Results ---")
        self.stdout.write(f"Proposed Course Selections to backfill: {len(proposed_selections)}")
        for s in proposed_selections:
            self.stdout.write(f"  + CourseSelection: {s['course'].title} -> {s['reason']}")

        self.stdout.write(f"\nProposed Enrollments to create/update: {len(proposed_enrollments)}")
        for e in proposed_enrollments:
            self.stdout.write(f"  + Enrollment: {e['student'].username} in {e['course'].title} (expires: {e['expires_at']}) -> {e['reason']}")

        if ambiguous_cases:
            self.stdout.write(self.style.WARNING(f"\nAmbiguous cases flagged for manual admin review: {len(ambiguous_cases)}"))
            for ac in ambiguous_cases:
                self.stdout.write(f"  ! Student: {ac['student']}, Payment: #{ac['payment_id']}, Plan: {ac['plan']} -> {ac['reason']}")
        else:
            self.stdout.write(self.style.SUCCESS("\nNo ambiguous student cases found."))

        # Apply changes if requested
        if apply_changes and not dry_run:
            self.stdout.write(self.style.MIGRATE_HEADING("\nApplying database updates atomically..."))
            with transaction.atomic():
                selections_created = 0
                for s in proposed_selections:
                    _, created = SubscriptionCourseSelection.objects.get_or_create(
                        payment=s['payment'],
                        subscription=s['subscription'],
                        course=s['course'],
                    )
                    if created:
                        selections_created += 1

                enrollments_touched = 0
                for e in proposed_enrollments:
                    en, created = Enrollment.objects.get_or_create(
                        student=e['student'],
                        course=e['course'],
                        defaults={
                            'status': e['status'],
                            'expires_at': e['expires_at'],
                        }
                    )
                    if not created:
                        en.status = e['status']
                        if e['expires_at'] and (not en.expires_at or e['expires_at'] > en.expires_at):
                            en.expires_at = e['expires_at']
                        en.save(update_fields=['status', 'expires_at'])
                    enrollments_touched += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully applied updates: {selections_created} selections created, {enrollments_touched} enrollments created/updated."
                )
            )
        elif dry_run:
            self.stdout.write(self.style.NOTICE("\nDry-run complete. No changes were committed to the database."))
