import io
import os
from xml.sax.saxutils import escape

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer


def _font_name(texts):
    font_path = getattr(settings, 'SUBJECTIVE_EXAM_PDF_FONT_PATH', '') or os.getenv('SUBJECTIVE_EXAM_PDF_FONT_PATH', '')
    if not font_path and os.name == 'nt':
        windows_font = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'Nirmala.ttc')
        if os.path.isfile(windows_font):
            font_path = windows_font
    if font_path:
        if not os.path.isfile(font_path):
            raise ValidationError('Configured subjective exam PDF font was not found.')
        font_name = 'LoksewaExamUnicode'
        if font_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font_name, font_path))
        return font_name

    if any(ord(character) > 255 for text in texts for character in text):
        raise ValidationError(
            'This paper contains non-Latin text. Configure SUBJECTIVE_EXAM_PDF_FONT_PATH '
            'to a Unicode TrueType font before generating it.'
        )
    return 'Helvetica'


def build_subjective_paper_pdf(
    *, title, position_name, subject_name, course_name, duration_minutes,
    total_marks, start_time, instructions, questions,
):
    texts = [title, position_name, subject_name or '', course_name or '', instructions or '']
    for question in questions:
        texts.extend([
            question.text or '', question.option_a or '', question.option_b or '',
            question.option_c or '', question.option_d or '',
        ])
    font_name = _font_name(texts)

    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        'PaperHeading', parent=styles['Title'], fontName=font_name, fontSize=16,
        leading=20, alignment=TA_CENTER, spaceAfter=5 * mm,
    )
    metadata = ParagraphStyle(
        'PaperMetadata', parent=styles['Normal'], fontName=font_name,
        fontSize=10, leading=14, alignment=TA_CENTER,
    )
    question_style = ParagraphStyle(
        'PaperQuestion', parent=styles['BodyText'], fontName=font_name,
        fontSize=11, leading=16, spaceAfter=2 * mm,
    )
    option_style = ParagraphStyle(
        'PaperOption', parent=question_style, leftIndent=8 * mm, fontSize=10,
    )

    content = io.BytesIO()
    document = SimpleDocTemplate(
        content, pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm, title=title, author='LoksewaAI',
    )
    story = [
        Paragraph('LOKSEWAAI', heading),
        Paragraph(escape(title), heading),
        Paragraph(escape(position_name), metadata),
    ]
    details = [f'Duration: {duration_minutes} minutes', f'Total Marks: {total_marks:g}']
    if start_time:
        details.append(f'Available: {timezone.localtime(start_time).strftime("%b %d, %Y %I:%M %p %Z")}')
    if subject_name:
        details.append(f'Subject: {subject_name}')
    if course_name:
        details.append(f'Course: {course_name}')
    story.extend([Paragraph(escape(' | '.join(details)), metadata), Spacer(1, 8 * mm)])
    if instructions:
        story.extend([
            Paragraph('<b>Instructions</b>', question_style),
            Paragraph(escape(instructions).replace('\n', '<br/>'), question_style),
            Spacer(1, 5 * mm),
        ])

    for index, question in enumerate(questions, start=1):
        parts = [Paragraph(f'<b>{index}. ({question.marks:g} marks)</b> {escape(question.text)}', question_style)]
        for label, option in (
            ('A', question.option_a), ('B', question.option_b),
            ('C', question.option_c), ('D', question.option_d),
        ):
            if option:
                parts.append(Paragraph(f'{label}. {escape(option)}', option_style))
        parts.append(Spacer(1, 4 * mm))
        story.append(KeepTogether(parts))

    document.build(story)
    result = content.getvalue()
    if not result.startswith(b'%PDF-'):
        raise ValidationError('Question paper PDF generation failed validation.')
    return result