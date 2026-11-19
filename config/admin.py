from django.contrib.admin import AdminSite


class PlatformAdminSite(AdminSite):
    """The unscoped Django admin is a platform-superuser interface."""

    def has_permission(self, request):
        return super().has_permission(request) and request.user.is_superuser
