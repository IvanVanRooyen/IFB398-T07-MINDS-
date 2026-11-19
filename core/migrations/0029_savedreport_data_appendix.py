from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0028_report_generation_jobs")]

    operations = [
        migrations.AddField(
            model_name="savedreport",
            name="data_appendix",
            field=models.JSONField(blank=True, default=dict),
        )
    ]
