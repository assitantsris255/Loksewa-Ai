"""
Subjective Examination PDF Generation & Compression Service.

Handles:
- Processing student-uploaded handwritten answer sheet images (JPG, PNG, WEBP).
- Safe image-to-PDF conversion while preserving handwriting clarity.
- Auto-orienting images based on EXIF orientation metadata.
- Smart compression: re-scales ultra-high-resolution mobile camera uploads
  to crisp A4 document bounds (~2400px at ~300 DPI) and compresses at 80-85% quality.
- Fallback for direct PDF uploads.
- Verification and safe cleanup of temporary processing files.
"""

import io
import os
import logging
from typing import List, Tuple
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

MAX_DIMENSION = 2400  # Max width/height in pixels for 300 DPI A4
JPEG_QUALITY = 82     # Keeps ink lines sharp while reducing file size dramatically


class SubjectivePdfService:
    @staticmethod
    def process_and_merge_images(images: List[Tuple[str, io.BytesIO]]) -> Tuple[ContentFile, int, int]:
        """
        Takes a list of (filename, file_bytes_io) tuples in desired page order.
        Converts them to a single compressed multi-page PDF.
        Returns:
            (ContentFile, page_count, total_bytes)
        """
        if not images:
            raise ValidationError("No answer sheet images provided for PDF conversion.")

        pil_images = []
        try:
            for idx, (fname, file_obj) in enumerate(images):
                file_obj.seek(0)
                try:
                    img = Image.open(file_obj)
                except Exception as e:
                    raise ValidationError(f"Invalid image format for page {idx + 1} ({fname}): {e}")

                # 1. Correct EXIF orientation (e.g. mobile portrait/landscape photos)
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass

                # 2. Convert to RGB (required for PDF and removing alpha channel)
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # 3. Smart downsampling if photo exceeds maximum document bounds
                width, height = img.size
                if max(width, height) > MAX_DIMENSION:
                    scale = MAX_DIMENSION / max(width, height)
                    new_size = (int(width * scale), int(height * scale))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)

                pil_images.append(img)

            # 4. Save all pages to a single PDF in memory
            pdf_buffer = io.BytesIO()
            first_image = pil_images[0]
            remaining_images = pil_images[1:] if len(pil_images) > 1 else []

            first_image.save(
                pdf_buffer,
                format='PDF',
                save_all=True,
                append_images=remaining_images,
                quality=JPEG_QUALITY,
                resolution=150.0,
            )

            pdf_bytes = pdf_buffer.getvalue()
            pdf_size = len(pdf_bytes)
            page_count = len(pil_images)

            # Verification: valid PDF header (%PDF-)
            if not pdf_bytes.startswith(b'%PDF-'):
                raise ValidationError("Generated file failed PDF header validation.")

            if pdf_size < 100:
                raise ValidationError("Generated PDF is suspiciously empty.")

            content_file = ContentFile(pdf_bytes, name="answer-sheet.pdf")
            return content_file, page_count, pdf_size

        finally:
            for img in pil_images:
                try:
                    img.close()
                except Exception:
                    pass

    @staticmethod
    def validate_and_process_pdf(file_obj) -> Tuple[ContentFile, int, int]:
        """
        Validates an uploaded PDF directly.
        Returns:
            (ContentFile, estimated_page_count, total_bytes)
        """
        file_obj.seek(0)
        content = file_obj.read()
        if not content.startswith(b'%PDF-'):
            raise ValidationError("Uploaded file is not a valid PDF document.")

        # Estimate page count by counting /Type /Page occurrences in PDF stream
        page_count = max(1, content.count(b'/Type /Page\n') + content.count(b'/Type /Page\r') + content.count(b'/Type/Page'))
        total_bytes = len(content)

        file_name = getattr(file_obj, 'name', None) or "answer-sheet.pdf"
        base_name = os.path.basename(file_name)
        if not base_name.lower().endswith('.pdf'):
            base_name += '.pdf'

        content_file = ContentFile(content, name=base_name)
        return content_file, page_count, total_bytes
