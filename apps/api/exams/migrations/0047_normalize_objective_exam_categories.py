from django.db import migrations, models


def normalize_categories(apps, schema_editor):
    Examination = apps.get_model('exams', 'Examination')
    examinations = Examination.objects.using(schema_editor.connection.alias)
    examinations.filter(objective_category='old_past').update(objective_category='past_year')
    examinations.filter(objective_category='custom').update(objective_category=None)
    examinations.filter(exam_type='subject', topic__isnull=False).update(objective_category='topicwise')


def restore_legacy_categories(apps, schema_editor):
    Examination = apps.get_model('exams', 'Examination')
    examinations = Examination.objects.using(schema_editor.connection.alias)
    examinations.filter(objective_category='past_year').update(objective_category='old_past')
    examinations.filter(objective_category='topicwise').update(objective_category=None)


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0046_examinationrequest'),
    ]

    operations = [
        migrations.RunPython(normalize_categories, restore_legacy_categories),
        migrations.AlterField(
            model_name='examination',
            name='objective_category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('past_year', 'Past Year Paper'),
                    ('model', 'Model Exam'),
                    ('live', 'Live Exam'),
                    ('topicwise', 'Topicwise Exam'),
                ],
                max_length=20,
                null=True,
            ),
        ),
    ]