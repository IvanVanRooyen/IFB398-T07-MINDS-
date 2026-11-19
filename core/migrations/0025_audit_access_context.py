import django.db.models.deletion
from django.db import migrations, models


def backfill_context(apps, schema_editor):
    AuditLog = apps.get_model("core", "AuditLog")
    levels = {
        "public": "PUBLIC",
        "internal": "INTERNAL",
        "confidential": "CONFIDENTIAL",
        "jorc_restricted": "JORC_APPROVED",
    }
    # Unknown/deleted targets remain platform-only (null organisation).
    for entry in AuditLog.objects.select_related("content_type").iterator(chunk_size=500):
        ct = entry.content_type
        if ct.app_label != "core":
            continue
        try:
            model = apps.get_model(ct.app_label, ct.model)
        except LookupError:
            continue
        if model._meta.pk.get_internal_type() != "UUIDField":
            continue
        if not any(field.name == "organisation" for field in model._meta.fields):
            continue
        obj = model.objects.filter(pk=entry.object_id).first()
        if obj is None:
            continue
        level = getattr(obj, "clearance_level", "PUBLIC")
        if hasattr(obj, "confidentiality"):
            level = levels.get(obj.confidentiality, "JORC_APPROVED")
        organisation_id = obj.organisation_id
        ranks = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "JORC_APPROVED": 3}
        if hasattr(obj, "confidentiality") and obj.confidentiality not in levels:
            organisation_id = None
        if ct.model == "savedreport":
            rank = ranks.get(level, 3)
            for source in obj.source_documents.values("organisation_id", "confidentiality"):
                rank = max(rank, ranks[levels.get(source["confidentiality"], "JORC_APPROVED")])
                if source["organisation_id"] != organisation_id or source["confidentiality"] not in levels:
                    organisation_id = None
            level = next(name for name, value in ranks.items() if value == rank)
        AuditLog.objects.filter(pk=entry.pk).update(
            organisation_id=organisation_id, clearance_level=level
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0024_req6_fixup")]
    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="organisation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="core.organisation",
            ),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="clearance_level",
            field=models.CharField(
                choices=[
                    ("PUBLIC", "Public"),
                    ("INTERNAL", "Internal"),
                    ("CONFIDENTIAL", "Confidential"),
                    ("JORC_APPROVED", "JORC Approved Personnel"),
                ],
                default="JORC_APPROVED",
                max_length=32,
            ),
        ),
        migrations.RunPython(backfill_context, migrations.RunPython.noop),
    ]
