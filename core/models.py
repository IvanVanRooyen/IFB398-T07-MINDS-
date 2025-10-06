import uuid

from django.contrib.gis.db import models
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
                valid_choices = [choice[0] for choice in field.choice]
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


def choice_constraint(field: str, choices: list[str], constraint: str = None):
    valid_values = [choice[0] for choice in choices]
    name = constraint or f"valid_{field}"
    return models.CheckConstraint(
        check=models.Q(**{f"{field}__in": valid_values}), name=name
    )


# class Organisation(models.Model):
class Organisation(ValidatedChoiceModel):
    class Mode(models.TextChoices):
        EXPLORATION = "EXPLORATION", _("Exploration")
        MINING = "MINING", _("Mining")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, null=False)
    name = models.CharField(max_length=32, null=False, unique=True)
    mode = models.CharField(choices=Mode, default=Mode.EXPLORATION)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(mode__in=["EXPLORATION", "MINING"]),
                name="valid_organisation_mode",
            )
        ]

    def __repr__(self):
        return f"Organisation(id={self.id},name={self.name},mode={self.mode})"


# class Process(models.Model):
class Process(ValidatedChoiceModel):
    class ProcessType(models.TextChoices):
        PROJECT = "PROJECT", _("Project")
        OPERATION = "OPERATION", _("Operation")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, null=False)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    process_type = models.IntegerField(choices=ProcessType)

    pass


class Tenement(models.Model):
    # type: one of [ prospect, survey, drillhole ]
    #   - (++ [ sample, assay ] ??)

    pass


class User(models.Model):
    pass


class Document(models.Model):
    id = models.UUIDField(default=uuid.uuid4, unique=True, null=False, primary_key=True)
    file = models.FileField(upload_to="docs/")

    pass


# class ProjectOp(models.Model):
#     MODE = (("EXP","Exploration"), ("MIN","Mining"))
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     mode = models.CharField(max_length=3, choices=MODE)
#     name = models.CharField(max_length=255)
#     geom = models.MultiPolygonField(srid=4326, null=True, blank=True)
#     commodity = models.CharField(max_length=64, blank=True)
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
