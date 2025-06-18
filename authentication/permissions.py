
from rest_framework.permissions import BasePermission

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request, "user") and isinstance(request.user, dict) and request.user.get("role") == "admin"

import logging
logger = logging.getLogger(__name__)

class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        if not isinstance(request.user, dict):
            logger.warning("No authenticated user found")
            return False
        if request.user.get("role") != "superadmin":
            logger.warning(f"Access denied. User role: {request.user.get('role')}")
            return False
        return True

class IsAdminOrSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request, "user") and isinstance(request.user, dict) and request.user.get("role") in ["admin", "superadmin"]
