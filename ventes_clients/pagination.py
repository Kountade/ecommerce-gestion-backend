# apps/ventes_clients/pagination.py
from rest_framework.pagination import PageNumberPagination


class LargePagination(PageNumberPagination):
    """Pagination large : 50 éléments par défaut."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 500


class OptimizedPagination(PageNumberPagination):
    """Pagination standard : 20 éléments par défaut."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 200


class VentePagination(PageNumberPagination):
    """Pagination pour les ventes : 20 par défaut, max 100."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class StockPagination(PageNumberPagination):
    """Pagination pour les stocks."""
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 200


class MovementPagination(PageNumberPagination):
    """Pagination pour les mouvements (grand volume)."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 500


class LotPagination(PageNumberPagination):
    """Pagination pour les lots."""
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200


class ProductPagination(PageNumberPagination):
    """Pagination pour les produits (storefront)."""
    page_size = 24
    page_size_query_param = 'page_size'
    max_page_size = 100