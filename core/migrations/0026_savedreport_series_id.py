import uuid

from django.db import migrations, models


def backfill_series(apps, schema_editor):
    Report = apps.get_model("core", "SavedReport")
    parents = dict(Report.objects.values_list("pk", "parent_version_id"))
    roots = {}
    for pk in parents:
        trail, positions = [], set()
        current = pk
        while current in parents and current not in roots and current not in positions:
            trail.append(current)
            positions.add(current)
            current = parents[current]
        if current in roots:
            root = roots[current]
        elif current in positions:
            # Preserve any legacy cycle as one series, without changing rows.
            root = min(trail[trail.index(current) :], key=str)
        else:
            root = trail[-1]
        for member in trail:
            roots[member] = root
    families = {}
    for pk, root in roots.items():
        families.setdefault(root, []).append(pk)
    for root, members in families.items():
        Report.objects.filter(pk__in=members).update(series_id=root)


class Migration(migrations.Migration):
    dependencies = [("core", "0025_audit_access_context")]
    operations = [
        migrations.AddField(
            model_name="savedreport",
            name="series_id",
            field=models.UUIDField(null=True, editable=False, db_index=True),
        ),
        migrations.RunPython(backfill_series, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="savedreport",
            name="series_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, db_index=True),
        ),
    ]
