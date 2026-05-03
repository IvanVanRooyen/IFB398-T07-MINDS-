"""
Placeholder migration — originally numbered incorrectly.
All operations moved to 0014_document_search_tsv.py which follows 0013_doclink.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_doclink'),
    ]

    operations = []
