# from django.utils import timezone
import uuid

from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ChoiceValidationMixin:
    """
    Automatically handle validation of choice fields
    """

    def clean(self):
        super().clean()
        for field in self._meta.fields:
            if field.choices:
                field_value = getattr(self, field.name)
                valid_choices = [choice[0] for choice in field.choices]
                if field_value not in valid_choices:
                    raise ValidationError(
                        {
                            field.name: f"invalid value for {field.name}"
                            f"(expected one of {valid_choices})"
                        }
                    )


class AutoCleanMixin:
    """
    Override `save()` method to run `full_clean()` prior to calling `save()`
    """

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ValidatedChoiceModel(ChoiceValidationMixin, AutoCleanMixin, models.Model):
    """
    Abstract base Model to handle automatic choice validation
    """

    class Meta:
        abstract = True


# def choice_constraint(field: str, choices: list[str], constraint: str = None):
#     valid_values = [choice[0] for choice in choices]
#     name = constraint or f"valid_{field}"
#     return models.CheckConstraint(
#         check=models.Q(**{f"{field}__in": valid_values}), name=name
#     )


# class Organisation(models.Model):
class Organisation(ValidatedChoiceModel):
    class Mode(models.TextChoices):
        EXPLORATION = "EXPLORATION", _("Exploration")
        MINING = "MINING", _("Mining")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, null=False)
    name = models.CharField(max_length=32, null=True)
    mode = models.CharField(choices=Mode, default=Mode.EXPLORATION)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(mode__in=["EXPLORATION", "MINING"]),
                name="valid_organisation_mode",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.mode})" if self.name else f"Organisation ({self.mode})"

    def __repr__(self):
        return f"Organisation(id={self.id},name={self.name},mode={self.mode})"


# TODO:
#  I feel like this is better named something like 'Campaign' or 'Activity' for
#  the sake of clarity
class Process(ValidatedChoiceModel):
    class ProcessType(models.TextChoices):
        PROJECT = "PROJECT", _("Project")
        OPERATION = "OPERATION", _("Operation")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, null=False)
    name = models.CharField(max_length=64, null=True)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, null=True, blank=True)
    mode = models.CharField(choices=ProcessType, default=ProcessType.PROJECT)

    geom = models.MultiPolygonField(srid=4326, null=True, blank=True)
    commodity = models.CharField(max_length=64, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(mode__in=["PROJECT", "OPERATION"]),
                name="valid_process_mode",
            )
        ]

    def __str__(self):
        return self.name if self.name else f"Process {self.id}"

    def __repr__(self):
        return (
            f"Process(id={self.id},name={self.name},organisation={self.organisation},"
            f"mode={self.mode},geom={self.geom},commodity={self.commodity},"
            f"created_at={self.created_at},updated_at={self.updated_at})"
        )


class Prospect(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, null=False)
    name = models.CharField(max_length=64, null=False)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    process = models.ForeignKey(Process, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __repr__(self):
        return (
            f"Prospect(id={self.id},name={self.name},organisation={self.organisation},"
            f"process={self.process},created_at={self.created_at},updated_at={self.updated_at}"
        )


class Tenement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, null=False)
    name = models.CharField(max_length=64, null=False)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    process = models.ForeignKey(Process, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __repr__(self):
        return (
            f"Tenement(id={self.id},name={self.name},organisation={self.organisation},"
            f"process={self.process},created_at={self.created_at},updated_at={self.updated_at}"
        )


class Drillhole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, null=False)
    name = models.CharField(max_length=64, null=False)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    process = models.ForeignKey(Process, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __repr__(self):
        return (
            f"Drillholed(id={self.id},name={self.name},organisation={self.organisation},"
            f"process={self.process},created_at={self.created_at},updated_at={self.updated_at}"
        )


class User(models.Model):
    pass


class Document(models.Model):
    id = models.UUIDField(default=uuid.uuid4, unique=True, null=False, primary_key=True)
    title = models.CharField(max_length=64)

    # filename = models.FileField(upload_to="docs/")
    file = models.FileField(upload_to="docs/")
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, null=True, blank=True)
    process = models.ForeignKey(Process, null=True, on_delete=models.SET_NULL, blank=True)
    tags = ArrayField(models.IntegerField(), default=list, blank=True)

    timestamp = models.DateField(null=True)
    doc_type = models.CharField(max_length=64, blank=True)
    confidentiality = models.CharField(max_length=64, default="internal")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True
    )

    checksum_sha256 = models.CharField(max_length=64, db_index=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Compute SHA-256 checksum if file exists and checksum not already set
        if self.file and not self.checksum_sha256:
            from .utils import sha256_file
            self.checksum_sha256 = sha256_file(self.file)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Delete the file from storage (MinIO) before deleting the database record
        if self.file:
            try:
                self.file.delete(save=False)
            except Exception as e:
                # Log the error but continue with deletion
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to delete file {self.file.name} from storage: {e}")
        super().delete(*args, **kwargs)

    def __str__(self):
        return self.title

    def __repr__(self):
        return (
            f"Document(id={self.id},title={self.title},filepath={self.file},"
            f"organisation={self.organisation},process={self.process},"
            f"doc_type={self.doc_type},confidentiality={self.confidentiality},"
            f"checksum_sha256={self.checksum_sha256},created_by={self.created_by},"
            f"created_at={self.created_at},"
        )


# class ProjectOp(models.Model):
#     MODE = (("EXP","Exploration"), ("MIN","Mining"))
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     mode = models.CharField(max_length=3, choices=MODE)
#     name = models.CharField(max_length=255)
# geom = models.MultiPolygonField(srid=4326, null=True, blank=True)
# commodity = models.CharField(max_length=64, blank=True)
#     def __str__(self): return self.name
#
# class Document(models.Model):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     file = models.FileField(upload_to="docs/")
#     title = models.CharField(max_length=255)
#     year = models.IntegerField(null=True, blank=True)
#     doc_type = models.CharField(max_length=64, blank=True)
#     confidentiality = models.CharField(max_length=32, default="internal")
#     checksum_sha256 = models.CharField(max_length=64, db_index=True, blank=True)
#     project = models.ForeignKey(ProjectOp, null=True, blank=True, on_delete=models.SET_NULL)
#     created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
#     created_at = models.DateTimeField(auto_now_add=True)
#     def __str__(self): return self.title
