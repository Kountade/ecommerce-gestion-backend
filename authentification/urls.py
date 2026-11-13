# config/urls.py
from django.contrib import admin
from django.urls import path, include
from knox import views as knox_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # ============================================================
    # API MODULES
    # ============================================================
    
    # ✅ 1. TRÉSORERIE EN PREMIER (pour éviter le conflit sur /dashboard/)
    # Attention : le dashboard de trésorerie est sur /dashboard-tresorerie/
    # (à renommer dans tresorerie/urls.py)
    path('', include('tresorerie.urls')),

    # ✅ 2. DASHBOARD PRINCIPAL (dashboard admin)
    path('', include('dashboard.urls')),

    # ✅ 3. AUTRES MODULES
    path('', include('users.urls')),
    path('', include('produits_stocks.urls')),
    path('', include('ventes_clients.urls')),
    path('', include('achats_fournisseurs.urls')),
    path('', include('finances.urls')),

    # ============================================================
    # AUTH
    # ============================================================
    path('logout/', knox_views.LogoutView.as_view(), name='knox_logout'),
    path('logoutall/', knox_views.LogoutAllView.as_view(), name='knox_logoutall'),
    path('api/password_reset/',
         include('django_rest_passwordreset.urls', namespace='password_reset')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)