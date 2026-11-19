from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0026_savedreport_series_id")]
    operations = [
        migrations.AddField(
            model_name="savedreport",
            name="generation_manifest",
            field=models.JSONField(default=dict, blank=True),
        )
    ]
