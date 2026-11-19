"""Shared access policy for application records and derived content."""

from django.core.exceptions import PermissionDenied
from django.db.models import Q

CLEARANCE_LEVELS = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "JORC_APPROVED": 3}
DOCUMENT_LEVELS = {"public": 0, "internal": 1, "confidential": 2, "jorc_restricted": 3}
AUTHOR_ROLES = (
    "GEOLOGIST_EXPL",
    "FIELD_LEAD",
    "DATA_MANAGER",
    "GEOLOGIST_MINE",
    "METALLURGIST",
    "OPS_MANAGER",
    "COMPETENT_PERSON",
    "ADMIN",
)


def organisation_filter(user, prefix=""):
    if user.is_authenticated and getattr(user, "is_superuser", False):
        return Q()
    profile = getattr(user, "profile", None) if user.is_authenticated else None
    if profile and profile.organisation:
        return Q(**{f"{prefix}organisation": profile.organisation})
    return Q(pk__in=[])


def clearance_level(user):
    if user.is_authenticated and getattr(user, "is_superuser", False):
        return "JORC_APPROVED"
    profile = getattr(user, "profile", None) if user.is_authenticated else None
    return getattr(profile, "clearance_level", "PUBLIC")


def document_filter(user, prefix=""):
    if user.is_authenticated and user.is_superuser:
        return Q()
    rank = CLEARANCE_LEVELS.get(clearance_level(user), -1)
    allowed = [name for name, level in DOCUMENT_LEVELS.items() if level <= rank]
    profile = getattr(user, "profile", None) if user.is_authenticated else None
    org = getattr(profile, "organisation", None)
    return (
        organisation_filter(user, prefix)
        & Q(**{f"{prefix}confidentiality__in": allowed})
        & (Q(**{f"{prefix}process__isnull": True}) | Q(**{f"{prefix}process__organisation": org}))
        & (Q(**{f"{prefix}tenement__isnull": True}) | Q(**{f"{prefix}tenement__organisation": org}))
    )


def report_filter(user):
    if user.is_authenticated and user.is_superuser:
        return Q()
    rank = CLEARANCE_LEVELS.get(clearance_level(user), -1)
    allowed = [name for name, level in CLEARANCE_LEVELS.items() if level <= rank]
    return organisation_filter(user) & Q(clearance_level__in=allowed)


def require_record_access(user, record):
    """Deny missing tenant context as well as mismatched/unknown classifications."""
    if not user.is_authenticated:
        raise PermissionDenied
    if user.is_superuser:
        return
    profile = getattr(user, "profile", None)
    if not profile or not profile.organisation_id:
        raise PermissionDenied
    if not record.organisation or record.organisation != profile.organisation:
        raise PermissionDenied
    if record._meta.label_lower in ("core.document", "core.savedreport"):
        if record.process_id and record.process.organisation_id != profile.organisation_id:
            raise PermissionDenied
    if record._meta.label_lower == "core.document" and record.tenement_id:
        if record.tenement.organisation_id != profile.organisation_id:
            raise PermissionDenied
    rank = CLEARANCE_LEVELS.get(profile.clearance_level, -1)
    if record._meta.label_lower == "core.document":
        if DOCUMENT_LEVELS.get(record.confidentiality, 4) > rank:
            raise PermissionDenied
    if record._meta.label_lower == "core.savedreport":
        if CLEARANCE_LEVELS.get(record.clearance_level, 4) > rank:
            raise PermissionDenied


def require_author(user):
    if user.is_authenticated and user.is_superuser:
        return
    profile = getattr(user, "profile", None) if user.is_authenticated else None
    if not profile or not profile.organisation_id or profile.role not in AUTHOR_ROLES:
        raise PermissionDenied


def require_report_author(user, report):
    require_record_access(user, report)
    require_author(user)
    if not user.is_superuser and report.created_by_id != user.pk and user.profile.role != "ADMIN":
        raise PermissionDenied
