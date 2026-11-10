from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Profile


class IsOrgMember(BasePermission):
    """User must belong to an organisation. Viewers can only read."""

    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        if profile is None:
            return False
        if request.method in SAFE_METHODS:
            return True
        if profile.role != Profile.Role.ADMIN:
            self.message = "Viewers cannot create, change or delete data."
            return False
        return True
