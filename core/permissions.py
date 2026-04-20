from functools import wraps

from django.core.exceptions import PermissionDenied

from .models import UserProfile, log_audit, AuditLog, DocumentView


# ---- ROLE SETS ----

EXPLORATION_ROLES = {
    UserProfile.RoleChoices.GEOLOGIST_EXPL,
    UserProfile.RoleChoices.FIELD_LEAD,
    UserProfile.RoleChoices.DATA_MANAGER,
    UserProfile.RoleChoices.COMPETENT_PERSON,
}

MINING_ROLES = {
    UserProfile.RoleChoices.GEOLOGIST_MINE,
    UserProfile.RoleChoices.METALLURGIST,
    UserProfile.RoleChoices.OPS_MANAGER,
}

MANAGEMENT_ROLES = {
    UserProfile.RoleChoices.FIELD_LEAD,
    UserProfile.RoleChoices.DATA_MANAGER,
    UserProfile.RoleChoices.COMPETENT_PERSON,
    UserProfile.RoleChoices.OPS_MANAGER,
    UserProfile.RoleChoices.ADMIN,
}

UPLOAD_ROLES = {
    UserProfile.RoleChoices.GEOLOGIST_EXPL,
    UserProfile.RoleChoices.FIELD_LEAD,
    UserProfile.RoleChoices.DATA_MANAGER,
    UserProfile.RoleChoices.COMPETENT_PERSON,
    UserProfile.RoleChoices.GEOLOGIST_MINE,
    UserProfile.RoleChoices.METALLURGIST,
    UserProfile.RoleChoices.OPS_MANAGER,
    UserProfile.RoleChoices.ADMIN,
}

REPORT_ROLES = {
    UserProfile.RoleChoices.GEOLOGIST_EXPL,
    UserProfile.RoleChoices.FIELD_LEAD,
    UserProfile.RoleChoices.DATA_MANAGER,
    UserProfile.RoleChoices.COMPETENT_PERSON,
    UserProfile.RoleChoices.GEOLOGIST_MINE,
    UserProfile.RoleChoices.METALLURGIST,
    UserProfile.RoleChoices.OPS_MANAGER,
    UserProfile.RoleChoices.ADMIN,
}

DELETE_ROLES = {
    UserProfile.RoleChoices.DATA_MANAGER,
    UserProfile.RoleChoices.ADMIN,
}

VIEW_ROLES = {
    UserProfile.RoleChoices.GEOLOGIST_EXPL,
    UserProfile.RoleChoices.FIELD_LEAD,
    UserProfile.RoleChoices.DATA_MANAGER,
    UserProfile.RoleChoices.COMPETENT_PERSON,
    UserProfile.RoleChoices.GEOLOGIST_MINE,
    UserProfile.RoleChoices.METALLURGIST,
    UserProfile.RoleChoices.OPS_MANAGER,
    UserProfile.RoleChoices.ADMIN,
    UserProfile.RoleChoices.VIEWER,
}


# ---- CLEARANCE HELPERS ----

CLEARANCE_RANK = {
    "PUBLIC": 0,
    "INTERNAL": 1,
    "CONFIDENTIAL": 2,
    # Keep this here temporarily so old data does not break anything
    "JORC_APPROVED": 3,
}

DOCUMENT_CONFIDENTIALITY_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    # Keep for backwards compatibility if old rows exist
    "jorc_restricted": 3,
}


# ---- BASIC USER / ROLE HELPERS ----

def is_authenticated_with_profile(user) -> bool:
    return bool(user and user.is_authenticated and hasattr(user, "profile"))


def get_user_profile(user):
    if not is_authenticated_with_profile(user):
        return None
    return user.profile


def get_user_role(user):
    profile = get_user_profile(user)
    return profile.role if profile else None


def get_user_clearance(user) -> str:
    profile = get_user_profile(user)
    if not profile:
        return "PUBLIC"
    return profile.clearance_level or "PUBLIC"


def has_role(user, *allowed_roles) -> bool:
    role = get_user_role(user)
    return role in allowed_roles


def has_any_role(user, allowed_roles) -> bool:
    role = get_user_role(user)
    return role in allowed_roles


def is_admin(user) -> bool:
    return get_user_role(user) == UserProfile.RoleChoices.ADMIN


def is_viewer(user) -> bool:
    return get_user_role(user) == UserProfile.RoleChoices.VIEWER


def is_exploration_user(user) -> bool:
    return has_any_role(user, EXPLORATION_ROLES)


def is_mining_user(user) -> bool:
    return has_any_role(user, MINING_ROLES)


def is_management_user(user) -> bool:
    return has_any_role(user, MANAGEMENT_ROLES)


# ---- CLEARANCE / ORG HELPERS ----

def has_clearance(user, min_level: str) -> bool:
    user_rank = CLEARANCE_RANK.get(get_user_clearance(user), 0)
    required_rank = CLEARANCE_RANK.get(min_level, 0)
    return user_rank >= required_rank


def document_confidentiality_rank(document) -> int:
    value = (getattr(document, "confidentiality", None) or "internal").lower()
    return DOCUMENT_CONFIDENTIALITY_RANK.get(value, 1)


def user_clearance_rank(user) -> int:
    return CLEARANCE_RANK.get(get_user_clearance(user), 0)


def belongs_to_same_organisation(user, obj) -> bool:
    profile = get_user_profile(user)
    if not profile:
        return False

    user_org = getattr(profile, "organisation", None)
    obj_org = getattr(obj, "organisation", None)

    # If object has no organisation, allow access
    if obj_org is None:
        return True

    # If user has no organisation, only admins should pass
    if user_org is None:
        return is_admin(user)

    return user_org == obj_org


# ---- DOMAIN HELPERS ----

def user_matches_process_mode(user, obj) -> bool:
    """
    Enforce exploration/mining split where possible.

    Accepts objects that either:
    - have a direct `mode`, or
    - have a related `process.mode`

    If mode cannot be determined, this helper allows access and leaves
    the decision to role/clearance/org checks.
    """
    if is_admin(user):
        return True

    mode = getattr(obj, "mode", None)

    if mode is None:
        process = getattr(obj, "process", None)
        mode = getattr(process, "mode", None)

    if mode is None:
        return True

    if mode == "PROJECT":
        return is_exploration_user(user)

    if mode == "OPERATION":
        return is_mining_user(user)

    return True


# ---- OBJECT ACCESS CHECKS ----

def can_access_document(user, document) -> bool:
    if not is_authenticated_with_profile(user):
        return False

    if not has_any_role(user, VIEW_ROLES):
        return False

    if not belongs_to_same_organisation(user, document):
        return False

    if user_clearance_rank(user) < document_confidentiality_rank(document):
        return False

    if not user_matches_process_mode(user, document):
        return False

    return True


def can_upload_document(user, process=None) -> bool:
    if not is_authenticated_with_profile(user):
        return False

    if not has_any_role(user, UPLOAD_ROLES):
        return False

    if process is not None:
        if not belongs_to_same_organisation(user, process):
            return False
        if not user_matches_process_mode(user, process):
            return False

    return True


def can_delete_document(user, document) -> bool:
    if not is_authenticated_with_profile(user):
        return False

    if not has_any_role(user, DELETE_ROLES):
        return False

    if not belongs_to_same_organisation(user, document):
        return False

    return True


def can_generate_report(user, process) -> bool:
    if not is_authenticated_with_profile(user):
        return False

    if not has_any_role(user, REPORT_ROLES):
        return False

    if not belongs_to_same_organisation(user, process):
        return False

    if not user_matches_process_mode(user, process):
        return False

    return True


def can_view_report(user, report) -> bool:
    if not is_authenticated_with_profile(user):
        return False

    if not has_any_role(user, VIEW_ROLES):
        return False

    if not belongs_to_same_organisation(user, report):
        return False

    report_rank = CLEARANCE_RANK.get(getattr(report, "clearance_level", "INTERNAL"), 1)
    if user_clearance_rank(user) < report_rank:
        return False

    if not user_matches_process_mode(user, report):
        return False

    return True


def can_edit_report(user, report) -> bool:
    if not can_view_report(user, report):
        return False

    if is_admin(user):
        return True

    return report.created_by == user


# ---- DECORATORS ----


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not is_authenticated_with_profile(request.user):
                raise PermissionDenied("Authentication required")

            if not has_role(request.user, *allowed_roles):
                raise PermissionDenied("You do not have permission for this action.")

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def exploration_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_authenticated_with_profile(request.user):
            raise PermissionDenied("Authentication required")

        if not (is_exploration_user(request.user) or is_admin(request.user)):
            raise PermissionDenied("Exploration access required.")

        return view_func(request, *args, **kwargs)
    return wrapper


def mining_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_authenticated_with_profile(request.user):
            raise PermissionDenied("Authentication required")

        if not (is_mining_user(request.user) or is_admin(request.user)):
            raise PermissionDenied("Mining access required.")

        return view_func(request, *args, **kwargs)
    return wrapper


def clearance_required(min_level):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not is_authenticated_with_profile(request.user):
                raise PermissionDenied("Authentication required")

            if not has_clearance(request.user, min_level):
                raise PermissionDenied("Insufficient clearance level.")

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def organisation_access_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_authenticated_with_profile(request.user):
            raise PermissionDenied("Authentication required")

        request.user_organisation = request.user.profile.organisation
        return view_func(request, *args, **kwargs)
    return wrapper



# ---- AUDIT HELPERS ----


def get_user_ip(request):
    ip_address = request.META.get("HTTP_X_FORWARDED_FOR")
    if ip_address:
        return ip_address.split(",")[0]
    return request.META.get("REMOTE_ADDR")


def log_view_access(model_class):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)

            obj_id = kwargs.get("pk") or kwargs.get("id") or kwargs.get("doc_id")
            if obj_id and request.user.is_authenticated:
                try:
                    obj = model_class.objects.get(pk=obj_id)
                    ip_address = get_user_ip(request)

                    log_audit(
                        user=request.user,
                        action=AuditLog.ActionType.VIEW,
                        obj=obj,
                        description=f"User viewed {model_class.__name__}",
                        ip_address=ip_address,
                        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                    )

                    if model_class.__name__ == "Document":
                        DocumentView.objects.create(
                            user=request.user,
                            document=obj,
                            ip_address=ip_address,
                        )
                except model_class.DoesNotExist:
                    pass

            return response
        return wrapper
    return decorator