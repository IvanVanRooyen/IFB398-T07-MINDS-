from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_savedreport_change_reason_savedreport_change_summary_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="prospect",
            name="hypothesis",
            field=models.TextField(default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="prospect",
            name="objective",
            field=models.TextField(default=""),
            preserve_default=False,
        ),
    ]
