"""Shared file-upload validators.

Every FileField/ImageField in this project routes through the same
GoogleDriveStorage backend (core/storage_backends.py), but that backend is a
generic Django Storage implementation - the right layer for "is this file
too big / the wrong type" is Django's own model-field validation, which runs
on every save() and every DRF serializer .is_valid() automatically once
attached here. Without these, an authenticated user could upload an
arbitrarily large or arbitrary-type file to the shared 15GB Drive quota.
"""
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

# Plain top-level functions, not a factory returning closures - Django's
# migration writer needs to serialize each validator back to an importable
# `module.name` reference, which only works for a real top-level function
# object, not a dynamically-named closure.


def validate_image_size_5mb(file):
    if file.size > 5 * 1024 * 1024:
        raise ValidationError("File too large - maximum size is 5MB.")


def validate_document_size_20mb(file):
    if file.size > 20 * 1024 * 1024:
        raise ValidationError("File too large - maximum size is 20MB.")


def validate_pdf_upload(file):
    if not file.name.lower().endswith('.pdf'):
        raise ValidationError('Only PDF files are accepted.')
    if file.size <= 5:
        raise ValidationError('The PDF file is empty or invalid.')
    content_type = getattr(file, 'content_type', None)
    if content_type and content_type not in ('application/pdf', 'application/x-pdf'):
        raise ValidationError('The uploaded file must have a PDF MIME type.')
    current_position = file.tell() if hasattr(file, 'tell') else None
    header = file.read(5)
    if current_position is not None:
        file.seek(current_position)
    if header != b'%PDF-':
        raise ValidationError('The uploaded file is not a valid PDF document.')

validate_image_extension = FileExtensionValidator(
    allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'gif']
)
validate_document_extension = FileExtensionValidator(
    allowed_extensions=['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'webp']
)
