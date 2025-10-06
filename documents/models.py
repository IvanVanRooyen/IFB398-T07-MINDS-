import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from .utils.checksums import md5_for_upload

User = get_user_model()

def doc_upload_to(instance, filename: str) -> str:
    project_part = f"{instance.project_id}/" if getattr(instance, "project_id", None) else "unassigned/" # if linked to project nest by IDs/names, otherwise unassigned
    date_part = timezone.now().strftime("%Y/%m/%d/")
    return f"documents/{project_part}{date_part}{filename}"

class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    file = models.FileField(upload_to=doc_upload_to)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    checksum = models.CharField(max_length=32, db_index=True)  # MD5 hex
    confidentiality = models.CharField(max_length=32, choices=[
        ("public", "Public"),
        ("internal", "Internal"),
        ("confidential", "Confidential"),
    ])

    # Example links (adjust to your actual models)
    project = models.ForeignKey("core.Project", null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    tenement = models.ForeignKey("core.Tenement", null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    commodity = models.ForeignKey("core.Commodity", null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")

    class Meta:
        indexes = [models.Index(fields=["checksum"])]

    def save(self, *args, **kwargs):
        # Only compute checksum on initial upload or file change
        if self.file and (not self.pk or self._state.adding or "update_fields" not in kwargs or "file" in (kwargs.get("update_fields") or [])):
            self.checksum = md5_for_upload(self.file)

        # Duplicate prevention: bail if checksum already exists (custom rule)
        if Document.objects.filter(checksum=self.checksum).exists() and not getattr(self, "_allow_duplicate", False):
            from django.core.exceptions import ValidationError
            raise ValidationError("A file with the same contents already exists (duplicate detected by checksum).")

        super().save(*args, **kwargs)
