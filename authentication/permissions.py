
from rest_framework.permissions import BasePermission
from wish_bot.db import get_admin_collection

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


class IsAgentOrSuperAdmin(BasePermission):
    """
    Allows full access to superadmin.
    Agents can access only objects assigned to their widget list.
    """

    def has_permission(self, request, view):
        user = getattr(request, "user", {})
        role = user.get("role")

        # Superadmin has global permission
        if role == "superadmin":
            return True

        # Agent needs to be verified per object (done in has_object_permission)
        return role == "agent"

    def has_object_permission(self, request, view, obj):
        user = getattr(request, "user", {})
        role = user.get("role")

        if role == "superadmin":
            return True

        if role == "agent":
            agent_id = user.get("admin_id")
            admin_doc = get_admin_collection().find_one({"admin_id": agent_id})
            assigned_widgets = admin_doc.get("assigned_widgets", []) if admin_doc else []

            widget_id = obj.get("widget_id")

            if widget_id in assigned_widgets:
                return True
            else:
                logger.info(f"Access denied: widget_id {widget_id} not in agent's assigned_widgets.")
                return False

        return False
