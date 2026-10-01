"""Custom Django Storage backend backed by Google Drive.

Wired in as STORAGES['default']['BACKEND'] in settings.py when Drive is
configured, so existing FileField/ImageField model fields and the manual
default_storage.save() avatar-upload pattern both transparently use Drive
with no other code changes.

Naming scheme: Django computes the desired relative path itself (via each
field's upload_to), e.g. "courses/thumbnails/foo.jpg". Drive has no concept
of a path or of "this name is taken" the way a filesystem does - every
upload becomes a new object with its own opaque file ID, and two files can
share a name in the same folder. To let _url()/delete()/_open() resolve a
saved name back to the right Drive object with NO extra API call (url() in
particular needs to be cheap - it can run on every list-page render), the
Drive file ID is folded into the *returned* name as a filename prefix:
"courses/thumbnails/<file_id>__foo.jpg". That returned value is what
actually gets stored in the model's FileField/ImageField column.
"""
import mimetypes

from django.core.files.base import ContentFile
from django.core.files.storage import Storage

from core import google_drive


def _split_name(name):
    """'dir/sub/<file_id>__foo.jpg' -> ('dir/sub', '<file_id>__foo.jpg')

    Django's FileField.generate_filename() builds names via pathlib.PurePath,
    which stringifies with backslashes on Windows dev machines even though
    upload_to values are written with forward slashes. Normalize first so
    routing/parsing behaves the same on Windows dev and Linux production.
    """
    name = name.replace('\\', '/')
    if '/' in name:
        directory, basename = name.rsplit('/', 1)
    else:
        directory, basename = '', name
    return directory, basename


def _parse_file_id(name):
    """Returns the Drive file ID embedded in a previously-saved name, or
    None if this name was never saved (e.g. a freshly-generated candidate
    name that hasn't gone through _save yet)."""
    _, basename = _split_name(name)
    if '__' not in basename:
        return None
    # Google Drive file IDs are base64url characters and may contain double
    # underscores ('__'). If basename contains multiple '__', partition('__')
    # would incorrectly cut the file ID short (e.g. '1Bk__AKkag...' -> '1Bk').
    cand_r, _, _rest_r = basename.rpartition('__')
    cand_l, _, _rest_l = basename.partition('__')
    if cand_r and not any(c in cand_r for c in ' /\\'):
        if len(cand_l) < 15 and len(cand_r) >= 15:
            return cand_r
    if cand_l and not any(c in cand_l for c in ' /\\'):
        return cand_l
    if cand_r and not any(c in cand_r for c in ' /\\'):
        return cand_r
    return None


class GoogleDriveStorage(Storage):
    def _open(self, name, mode='rb'):
        file_id = _parse_file_id(name)
        if file_id is None:
            raise FileNotFoundError(f'"{name}" was not saved by GoogleDriveStorage.')
        data = google_drive.download_file(file_id)
        return ContentFile(data, name=name)

    def _save(self, name, content):
        name = name.replace('\\', '/')
        content_type = getattr(content, 'content_type', None)
        mime_type = content_type or mimetypes.guess_type(name)[0] or 'application/octet-stream'

        file_obj = content.file if hasattr(content, 'file') else content
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)

        drive_file = google_drive.upload_file(name, file_obj, mime_type=mime_type)

        directory, basename = _split_name(name)
        clean_basename = basename.replace('__', '_')
        new_basename = f"{drive_file['id']}__{clean_basename}"
        return f'{directory}/{new_basename}' if directory else new_basename

    def exists(self, name):
        file_id = _parse_file_id(name)
        if file_id is None:
            # Never-saved candidate name - Drive has no notion of a path
            # being "taken", so there's nothing to collide with.
            return False
        return google_drive.get_file(file_id) is not None

    def delete(self, name):
        file_id = _parse_file_id(name)
        if file_id is None:
            return
        google_drive.delete_file(file_id)

    def size(self, name):
        file_id = _parse_file_id(name)
        if file_id is None:
            raise FileNotFoundError(f'"{name}" was not saved by GoogleDriveStorage.')
        meta = google_drive.get_file(file_id)
        if meta is None:
            raise FileNotFoundError(f'Drive file for "{name}" no longer exists.')
        return int(meta.get('size', 0))

    def url(self, name):
        # Unlike _open/size/delete, this must never raise: DRF (and any
        # other generic serializer) calls .url on every request that touches
        # a FileField, so one legacy or malformed name would 500 an entire
        # response. Names not in our own "<file_id>__basename" format (data
        # from before this storage backend existed, or a test fixture using
        # a plain placeholder string) just get no URL, same as an empty field.
        file_id = _parse_file_id(name)
        if file_id is None:
            return ''
        _, basename = _split_name(name)
        prefix = f'{file_id}__'
        if basename.startswith(prefix):
            original_filename = basename[len(prefix):]
        else:
            original_filename = basename.split('__', 1)[1] if '__' in basename else basename
        return google_drive.get_file_url(file_id, filename=original_filename)

    def get_available_name(self, name, max_length=None):
        # Every save produces a distinct Drive file ID regardless of the
        # requested name, so there's never a real collision to avoid here.
        return name
