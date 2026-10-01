"""Tests for the Google Drive storage integration. Every Drive HTTP call is
mocked - these must never depend on, or reach, the real Google account."""
from unittest.mock import MagicMock, patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from core import google_drive
from core.storage_backends import GoogleDriveStorage


DRIVE_ENV = {
    'GOOGLE_DRIVE_CLIENT_ID': 'test-client-id',
    'GOOGLE_DRIVE_CLIENT_SECRET': 'test-client-secret',
    'GOOGLE_DRIVE_REFRESH_TOKEN': 'test-refresh-token',
    'GOOGLE_DRIVE_ROOT_FOLDER_ID': 'root-folder-id',
}


class IsConfiguredTests(TestCase):
    @patch.dict('os.environ', DRIVE_ENV, clear=False)
    def test_true_when_all_four_vars_present(self):
        self.assertTrue(google_drive.is_configured())

    @patch.dict('os.environ', {**DRIVE_ENV, 'GOOGLE_DRIVE_REFRESH_TOKEN': ''}, clear=False)
    def test_false_when_a_var_is_missing(self):
        self.assertFalse(google_drive.is_configured())


class GetFileUrlFormatTests(TestCase):
    """get_file_url returns a link to our own /api/media/drive/<id>/ proxy,
    not a direct Google CDN link. Linking straight to Google was tried first
    (drive.google.com/uc for downloads, lh3.googleusercontent.com for inline
    images) but abandoned: the lh3 CDN enforces an undocumented per-referer
    rate limit that a handful of admin page loads was enough to trip,
    breaking every Drive-hosted image on the site for that browser far
    longer than expected. Proxying through our own domain uses the
    authenticated Drive API instead, a separate quota untouched by that
    throttle."""

    @override_settings(BACKEND_PUBLIC_URL='https://api.example.com')
    def test_builds_proxy_url_with_configured_base(self):
        url = google_drive.get_file_url('abc123', filename='photo.png')
        self.assertEqual(url, 'https://api.example.com/api/media/drive/abc123/')

    @override_settings(BACKEND_PUBLIC_URL='https://api.example.com')
    def test_filename_does_not_affect_the_url(self):
        # No extension-based branching any more - the proxy serves any file
        # type correctly using Drive's own reported mimeType.
        image_url = google_drive.get_file_url('abc123', filename='photo.png')
        pdf_url = google_drive.get_file_url('abc123', filename='notes.pdf')
        no_name_url = google_drive.get_file_url('abc123')
        self.assertEqual(image_url, pdf_url)
        self.assertEqual(image_url, no_name_url)


class GoogleDriveStorageTests(TestCase):
    """Exercises the Storage subclass Django actually calls (default_storage
    when STORAGES['default'] points at it), with the google_drive service
    module mocked at its public function boundary."""

    def setUp(self):
        self.storage = GoogleDriveStorage()

    @patch('core.storage_backends.google_drive.upload_file')
    def test_save_returns_name_with_drive_file_id_prefix(self, mock_upload):
        mock_upload.return_value = {'id': 'FILE123', 'name': 'photo.png'}
        saved_name = self.storage._save('courses/thumbnails/photo.png', ContentFile(b'data'))
        self.assertEqual(saved_name, 'courses/thumbnails/FILE123__photo.png')
        mock_upload.assert_called_once()
        self.assertEqual(mock_upload.call_args[0][0], 'courses/thumbnails/photo.png')

    @patch('core.storage_backends.google_drive.upload_file')
    def test_save_normalizes_windows_backslashes_before_upload(self, mock_upload):
        # Django's FileField.generate_filename() stringifies via
        # pathlib.PurePath, which yields backslash-joined names on Windows
        # dev machines even though upload_to values use forward slashes.
        mock_upload.return_value = {'id': 'FILE123', 'name': 'photo.png'}
        saved_name = self.storage._save('courses\\thumbnails\\photo.png', ContentFile(b'data'))
        self.assertEqual(saved_name, 'courses/thumbnails/FILE123__photo.png')
        self.assertEqual(mock_upload.call_args[0][0], 'courses/thumbnails/photo.png')

    @patch('core.storage_backends.google_drive.upload_file')
    def test_save_without_directory_prefix(self, mock_upload):
        mock_upload.return_value = {'id': 'FILE123', 'name': 'photo.png'}
        saved_name = self.storage._save('photo.png', ContentFile(b'data'))
        self.assertEqual(saved_name, 'FILE123__photo.png')

    @patch('core.storage_backends.google_drive.get_file_url')
    def test_url_extracts_file_id_and_basename(self, mock_get_url):
        mock_get_url.return_value = 'https://lh3.googleusercontent.com/d/FILE123'
        url = self.storage.url('courses/thumbnails/FILE123__photo.png')
        self.assertEqual(url, 'https://lh3.googleusercontent.com/d/FILE123')
        mock_get_url.assert_called_once_with('FILE123', filename='photo.png')

    def test_url_returns_empty_string_for_a_name_never_saved_by_this_storage(self):
        # Must never raise here - DRF calls .url on every FileField on every
        # serialized response, so one legacy/placeholder name would 500 an
        # entire endpoint rather than just leave one field blank.
        self.assertEqual(self.storage.url('courses/thumbnails/photo.png'), '')

    @patch('core.storage_backends.google_drive.get_file')
    def test_exists_true_when_drive_has_the_file(self, mock_get_file):
        mock_get_file.return_value = {'id': 'FILE123'}
        self.assertTrue(self.storage.exists('courses/thumbnails/FILE123__photo.png'))

    @patch('core.storage_backends.google_drive.get_file')
    def test_exists_false_when_drive_no_longer_has_the_file(self, mock_get_file):
        mock_get_file.return_value = None
        self.assertFalse(self.storage.exists('courses/thumbnails/FILE123__photo.png'))

    @patch('core.storage_backends.google_drive.get_file')
    def test_exists_false_for_a_never_saved_candidate_name_without_api_call(self, mock_get_file):
        # get_available_name/exists get called on the desired name BEFORE a
        # Drive file id exists for it - must not error, and must not need
        # a network call to answer (Drive has no concept of "this name is
        # taken" the way a filesystem does).
        self.assertFalse(self.storage.exists('courses/thumbnails/photo.png'))
        mock_get_file.assert_not_called()

    @patch('core.storage_backends.google_drive.delete_file')
    def test_delete_calls_drive_delete_with_extracted_file_id(self, mock_delete):
        self.storage.delete('courses/thumbnails/FILE123__photo.png')
        mock_delete.assert_called_once_with('FILE123')

    @patch('core.storage_backends.google_drive.delete_file')
    def test_delete_is_a_noop_for_a_never_saved_name(self, mock_delete):
        self.storage.delete('courses/thumbnails/photo.png')
        mock_delete.assert_not_called()

    @patch('core.storage_backends.google_drive.download_file')
    def test_open_downloads_and_wraps_in_content_file(self, mock_download):
        mock_download.return_value = b'the file bytes'
        f = self.storage._open('courses/thumbnails/FILE123__photo.png')
        self.assertEqual(f.read(), b'the file bytes')
        mock_download.assert_called_once_with('FILE123')

    @patch('core.storage_backends.google_drive.get_file')
    def test_size_reads_from_drive_metadata(self, mock_get_file):
        mock_get_file.return_value = {'id': 'FILE123', 'size': '4096'}
        self.assertEqual(self.storage.size('courses/thumbnails/FILE123__photo.png'), 4096)

    def test_get_available_name_never_deduplicates(self):
        # Every upload produces a fresh, distinct Drive file id regardless
        # of the requested name, so there is never a real collision.
        name = 'courses/thumbnails/photo.png'
        self.assertEqual(self.storage.get_available_name(name), name)

    @patch('core.storage_backends.google_drive.get_file_url')
    def test_file_id_with_double_underscore_parsed_correctly(self, mock_get_url):
        mock_get_url.return_value = 'https://lh3.googleusercontent.com/d/1Bk__AKkagV0ydpcTt5e4IQp_ggIYaXLC'
        url = self.storage.url('exams/question_papers/1Bk__AKkagV0ydpcTt5e4IQp_ggIYaXLC__officer_qp.pdf')
        self.assertEqual(url, 'https://lh3.googleusercontent.com/d/1Bk__AKkagV0ydpcTt5e4IQp_ggIYaXLC')
        mock_get_url.assert_called_once_with('1Bk__AKkagV0ydpcTt5e4IQp_ggIYaXLC', filename='officer_qp.pdf')


class ResolveTargetFolderTests(TestCase):
    """get_or_create_drive_folder/_resolve_target_folder against a mocked
    Drive service - no real API calls, no real folder IDs."""

    def setUp(self):
        google_drive._folder_cache.clear()

    def tearDown(self):
        google_drive._folder_cache.clear()

    def _mock_service(self, existing_folders=None):
        service = MagicMock()
        list_execute = service.files.return_value.list.return_value.execute
        list_execute.return_value = {'files': existing_folders or []}
        create_execute = service.files.return_value.create.return_value.execute
        create_execute.return_value = {'id': 'NEW-FOLDER-ID'}
        return service

    @patch('core.google_drive._get_service')
    def test_creates_folder_when_it_does_not_exist(self, mock_get_service):
        service = self._mock_service(existing_folders=[])
        mock_get_service.return_value = service
        folder_id = google_drive.get_or_create_drive_folder('course-media', 'root-id')
        self.assertEqual(folder_id, 'NEW-FOLDER-ID')
        service.files.return_value.create.assert_called_once()

    @patch('core.google_drive._get_service')
    def test_reuses_existing_folder_without_creating(self, mock_get_service):
        service = self._mock_service(existing_folders=[{'id': 'EXISTING-ID', 'name': 'course-media'}])
        mock_get_service.return_value = service
        folder_id = google_drive.get_or_create_drive_folder('course-media', 'root-id')
        self.assertEqual(folder_id, 'EXISTING-ID')
        service.files.return_value.create.assert_not_called()

    @patch('core.google_drive._get_service')
    def test_second_call_uses_in_process_cache_not_the_api(self, mock_get_service):
        service = self._mock_service(existing_folders=[{'id': 'EXISTING-ID', 'name': 'course-media'}])
        mock_get_service.return_value = service
        google_drive.get_or_create_drive_folder('course-media', 'root-id')
        google_drive.get_or_create_drive_folder('course-media', 'root-id')
        service.files.return_value.list.assert_called_once()

    @patch.dict('os.environ', DRIVE_ENV, clear=False)
    @patch('core.google_drive.get_or_create_drive_folder')
    def test_known_category_routes_to_its_named_subfolder(self, mock_get_or_create):
        mock_get_or_create.return_value = 'folder-id'
        google_drive._resolve_target_folder('courses/thumbnails/foo.jpg')
        mock_get_or_create.assert_called_once_with('course-media', 'root-folder-id')

    @patch.dict('os.environ', DRIVE_ENV, clear=False)
    @patch('core.google_drive.get_or_create_drive_folder')
    def test_unrecognized_category_routes_to_other(self, mock_get_or_create):
        mock_get_or_create.return_value = 'folder-id'
        google_drive._resolve_target_folder('unknown_category/covers/foo.jpg')
        mock_get_or_create.assert_called_once_with('other', 'root-folder-id')

    @patch.dict('os.environ', DRIVE_ENV, clear=False)
    @patch('core.google_drive.get_or_create_drive_folder')
    def test_backslash_path_still_routes_correctly(self, mock_get_or_create):
        mock_get_or_create.return_value = 'folder-id'
        google_drive._resolve_target_folder('courses\\thumbnails\\foo.jpg')
        mock_get_or_create.assert_called_once_with('course-media', 'root-folder-id')
