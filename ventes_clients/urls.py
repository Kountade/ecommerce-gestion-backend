# apps/ventes_clients/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ClientViewSet, DevisViewSet, VenteViewSet, FactureViewSet,
    PaiementViewSet, AvoirViewSet, TaxeViewSet, RemiseViewSet,
    SalesDashboardStatsViewSet, WalletViewSet, ClientWalletViewSet,
)
from .views_storefront import (
    FavoriteViewSet, StoreCheckoutViewSet, MyInvoicesViewSet,
)
# ✅ IMPORT DES VIEWSETS ECOMMERCE (Commandes + Paniers)
from .views_ecommerce_admin import AdminEcommerceOrdersViewSet, AbandonedCartViewSet

router = DefaultRouter()

# ============================================================
# BACK-OFFICE
# ============================================================
router.register('clients', ClientViewSet, basename='clients')
router.register('devis', DevisViewSet, basename='devis')
router.register('ventes', VenteViewSet, basename='ventes')
router.register('factures', FactureViewSet, basename='factures')
router.register('paiements', PaiementViewSet, basename='paiements')
router.register('avoirs', AvoirViewSet, basename='avoirs')
router.register('taxes', TaxeViewSet, basename='taxes')
router.register('remises', RemiseViewSet, basename='remises')
router.register('dashboard-stats', SalesDashboardStatsViewSet, basename='dashboard-stats')
router.register('wallets', WalletViewSet, basename='wallets')
router.register('client-wallets', ClientWalletViewSet, basename='client-wallets')

# ============================================================
# ✅ ECOMMERCE ADMIN (SANS LE PRÉFIXE "admin/")
# ============================================================
# Commandes en ligne
router.register('ecommerce-admin/orders', AdminEcommerceOrdersViewSet, basename='ecommerce-admin-orders')

# Paniers abandonnés
router.register('ecommerce-admin/abandoned-carts', AbandonedCartViewSet, basename='ecommerce-admin-abandoned-carts')

# ============================================================
# E-COMMERCE (client connecté)
# ============================================================
router.register('store/favorites', FavoriteViewSet, basename='store-favorites')
router.register('store/checkout', StoreCheckoutViewSet, basename='store-checkout')
router.register('store/my-invoices', MyInvoicesViewSet, basename='store-my-invoices')

urlpatterns = [
    path('', include(router.urls)),
]