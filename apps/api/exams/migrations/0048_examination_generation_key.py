import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0047_normalize_objective_exam_categories'),
    ]

    operations = [
        migrations.AddField(
            model_name='examination',
            name='generation_key',
            field=models.UUIDField(blank=True, editable=False, null=True, unique=True),
        ),
    ]