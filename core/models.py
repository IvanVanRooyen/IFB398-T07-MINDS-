# from django.utils import timezone
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver
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


# USER PROFILE & PERMISSIONS ---------------------------------

class UserProfile(models.Model):
    """Extended user attributes for mining/exploration governance"""

    class RoleChoices(models.TextChoices):
        # Exploration roles
        GEOLOGIST_EXPL = "GEOLOGIST_EXPL", _("Geologist (Exploration)")
        FIELD_LEAD = "FIELD_LEAD", _("Field Lead")
        DATA_MANAGER = "DATA_MANAGER", _("Data Manager")

        # Mining roles
        GEOLOGIST_MINE = "GEOLOGIST_MINE", _("Mine Geologist")
        METALLURGIST = "METALLURGIST", _("Metallurgist")
        OPERATIONS_MANAGER = "OPS_MANAGER", _("Operations Manager")

        # Admin/Other
        ADMIN = "ADMIN", _("Administrator")
        VIEWER = "VIEWER", _("Viewer Only")

    class ClearanceLevel(models.TextChoices):
        PUBLIC = "PUBLIC", _("Public")
        INTERNAL = "INTERNAL", _("Internal")
        CONFIDENTIAL = "CONFIDENTIAL", _("Confidential")
        JORC_APPROVED = "JORC_APPROVED", _("JORC Approved Personnel")

    # Core fields
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, null=True, blank=True)
    role = models.CharField(max_length=32, choices=RoleChoices.choices, default=RoleChoices.VIEWER)
    clearance_level = models.CharField(
        max_length=32,
        choices=ClearanceLevel.choices,
        default=ClearanceLevel.INTERNAL
    )

    # Optional metadata - We need to decide if this is needed*********
    department = models.CharField(max_length=64, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    employee_id = models.CharField(max_length=32, blank=True, unique=True, null=True)

    # Workflow permissions
    can_approve_jorc = models.BooleanField(default=False, help_text="Can approve JORC compliance workflows")
    can_approve_valmin = models.BooleanField(default=False, help_text="Can approve VALMIN compliance workflows")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_profiles'
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    def is_exploration_role(self):
        """Check if user has an exploration role"""
        return self.role in [
            self.RoleChoices.GEOLOGIST_EXPL,
            self.RoleChoices.FIELD_LEAD,
            self.RoleChoices.DATA_MANAGER,
        ]

    def is_mining_role(self):
        """Check if user has a mining role"""
        return self.role in [
            self.RoleChoices.GEOLOGIST_MINE,
            self.RoleChoices.METALLURGIST,
            self.RoleChoices.OPERATIONS_MANAGER,
        ]

    def can_access_document(self, document):
        """Attribute-based access control for documents"""
        # Same organisation check
        if document.organisation and document.organisation != self.organisation:
            return False

        # Clearance level check
        doc_clearance_hierarchy = {
            'public': 0,
            'internal': 1,
            'confidential': 2,
            'jorc_restricted': 3,
        }
        user_clearance_hierarchy = {
            self.ClearanceLevel.PUBLIC: 0,
            self.ClearanceLevel.INTERNAL: 1,
            self.ClearanceLevel.CONFIDENTIAL: 2,
            self.ClearanceLevel.JORC_APPROVED: 3,
        }

        doc_level = doc_clearance_hierarchy.get(document.confidentiality.lower() if document.confidentiality else 'internal', 0)
        user_level = user_clearance_hierarchy.get(self.clearance_level, 0)

        return user_level >= doc_level


# Autocreate profile when user is created
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()


# AUDIT TRAIL ---------------------------------

class AuditLog(models.Model):
    """Track all user actions for compliance (JORC/VALMIN requirements)"""

    class ActionType(models.TextChoices):
        CREATE = "CREATE", _("Created")
        VIEW = "VIEW", _("Viewed")
        EDIT = "EDIT", _("Edited")
        APPROVE = "APPROVE", _("Approved")
        REJECT = "REJECT", _("Rejected")
        DELETE = "DELETE", _("Deleted")
        DOWNLOAD = "DOWNLOAD", _("Downloaded")

    # Who made the changes
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    # What was changed
    action = models.CharField(max_length=16, choices=ActionType.choices)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # Context
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # When changes were made 
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user', 'action']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        user_name = self.user.username if self.user else "Unknown"
        return f"{user_name} {self.action} {self.content_object} at {self.timestamp}"


# APPROVAL WORKFLOWS ---------------------------------
class ApprovalWorkflow(models.Model):
    """JORC/VALMIN approval workflows"""

    class WorkflowType(models.TextChoices):
        JORC = "JORC", _("JORC Compliance")
        VALMIN = "VALMIN", _("VALMIN Compliance")
        GENERAL = "GENERAL", _("General Approval")

    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pending Review")
        APPROVED = "APPROVED", _("Approved")
        REJECTED = "REJECTED", _("Rejected")
        REVISION_REQUIRED = "REVISION", _("Revision Required")

    # WHich items needs approval
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # Workflow details
    workflow_type = models.CharField(max_length=16, choices=WorkflowType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    # Which users are associated 
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workflow_submissions')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='workflow_approvals')

    # Context
    submission_notes = models.TextField(blank=True)
    approval_notes = models.TextField(blank=True)

    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'approval_workflows'
        ordering = ['-submitted_at']
        verbose_name = 'Approval Workflow'
        verbose_name_plural = 'Approval Workflows'

    def __str__(self):
        return f"{self.workflow_type} - {self.status} - {self.content_object}"

    def can_approve(self, user):
        """Check if user can approve this workflow"""
        if not hasattr(user, 'profile'):
            return False

        profile = user.profile

        if self.workflow_type == self.WorkflowType.JORC:
            return profile.can_approve_jorc
        elif self.workflow_type == self.WorkflowType.VALMIN:
            return profile.can_approve_valmin
        else:
            # General approval - check role
            return profile.role in [
                UserProfile.RoleChoices.FIELD_LEAD,
                UserProfile.RoleChoices.DATA_MANAGER,
                UserProfile.RoleChoices.OPERATIONS_MANAGER,
                UserProfile.RoleChoices.ADMIN,
            ]


# DOCUMENT VIEW TRACKING (Phase 2) ---------------------------------

class DocumentView(models.Model):
    """Track when users view documents for audit trail"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    document = models.ForeignKey('Document', on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'document_views'
        ordering = ['-viewed_at']
        indexes = [
            models.Index(fields=['document', 'user']),
            models.Index(fields=['viewed_at']),
        ]

    def __str__(self):
        return f"{self.user.username} viewed {self.document.title} at {self.viewed_at}"

# HELPER FUNCTIONS ---------------------------------

def log_audit(user, action, obj, description="", ip_address=None, user_agent=""):
    """Create audit trail entry"""
    AuditLog.objects.create(
        user=user,
        action=action,
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.id,
        description=description,
        ip_address=ip_address,
        user_agent=user_agent,
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
