
#Permission decorators and utilities for role-based and attribute-based access control.
#This will be the implementation for JORC/VALMIN compliance and audit trail requirements.

from functools import wraps
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden

from .models import UserProfile, log_audit, AuditLog


def role_required(*allowed_roles):
    # Decorator to checks if user has one of the allowed roles.

    #Usage:
        #@role_required(UserProfile.RoleChoices.FIELD_LEAD, UserProfile.RoleChoices.ADMIN)
        #def approve_document(request, doc_id):
            
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied("Authentication required")

            if not hasattr(request.user, 'profile'):
                raise PermissionDenied("User profile not found")

            user_role = request.user.profile.role
            if user_role not in allowed_roles:
                raise PermissionDenied(f"Role {user_role} not authorized for this action")

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def organisation_access_required(view_func):
    #Decorator to ensure user can only access their organisation data.
    #Adds user_organisation to request object.

    #Usage:
        #@organisation_access_required
        #def view_documents(request):
            # Documents will be filtered by request.user_organisation
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")

        if not hasattr(request.user, 'profile'):
            raise PermissionDenied("User profile not found")

        # Add organisation filter to request
        request.user_organisation = request.user.profile.organisation
        return view_func(request, *args, **kwargs)
    return wrapper


def clearance_required(min_level):
    #Decorator to check if user has sufficient clearance

    #Usage:
        #@clearance_required(UserProfile.ClearanceLevel.JORC_APPROVED)
        #def view_jorc_report(request, report_id):

    clearance_hierarchy = {
        UserProfile.ClearanceLevel.PUBLIC: 0,
        UserProfile.ClearanceLevel.INTERNAL: 1,
        UserProfile.ClearanceLevel.CONFIDENTIAL: 2,
        UserProfile.ClearanceLevel.JORC_APPROVED: 3,
    }

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied("Authentication required")

            if not hasattr(request.user, 'profile'):
                raise PermissionDenied("User profile not found")

            user_level = clearance_hierarchy.get(request.user.profile.clearance_level, 0)
            required_level = clearance_hierarchy.get(min_level, 0)

            if user_level < required_level:
                raise PermissionDenied(f"Insufficient clearance level")

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def log_view_access(model_class):
    #Decorator to automatically log when users view objects for audit trail

    #Usage:
        #@log_view_access(Document)
        #def view_document(request, doc_id):
            #doc = get_object_or_404(Document, pk=doc_id)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)

            # Try to get object ID from kwargs
            obj_id = kwargs.get('pk') or kwargs.get('id') or kwargs.get('doc_id')

            if obj_id and request.user.is_authenticated:
                try:
                    obj = model_class.objects.get(pk=obj_id)

                    # Get IP address
                    ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
                    if ip_address:
                        ip_address = ip_address.split(',')[0]
                    else:
                        ip_address = request.META.get('REMOTE_ADDR')

                    # Log the view
                    log_audit(
                        user=request.user,
                        action=AuditLog.ActionType.VIEW,
                        obj=obj,
                        description=f"User viewed {model_class.__name__}",
                        ip_address=ip_address,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
                    )

                    # Also create DocumentView record if it's a Document
                    if model_class.__name__ == 'Document':
                        from .models import DocumentView
                        DocumentView.objects.create(
                            user=request.user,
                            document=obj,
                            ip_address=ip_address
                        )
                except model_class.DoesNotExist:
                    pass  # Object not found, view will handle 404

            return response
        return wrapper
    return decorator


def can_approve_workflow(user, workflow_type):
    #Check if a user can approve a specific workflow type

    #Args:
        #user: Django User instance
        #workflow_type: ApprovalWorkflow.WorkflowType choice

    #Returns:
        #bool: True if user can approve False otherwise

    if not hasattr(user, 'profile'):
        return False

    from .models import ApprovalWorkflow

    if workflow_type == ApprovalWorkflow.WorkflowType.JORC:
        return user.profile.can_approve_jorc
    elif workflow_type == ApprovalWorkflow.WorkflowType.VALMIN:
        return user.profile.can_approve_valmin
    else:
        # General approval - check role
        return user.profile.role in [
            UserProfile.RoleChoices.FIELD_LEAD,
            UserProfile.RoleChoices.DATA_MANAGER,
            UserProfile.RoleChoices.OPERATIONS_MANAGER,
            UserProfile.RoleChoices.ADMIN,
        ]


def get_user_ip(request):
    #Extract user IP address from request
    ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
    if ip_address:
        ip_address = ip_address.split(',')[0]
    else:
        ip_address = request.META.get('REMOTE_ADDR')
    return ip_address
