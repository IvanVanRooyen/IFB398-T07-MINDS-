import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_documentchunk'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SavedReport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=256)),
                ('content_md', models.TextField()),
                ('clearance_level', models.CharField(
                    choices=[
                        ('PUBLIC', 'Public'),
                        ('INTERNAL', 'Internal'),
                        ('CONFIDENTIAL', 'Confidential'),
                        ('JORC_APPROVED', 'JORC Approved Personnel'),
                    ],
                    default='INTERNAL',
                    max_length=32,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('organisation', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='core.organisation',
                )),
                ('process', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='saved_reports',
                    to='core.process',
                )),
            ],
            options={
                'db_table': 'saved_reports',
                'ordering': ['-created_at'],
            },
        ),
    ]
