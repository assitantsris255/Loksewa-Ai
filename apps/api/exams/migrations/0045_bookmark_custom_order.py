from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0044_alter_practicesession_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='bookmark',
            name='custom_order',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]