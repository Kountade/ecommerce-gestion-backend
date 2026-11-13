from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, UnitMeasureViewSet, ProductViewSet, WarehouseViewSet,
    LotViewSet, StockViewSet, StockMovementViewSet, ExpiryAlertViewSet,
    InventoryViewSet, DashboardStatsViewSet, TransferViewSet,
    InventoryLineViewSet,
)
from .views_storefront import (
    PublicProductViewSet, PublicCategoryViewSet, PublicWarehouseViewSet,
)

router = DefaultRouter()
# --- Back-office (admin) ---
router.register('categories', CategoryViewSet, basename='categories')
router.register('unit-measures', UnitMeasureViewSet, basename='unit-measures')
router.register('products', ProductViewSet, basename='products')
router.register('warehouses', WarehouseViewSet, basename='warehouses')
router.register('lots', LotViewSet, basename='lots')
router.register('stocks', StockViewSet, basename='stocks')
router.register('movements', StockMovementViewSet, basename='movements')
router.register('expiry-alerts', ExpiryAlertViewSet, basename='expiry-alerts')
router.register('inventories', InventoryViewSet, basename='inventories')
router.register('inventory-lines', InventoryLineViewSet, basename='inventory-lines')
router.register('transfers', TransferViewSet, basename='transfers')
router.register('dashboard-stats', DashboardStatsViewSet, basename='dashboard-stats')

# --- E-commerce (public) ---
router.register('store/products', PublicProductViewSet, basename='store-products')
router.register('store/categories', PublicCategoryViewSet, basename='store-categories')
router.register('store/warehouses', PublicWarehouseViewSet, basename='store-warehouses')

urlpatterns = [
    path('', include(router.urls)),
]