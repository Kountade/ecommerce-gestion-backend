# users/permissions.py
from rest_framework import permissions


# ============================================================
# Permissions simples par rôle
# ============================================================
class IsAdmin(permissions.BasePermission):
    """Admin uniquement"""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role == 'admin')

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsAdminOrVendeur(permissions.BasePermission):
    """Admin ou vendeur"""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'vendeur'])

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsGestionnaire(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire'])

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsComptable(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'comptable'])

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsMagasinier(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire', 'magasinier'])

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsCaissier(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire', 'caissier'])

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsLivreur(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire', 'livreur'])

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


# ============================================================
# Permissions lecture seule / écriture
# ============================================================
class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated
                    and request.user.role == 'admin')

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsGestionnaireOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire'])

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsStaffOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_staff)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


# ============================================================
# Propre / staff
# ============================================================
class IsOwnerOrStaff(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff or request.user.role == 'admin':
            return True
        if hasattr(obj, 'user'):
            return obj.user == request.user
        if hasattr(obj, 'created_by'):
            return obj.created_by == request.user
        return False


# ============================================================
# ✅ Permission dynamique via FACTORY (le pattern DRF correct)
# ============================================================
class HasRolePermission(permissions.BasePermission):
    """
    Utilisation : permission_classes = [HasRolePermission.for_permission('manage_stock')]
    """
    required_permission = None

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if not self.required_permission:
            return True
        return request.user.has_permission(self.required_permission)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)

    @classmethod
    def for_permission(cls, permission_name):
        """Retourne une sous-classe pré-configurée"""
        return type(
            f'HasRolePermission_{permission_name}',
            (cls,),
            {'required_permission': permission_name}
        )


class PermissionFactory:
    """Factory utilitaire"""

    @staticmethod
    def require_permission(permission_name):
        return HasRolePermission.for_permission(permission_name)

    @staticmethod
    def require_any_role(roles):
        return type(
            'RequireAnyRole',
            (permissions.BasePermission,),
            {
                'has_permission': lambda self, request, view: (
                    bool(request.user and request.user.is_authenticated
                         and request.user.role in roles)
                ),
                'has_object_permission': lambda self, request, view, obj: (
                    bool(request.user and request.user.is_authenticated
                         and request.user.role in roles)
                ),
            }
        )


# ============================================================
# Permissions métier pré-définies
# ============================================================
class CanViewProducts(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire', 'magasinier', 'caissier', 'comptable'])


class CanEditProducts(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire', 'magasinier'])


class CanViewStock(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire', 'magasinier', 'caissier'])


class CanManageStock(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire', 'magasinier'])


class CanViewSales(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire', 'caissier', 'comptable'])


class CanCreateSales(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire', 'caissier'])


class CanViewFinances(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire', 'comptable'])


class CanManageFinances(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'comptable'])


class CanViewUsers(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role == 'admin')


class CanManageUsers(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role == 'admin')


class CanViewReports(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire', 'comptable'])


class CanManageDeliveries(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role in ['admin', 'gestionnaire', 'livreur'])


class CanManageLots(permissions.BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return request.user.role in ['admin', 'gestionnaire', 'magasinier', 'caissier']
        return request.user.role in ['admin', 'gestionnaire', 'magasinier']


class CanManageExpiryAlerts(permissions.BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return request.user.role in ['admin', 'gestionnaire', 'magasinier']
        return request.user.role in ['admin', 'gestionnaire']


class CanManageInventory(permissions.BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return request.user.role in ['admin', 'gestionnaire', 'magasinier']
        return request.user.role in ['admin', 'gestionnaire']