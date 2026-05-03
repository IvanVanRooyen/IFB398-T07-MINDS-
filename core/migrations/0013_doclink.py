import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("core", "0012_prospect_hypothesis_objective"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DocLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("object_id", models.UUIDField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("content_type", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to="contenttypes.contenttype",
                )),
                ("document", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="links",
                    to="core.document",
                )),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "db_table": "doc_links",
            },
        ),
        migrations.AddIndex(
            model_name="doclink",
            index=models.Index(fields=["content_type", "object_id"], name="doc_links_ct_obj_idx"),
        ),
        migrations.AddIndex(
            model_name="doclink",
            index=models.Index(fields=["document"], name="doc_links_document_idx"),
        ),
        migrations.AddConstraint(
            model_name="doclink",
            constraint=models.UniqueConstraint(
                fields=["document", "content_type", "object_id"],
                name="unique_doc_link",
            ),
        ),
    ]
