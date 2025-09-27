import uuid
from django.conf import settings
from django.contrib.gis.db import models

class ProjectOp(models.Model):
    MODE = (("EXP","Exploration"), ("MIN","Mining"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mode = models.CharField(max_length=3, choices=MODE)
    name = models.CharField(max_length=255)
    geom = models.MultiPolygonField(srid=4326, null=True, blank=True)
    commodity = models.CharField(max_length=64, blank=True)
    def __str__(self): return self.name

class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(upload_to="docs/")
    title = models.CharField(max_length=255)
    year = models.IntegerField(null=True, blank=True)
    doc_type = models.CharField(max_length=64, blank=True)
    confidentiality = models.CharField(max_length=32, default="internal")
    checksum_sha256 = models.CharField(max_length=64, db_index=True, blank=True)
    project = models.ForeignKey(ProjectOp, null=True, blank=True, on_delete=models.SET_NULL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.title
