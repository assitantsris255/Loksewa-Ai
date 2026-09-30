from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0001_initial'),
        ('exams', '0048_examination_generation_key'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='examinationrequest',
            name='unique_student_examination_request',
        ),
        migrations.AddField(
            model_name='examinationrequest',
            name='request_type',
            field=models.CharField(choices=[('exam_access', 'Examination Access'), ('subjective_live', 'Subjective Live Exam')], default='exam_access', max_length=24),
        ),
        migrations.AddField(
            model_name='examinationrequest',
            name='academic_exam',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='subjective_exam_requests', to='exams.exam'),
        ),
        migrations.AddField(
            model_name='examinationrequest',
            name='course',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subjective_exam_requests', to='courses.course'),
        ),
        migrations.AddField(
            model_name='examinationrequest',
            name='subject',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subjective_exam_requests', to='exams.subject'),
        ),
        migrations.AddField(
            model_name='examinationrequest',
            name='topic',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subjective_exam_requests', to='exams.topic'),
        ),
        migrations.AlterField(
            model_name='examinationrequest',
            name='examination',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='student_requests', to='exams.examination'),
        ),
        migrations.AddConstraint(
            model_name='examinationrequest',
            constraint=models.UniqueConstraint(condition=models.Q(('examination__isnull', False)), fields=('student', 'examination'), name='unique_student_examination_request'),
        ),
        migrations.AddConstraint(
            model_name='examinationrequest',
            constraint=models.UniqueConstraint(condition=models.Q(('request_type', 'subjective_live'), ('status', 'pending')), fields=('student', 'academic_exam'), name='unique_pending_subjective_request'),
        ),
    ]