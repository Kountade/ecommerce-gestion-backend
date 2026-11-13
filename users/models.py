# users/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.conf import settings
from django_rest_passwordreset.signals import reset_password_token_created
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is a required field')

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('is_active', True)
        return self.create_user(email, password, **extra_fields)

    def create_admin(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

    def create_vendeur(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', 'vendeur')
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self.create_user(email, password, **extra_fields)

    def create_client(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', 'client')
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Administrateur'),
        ('vendeur', 'Vendeur'),
        ('client', 'Client'),
    )

    email = models.EmailField(max_length=200, unique=True)
    birthday = models.DateField(null=True, blank=True)
    username = models.CharField(max_length=200, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    profile_picture = models.ImageField(
        upload_to='profiles/', null=True, blank=True)

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='vendeur'
    )

    is_online = models.BooleanField(default=False)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
        ordering = ['-date_joined']

    def __str__(self):
        return f"{self.get_full_name() or self.email} ({self.get_role_display()})"

    # ------------------------------------------------------------
    # Propriétés rôles
    # ------------------------------------------------------------
    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_vendeur(self):
        return self.role == 'vendeur'

    @property
    def is_client(self):
        return self.role == 'client'

    @property
    def has_admin_access(self):
        return self.role == 'admin'

    def change_role(self, new_role):
        if new_role in dict(self.ROLE_CHOICES).keys():
            self.role = new_role
            if new_role == 'admin':
                self.is_staff = True
                self.is_superuser = True
            else:
                self.is_staff = False
                self.is_superuser = False
            self.save()
            return True
        return False

    # ------------------------------------------------------------
    # Permissions applicatives (méthode maison)
    # ------------------------------------------------------------
    def get_permissions(self):
        permissions = {
            'admin': [
                'view_all', 'edit_all', 'manage_users',
                'view_finances', 'edit_finances', 'generate_reports',
                'view_products', 'edit_products', 'manage_stock',
                'process_sales', 'view_sales', 'manage_cash',
                'view_deliveries', 'update_delivery_status', 'delete_data',
            ],
            'vendeur': [
                'process_sales', 'view_sales', 'manage_cash', 'view_products',
            ],
            'client': [
                'view_products', 'process_orders', 'view_own_orders',
                'manage_own_profile', 'view_own_invoices', 'write_reviews',
            ],
        }
        return permissions.get(self.role, [])

    def has_permission(self, permission):
        """Permission maison (utilisée par HasRolePermission)"""
        return permission in self.get_permissions()

    # ------------------------------------------------------------
    # ✅ has_perm : méthode Django native (permissions admin)
    # ------------------------------------------------------------
    def has_perm(self, perm, obj=None):
        # Un admin a toutes les permissions
        if self.role == 'admin':
            return True
        return super().has_perm(perm, obj)


# ============================================================
# ✅ SIGNAL : envoi de l'email de réinitialisation
# ============================================================
@receiver(reset_password_token_created)
def password_reset_token_created(reset_password_token, *args, **kwargs):
    """
    Envoie un email HTML contenant le lien de réinitialisation.
    """
    # URL du frontend (configurable via settings.FRONTEND_URL)
    sitelink = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173/')
    if not sitelink.endswith('/'):
        sitelink += '/'

    token = str(reset_password_token.key)
    full_link = f"{sitelink}password-reset/{token}"

    context = {
        'full_link': full_link,
        'email_address': reset_password_token.user.email,
    }

    html_message = render_to_string("backend/email.html", context=context)
    plain_message = strip_tags(html_message)

    msg = EmailMultiAlternatives(
        subject=f"Réinitialisation de mot de passe pour {reset_password_token.user.email}",
        body=plain_message,
        from_email=settings.EMAIL_HOST_USER,   # ✅ cohérent avec le SMTP Gmail
        to=[reset_password_token.user.email],
    )
    msg.attach_alternative(html_message, "text/html")

    try:
        msg.send(fail_silently=False)
    except Exception as e:
        # On log l'erreur mais on ne crashe pas la requête HTTP
        import logging
        logging.getLogger(__name__).error(
            f"Erreur envoi email reset password : {e}"
        )