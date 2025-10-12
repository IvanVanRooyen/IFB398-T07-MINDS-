# core/admin.py
from django.contrib import admin as djadmin
from django.contrib.gis.admin import GISModelAdmin

from .models import (
    Process, Document, Organisation, Prospect, Tenement, Drillhole,
    UserProfile, AuditLog, ApprovalWorkflow, DocumentView
)

# CORE MODELS ---------------------------------

@djadmin.register(Organisation)
class OrganisationAdmin(djadmin.ModelAdmin):
    list_display = ("name", "mode", "created_at")
    list_filter = ("mode",)
    search_fields = ("name",)

@djadmin.register(Process)
class ProcessAdmin(GISModelAdmin):
    list_display = ("name", "mode", "commodity", "organisation")
    list_filter = ("mode", "organisation")
    search_fields = ("name", "commodity")

@djadmin.register(Document)
class DocumentAdmin(djadmin.ModelAdmin):
    list_display = ("title", "timestamp", "doc_type", "confidentiality", "process", "created_by") # removed approved_by -> not in model
    list_filter = ("doc_type", "confidentiality", "organisation")
    search_fields = ("title", "checksum_sha256")
    readonly_fields = ("checksum_sha256", "created_at", "updated_at")

@djadmin.register(Prospect)
class ProspectAdmin(djadmin.ModelAdmin):
    list_display = ("name", "organisation", "process", "created_at")
    list_filter = ("organisation",)
    search_fields = ("name",)

@djadmin.register(Tenement)
class TenementAdmin(djadmin.ModelAdmin):
    list_display = ("name", "organisation", "process", "created_at")
    list_filter = ("organisation",)
    search_fields = ("name",)

@djadmin.register(Drillhole)
class DrillholeAdmin(djadmin.ModelAdmin):
    list_display = ("name", "organisation", "process", "created_at")
    list_filter = ("organisation",)
    search_fields = ("name",)

# USER PERMISSIONS & AUDIT ---------------------------------

@djadmin.register(UserProfile)
class UserProfileAdmin(djadmin.ModelAdmin):
    list_display = ("user", "role", "organisation", "clearance_level", "can_approve_jorc", "can_approve_valmin")
    list_filter = ("role", "clearance_level", "can_approve_jorc", "can_approve_valmin", "organisation")
    search_fields = ("user__username", "user__email", "employee_id")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("User Information", {
            "fields": ("user", "organisation", "role", "clearance_level")
        }),
        ("Contact Details", {
            "fields": ("department", "phone", "employee_id")
        }),
        ("Approval Permissions", {
            "fields": ("can_approve_jorc", "can_approve_valmin")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

@djadmin.register(AuditLog)
class AuditLogAdmin(djadmin.ModelAdmin):
    list_display = ("user", "action", "content_type", "object_id", "timestamp", "ip_address")
    list_filter = ("action", "content_type", "timestamp")
    search_fields = ("user__username", "description", "object_id")
    readonly_fields = ("user", "action", "content_type", "object_id", "description", "ip_address", "user_agent", "timestamp")
    date_hierarchy = "timestamp"

    def has_add_permission(self, request):
        return False  # Audit logs should only be created programmatically

    def has_change_permission(self, request, obj=None):
        return False  # Audit logs should be immutable

@djadmin.register(ApprovalWorkflow)
class ApprovalWorkflowAdmin(djadmin.ModelAdmin):
    list_display = ("workflow_type", "status", "content_type", "object_id", "submitted_by", "approved_by", "submitted_at")
    list_filter = ("workflow_type", "status", "submitted_at")
    search_fields = ("submission_notes", "approval_notes", "object_id")
    readonly_fields = ("submitted_at", "reviewed_at")

    fieldsets = (
        ("Workflow Details", {
            "fields": ("workflow_type", "status", "content_type", "object_id")
        }),
        ("Participants", {
            "fields": ("submitted_by", "approved_by")
        }),
        ("Notes", {
            "fields": ("submission_notes", "approval_notes")
        }),
        ("Timestamps", {
            "fields": ("submitted_at", "reviewed_at")
        }),
    )

@djadmin.register(DocumentView)
class DocumentViewAdmin(djadmin.ModelAdmin):
    list_display = ("user", "document", "viewed_at", "ip_address")
    list_filter = ("viewed_at",)
    search_fields = ("user__username", "document__title")
    readonly_fields = ("user", "document", "viewed_at", "ip_address")
    date_hierarchy = "viewed_at"

    def has_add_permission(self, request):
        return False  # View tracking should only be created programmatically

    def has_change_permission(self, request, obj=None):
        return False  # View records should be immutable
