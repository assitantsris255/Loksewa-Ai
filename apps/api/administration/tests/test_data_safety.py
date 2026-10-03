import os
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import User
from exams.models import (
    ExamCategory, Exam, Examination, ExaminationAttempt, Question
)
from administration.models import TrashItem, DatabaseBackup, AuditLog
from administration.backup_service import BackupService


class DataSafetySystemTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='safety_admin', password='pw', role='admin', is_staff=True
        )
        self.super_admin = User.objects.create_user(
            username='safety_superadmin', password='pw', role='super-admin', is_staff=True, is_superuser=True
        )
        self.student = User.objects.create_user(
            username='safety_student', password='pw', role='student'
        )

        self.category = ExamCategory.objects.create(name='PSC Technical')
        self.exam = Exam.objects.create(category=self.category, name='Civil Engineer')
        self.client.force_authenticate(user=self.admin)

    def test_safe_delete_examination_moves_to_trash(self):
        examination = Examination.objects.create(
            category=self.category,
            exam=self.exam,
            title='Test Civil Exam 2026',
            exam_type='mock',
            status='draft',
            total_marks=100,
            passing_marks=40,
            time_limit=60,
        )

        response = self.client.delete(f'/api/admin/exams/{examination.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Examination should NOT be physically deleted; status changed to archived
        examination.refresh_from_db()
        self.assertEqual(examination.status, 'archived')

        # TrashItem should exist
        trash_item = TrashItem.objects.filter(
            app_label='exams', model_name='examination', object_id=str(examination.id)
        ).first()
        self.assertIsNotNone(trash_item)
        self.assertEqual(trash_item.title, 'Test Civil Exam 2026')
        self.assertFalse(trash_item.is_restored)
        self.assertFalse(trash_item.is_permanent_deleted)

        # AuditLog should be recorded
        audit = AuditLog.objects.filter(action='DELETE', entity_id=str(examination.id)).first()
        self.assertIsNotNone(audit)

    def test_cannot_permanently_delete_protected_examination(self):
        examination = Examination.objects.create(
            category=self.category,
            exam=self.exam,
            title='Protected Civil Exam',
            exam_type='mock',
            status='published',
            total_marks=100,
            passing_marks=40,
            time_limit=60,
        )
        # Create an attempt on this exam
        ExaminationAttempt.objects.create(
            examination=examination,
            student=self.student,
            status='submitted',
            score=75,
            submitted_at=timezone.now(),
        )

        # Safe delete the exam
        del_resp = self.client.delete(f'/api/admin/exams/{examination.id}/')
        self.assertEqual(del_resp.status_code, status.HTTP_200_OK)

        trash_item = TrashItem.objects.get(object_id=str(examination.id), model_name='examination')
        self.assertTrue(trash_item.is_protected)
        self.assertIn('attempt', trash_item.protection_reason.lower())

        # Now try to permanently delete as Super Admin
        self.client.force_authenticate(user=self.super_admin)
        perm_resp = self.client.post(
            f'/api/admin/data-safety/trash/{trash_item.id}/permanent-delete/',
            {'confirmation': 'DELETE PERMANENTLY'},
            format='json'
        )
        self.assertEqual(perm_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('rejected', perm_resp.data.get('error', '').lower())

        # Record still exists in DB
        self.assertTrue(Examination.objects.filter(pk=examination.pk).exists())

    def test_restore_trashed_item(self):
        examination = Examination.objects.create(
            category=self.category,
            exam=self.exam,
            title='Restorable Civil Exam',
            exam_type='mock',
            status='draft',
            total_marks=50,
            passing_marks=20,
            time_limit=45,
        )

        # Safe delete
        self.client.delete(f'/api/admin/exams/{examination.id}/')
        examination.refresh_from_db()
        self.assertEqual(examination.status, 'archived')

        trash_item = TrashItem.objects.get(object_id=str(examination.id), model_name='examination')

        # Restore item
        restore_resp = self.client.post(f'/api/admin/data-safety/trash/{trash_item.id}/restore/')
        self.assertEqual(restore_resp.status_code, status.HTTP_200_OK)

        # Examination active/draft status restored
        examination.refresh_from_db()
        self.assertNotEqual(examination.status, 'archived')

        # Trash item marked restored
        trash_item.refresh_from_db()
        self.assertTrue(trash_item.is_restored)

        # Audit recorded
        audit = AuditLog.objects.filter(action='RESTORE', entity_id=str(examination.id)).first()
        self.assertIsNotNone(audit)

    def test_permanent_delete_eligible_item_by_super_admin(self):
        question = Question.objects.create(
            category=self.category,
            exam=self.exam,
            text='Temporary sample test question?',
            question_type='mcq',
            status='draft',
        )

        del_resp = self.client.delete(f'/api/admin/questions/{question.id}/')
        self.assertEqual(del_resp.status_code, status.HTTP_200_OK)

        trash_item = TrashItem.objects.get(object_id=str(question.id), model_name='question')
        self.assertFalse(trash_item.is_protected)

        # Normal admin attempting permanent delete must be rejected
        admin_perm_resp = self.client.post(
            f'/api/admin/data-safety/trash/{trash_item.id}/permanent-delete/',
            {'confirmation': 'DELETE PERMANENTLY'},
            format='json'
        )
        self.assertEqual(admin_perm_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('super admin', admin_perm_resp.data.get('error', '').lower())

        # Super admin with incorrect confirmation is rejected
        self.client.force_authenticate(user=self.super_admin)
        bad_confirm_resp = self.client.post(
            f'/api/admin/data-safety/trash/{trash_item.id}/permanent-delete/',
            {'confirmation': 'delete'},
            format='json'
        )
        self.assertEqual(bad_confirm_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('confirmation', bad_confirm_resp.data.get('error', '').lower())

        # Super admin with exact confirmation 'DELETE PERMANENTLY' succeeds
        good_perm_resp = self.client.post(
            f'/api/admin/data-safety/trash/{trash_item.id}/permanent-delete/',
            {'confirmation': 'DELETE PERMANENTLY'},
            format='json'
        )
        self.assertEqual(good_perm_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(good_perm_resp.data.get('success'))

        # Question physically removed
        self.assertFalse(Question.objects.filter(pk=question.pk).exists())

        # Trash item marked permanently deleted
        trash_item.refresh_from_db()
        self.assertTrue(trash_item.is_permanent_deleted)

    def test_backup_creation_and_verification(self):
        # Admin creates backup
        create_resp = self.client.post(
            '/api/admin/data-safety/backups/',
            {'name': 'Test TestBackup', 'backup_type': 'manual'},
            format='json'
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        backup_id = create_resp.data['id']

        backup = DatabaseBackup.objects.get(id=backup_id)
        self.assertEqual(backup.status, 'verified')
        self.assertTrue(backup.is_verified)
        self.assertTrue(os.path.exists(backup.file_path))
        self.assertTrue(backup.file_path.endswith('.json.gz'))
        self.assertGreater(backup.size_bytes, 0)
        self.assertGreater(len(backup.checksum_sha256), 20)

        # Verify endpoint works
        verify_resp = self.client.post(f'/api/admin/data-safety/backups/{backup_id}/verify/')
        self.assertEqual(verify_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_resp.data['verified'])

        # Clean up created file
        try:
            if os.path.exists(backup.file_path):
                os.remove(backup.file_path)
        except OSError:
            pass

    def test_overview_and_recovery_endpoints(self):
        overview_resp = self.client.get('/api/admin/data-safety/overview/')
        self.assertEqual(overview_resp.status_code, status.HTTP_200_OK)
        self.assertIn('trash_items_count', overview_resp.data)
        self.assertIn('backup_status', overview_resp.data)
        self.assertIn('r2_configured', overview_resp.data)
        self.assertIn('storage_backend', overview_resp.data)
        self.assertIn('retention_days', overview_resp.data)

        recovery_resp = self.client.get('/api/admin/data-safety/recovery/')
        self.assertEqual(recovery_resp.status_code, status.HTTP_200_OK)
        self.assertIn('recovery_points', recovery_resp.data)
        self.assertIn('pre_restore_snapshots', recovery_resp.data)

    def test_toggle_protect_backup(self):
        backup = BackupService.create_backup(backup_type='manual', user=self.admin, custom_name='Test Shield Backup')
        self.assertFalse(backup.is_protected)

        # Standard admin cannot toggle protection
        resp_admin = self.client.post(f'/api/admin/data-safety/backups/{backup.id}/toggle-protect/')
        self.assertEqual(resp_admin.status_code, status.HTTP_403_FORBIDDEN)

        # Super admin can toggle protection
        self.client.force_authenticate(user=self.super_admin)
        resp_super = self.client.post(f'/api/admin/data-safety/backups/{backup.id}/toggle-protect/')
        self.assertEqual(resp_super.status_code, status.HTTP_200_OK)
        self.assertTrue(resp_super.data['is_protected'])

        backup.refresh_from_db()
        self.assertTrue(backup.is_protected)

        # Toggle back
        resp_super_off = self.client.post(f'/api/admin/data-safety/backups/{backup.id}/toggle-protect/')
        self.assertEqual(resp_super_off.status_code, status.HTTP_200_OK)
        self.assertFalse(resp_super_off.data['is_protected'])

        # Cleanup file
        if os.path.exists(backup.file_path):
            try:
                os.remove(backup.file_path)
            except OSError:
                pass

    def test_retention_cleanup_preserves_latest_and_shielded_backups(self):
        now = timezone.now()
        expired_date = now - timezone.timedelta(days=40)

        # 1. Old expired backup (eligible for cleanup)
        old_backup = BackupService.create_backup(backup_type='daily', user=self.admin, custom_name='Old Backup 1')
        old_backup.created_at = expired_date
        old_backup.retention_until = expired_date + timezone.timedelta(days=30)
        old_backup.status = 'verified'
        old_backup.save()

        # 2. Old expired backup BUT shielded / protected
        shielded_backup = BackupService.create_backup(backup_type='daily', user=self.admin, custom_name='Old Shielded Backup')
        shielded_backup.created_at = expired_date
        shielded_backup.retention_until = expired_date + timezone.timedelta(days=30)
        shielded_backup.is_protected = True
        shielded_backup.status = 'verified'
        shielded_backup.save()

        # 3. Latest verified backup (created now, should never be pruned)
        latest_backup = BackupService.create_backup(backup_type='daily', user=self.admin, custom_name='Latest Backup')
        latest_backup.status = 'verified'
        latest_backup.save()

        # Run cleanup
        result = BackupService.cleanup_expired_backups()
        self.assertGreaterEqual(result['cleaned_count'], 1)

        # Old backup should be marked expired
        old_backup.refresh_from_db()
        self.assertEqual(old_backup.status, 'expired')

        # Shielded backup MUST remain verified
        shielded_backup.refresh_from_db()
        self.assertEqual(shielded_backup.status, 'verified')
        self.assertTrue(shielded_backup.is_protected)

        # Latest backup MUST remain verified
        latest_backup.refresh_from_db()
        self.assertEqual(latest_backup.status, 'verified')

        # Clean up files
        for b in [old_backup, shielded_backup, latest_backup]:
            if os.path.exists(b.file_path):
                try:
                    os.remove(b.file_path)
                except OSError:
                    pass

    def test_create_database_backup_management_command(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        # First execution creates daily backup
        call_command('create_database_backup', type='daily', stdout=out)
        output = out.getvalue()
        self.assertIn('Status: VERIFIED', output)

        # Second execution without --force detects idempotency and skips
        out2 = StringIO()
        call_command('create_database_backup', type='daily', stdout=out2)
        output2 = out2.getvalue()
        self.assertIn('already exists for today', output2)

        # With --force it creates a new snapshot
        out3 = StringIO()
        call_command('create_database_backup', type='daily', force=True, stdout=out3)
        output3 = out3.getvalue()
        self.assertIn('Status: VERIFIED', output3)

    def test_verify_and_cleanup_management_commands(self):
        from django.core.management import call_command
        from io import StringIO

        out_verify = StringIO()
        call_command('verify_database_backups', stdout=out_verify)
        self.assertIn('Auditing', out_verify.getvalue())
        self.assertIn('Audit completed', out_verify.getvalue())

        out_cleanup = StringIO()
        call_command('cleanup_database_backups', stdout=out_cleanup)
        self.assertIn('database backup retention cleanup', out_cleanup.getvalue().lower())

    def test_post_restore_integrity_checks(self):
        checks = BackupService.run_post_restore_integrity_checks()
        self.assertTrue(checks['passed'])
        self.assertTrue(checks['metrics']['users_exist'])
        self.assertTrue(checks['metrics']['categories_exist'])

    def test_r2_storage_service_unit_and_mock(self):
        from unittest.mock import patch, MagicMock
        from django.core.exceptions import ValidationError
        from administration.r2_storage_service import R2StorageService

        # When credentials are not configured
        with patch.object(R2StorageService, 'is_configured', return_value=False):
            self.assertFalse(R2StorageService.is_configured())
            with self.assertRaises(ValidationError):
                R2StorageService.upload_file('dummy.gz', 'key.gz')

        # When credentials are configured and S3 responds
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {'ETag': '"abc123etag"'}
        mock_s3.head_object.return_value = {
            'ContentLength': 1024,
            'ETag': '"abc123etag"',
            'Metadata': {'sha256': 'testhash'},
        }

        # Mock streaming body for download / sha256 verification
        mock_body = MagicMock()
        mock_body.read.side_effect = [b"chunk1", b"chunk2", b""]
        mock_s3.get_object.return_value = {'Body': mock_body}

        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.json.gz', delete=False) as tf:
            tf.write(b"test backup content")
            temp_path = tf.name

        try:
            with patch.object(R2StorageService, 'is_configured', return_value=True), \
                 patch.object(R2StorageService, 'get_client', return_value=mock_s3):

                # Test upload
                res = R2StorageService.upload_file(temp_path, 'loksewaai/backups/test.gz', metadata={'sha256': 'testhash'})
                self.assertIsNotNone(res)
                self.assertEqual(res['etag'], 'abc123etag')
                self.assertEqual(res['size_bytes'], 19)

                # Test exists
                self.assertTrue(R2StorageService.exists('loksewaai/backups/test.gz'))

                # Test delete
                self.assertTrue(R2StorageService.delete_object('loksewaai/backups/test.gz'))

                # Test verify object integrity
                import hashlib
                expected_hash = hashlib.sha256(b"chunk1chunk2").hexdigest()
                integrity = R2StorageService.verify_object_integrity('loksewaai/backups/test.gz', expected_hash)
                self.assertTrue(integrity['valid'])
                self.assertEqual(integrity['calculated_sha256'], expected_hash)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


