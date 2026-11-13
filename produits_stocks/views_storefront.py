# apps/produits_stocks/views_storefront.py
# ============================================================
# API PUBLIQUE - CATALOGUE PRODUITS POUR LE SITE E-COMMERCE
# Accessible sans authentification (AllowAny)
# ============================================================

from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import models
from django.db.models import Q, Sum, Count, Avg, Min, Max
from django.db.models.functions import Coalesce
from django_filters.rest_framework import DjangoFilterBackend

from .models import Product, Category, Warehouse, Lot
from .serializers import (
    ProductListSerializer,
    ProductLiteSerializer,
    ProductDetailSerializer,
    CategorySerializer,
    CategoryListSerializer,
)
from .filters import ProductFilter  # ✅ Filtre personnalisé (accepte ID ou Code)
from .pagination import ProductPagination


# ============================================================
# CATALOGUE PUBLIC - PRODUITS
# ============================================================
class PublicProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API publique pour le site e-commerce.
    
    Endpoints :
    - GET /api/store/products/                 → catalogue paginé
    - GET /api/store/products/{id}/            → détail produit
    - GET /api/store/products/featured/        → produits vedettes (page accueil)
    - GET /api/store/products/new-arrivals/    → nouveaux produits
    - GET /api/store/products/best-sellers/    → meilleures ventes
    - GET /api/store/products/{id}/related/    → produits similaires
    - GET /api/store/products/search/          → recherche rapide
    - GET /api/store/products/filters/         → options de filtres (prix, catégories)
    
    Filtres disponibles :
    - ?category=<id> OU ?category=<code>  (ex: 1 ou high-tech)
    - ?search=<texte>
    - ?min_price=<montant>&max_price=<montant>
    - ?in_stock=true
    - ?is_featured=true
    - ?ordering=selling_price|-created_at|name
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ProductListSerializer
    pagination_class = ProductPagination
    
    # ✅ Backends : DjangoFilter (pour le ProductFilter custom) + Search + Ordering
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ProductFilter  # ✅ Accepte ID ou code de catégorie
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['selling_price', 'created_at', 'name']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def get_queryset(self):
        """
        Queryset public : uniquement les produits actifs avec du stock disponible.
        """
        qs = (
            Product.objects
            .filter(status='active')
            .select_related('category', 'unit')
            .annotate(
                total_stock=Coalesce(
                    Sum(
                        'lots__current_quantity',
                        filter=(
                            Q(lots__status__in=['good', 'expiring']) &
                            Q(lots__is_blocked=False)
                        )
                    ),
                    0
                )
            )
            .filter(total_stock__gt=0)
        )

        # ✅ Le filtre `category` est géré par ProductFilter (accepte ID ou code)
        # Les autres filtres simples sont gérés manuellement ci-dessous.

        # Filtre prix
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            try:
                qs = qs.filter(selling_price__gte=float(min_price))
            except (ValueError, TypeError):
                pass
        if max_price:
            try:
                qs = qs.filter(selling_price__lte=float(max_price))
            except (ValueError, TypeError):
                pass

        # Filtre produits vedettes
        is_featured = self.request.query_params.get('is_featured')
        if is_featured == 'true':
            qs = qs.filter(is_featured=True)

        # Filtre produits en promotion
        on_sale = self.request.query_params.get('on_sale')
        if on_sale == 'true':
            qs = qs.filter(promo_price__isnull=False)

        return qs

    # ============================================================
    # PRODUITS VEDETTES (Page d'accueil)
    # ============================================================
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Retourne les 8 produits vedettes pour la page d'accueil."""
        products = (
            self.get_queryset()
            .filter(is_featured=True)
            .order_by('-created_at')[:8]
        )
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)

    # ============================================================
    # NOUVEAUX PRODUITS
    # ============================================================
    @action(detail=False, methods=['get'], url_path='new-arrivals')
    def new_arrivals(self, request):
        """Retourne les 8 produits les plus récents."""
        products = self.get_queryset().order_by('-created_at')[:8]
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)

    # ============================================================
    # MEILLEURES VENTES
    # ============================================================
    @action(detail=False, methods=['get'], url_path='best-sellers')
    def best_sellers(self, request):
        """Retourne les 8 produits les plus vendus."""
        from ventes_clients.models import LigneVente

        # IDs des produits les plus vendus
        top_products_ids = (
            LigneVente.objects
            .values('product_id')
            .annotate(total_sold=Sum('quantity'))
            .filter(total_sold__gt=0)
            .order_by('-total_sold')
            .values_list('product_id', flat=True)[:20]
        )

        if not top_products_ids:
            # Fallback : produits vedettes
            products = self.get_queryset().filter(is_featured=True)[:8]
        else:
            # Conserver l'ordre des ventes
            products_qs = self.get_queryset().filter(id__in=top_products_ids)
            products_map = {p.id: p for p in products_qs}
            products = [
                products_map[pid] for pid in top_products_ids
                if pid in products_map
            ][:8]

        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)

    # ============================================================
    # PRODUITS SIMILAIRES
    # ============================================================
    @action(detail=True, methods=['get'])
    def related(self, request, pk=None):
        """Retourne 8 produits de la même catégorie."""
        product = self.get_object()
        related = (
            self.get_queryset()
            .filter(category=product.category)
            .exclude(id=product.id)
            .order_by('-created_at')[:8]
        )
        serializer = self.get_serializer(related, many=True)
        return Response(serializer.data)

    # ============================================================
    # RECHERCHE RAPIDE (autocomplete)
    # ============================================================
    @action(detail=False, methods=['get'])
    def search(self, request):
        """Recherche rapide de produits (pour l'autocomplete)."""
        query = request.query_params.get('q', '').strip()
        if not query or len(query) < 2:
            return Response({'results': [], 'count': 0})

        try:
            limit = min(int(request.query_params.get('limit', 10)), 20)
        except (ValueError, TypeError):
            limit = 10

        products = (
            self.get_queryset()
            .filter(
                Q(name__icontains=query) |
                Q(code__icontains=query) |
                Q(barcode__icontains=query) |
                Q(description__icontains=query)
            )
            .order_by('-is_featured', '-created_at')[:limit]
        )

        serializer = ProductLiteSerializer(
            products, many=True, context={'request': request}
        )
        return Response({
            'count': len(serializer.data),
            'results': serializer.data
        })

    # ============================================================
    # FILTRES DISPONIBLES (pour la sidebar du catalogue)
    # ============================================================
    @action(detail=False, methods=['get'])
    def filters(self, request):
        """
        Retourne les options de filtres disponibles pour la sidebar :
        - Catégories actives avec nombre de produits
        - Prix min/max du catalogue
        """
        qs = self.get_queryset()

        # ✅ Prix min/max (avec l'import correct de models)
        prices = qs.aggregate(
            min_price=Min('selling_price'),
            max_price=Max('selling_price'),
        )

        # Catégories avec comptage
        categories = (
            Category.objects
            .filter(is_active=True, products__status='active')
            .annotate(
                products_count=Count(
                    'products',
                    filter=Q(products__status='active')
                )
            )
            .filter(products_count__gt=0)
            .order_by('name')
        )

        categories_data = [
            {
                'id': cat.id,
                'name': cat.name,
                'code': cat.code,
                'products_count': cat.products_count,
            }
            for cat in categories
        ]

        return Response({
            'categories': categories_data,
            'price_range': {
                'min': prices['min_price'] or 0,
                'max': prices['max_price'] or 0,
            }
        })


# ============================================================
# CATALOGUE PUBLIC - CATÉGORIES
# ============================================================
class PublicCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API publique pour les catégories.
    
    Endpoints :
    - GET /api/store/categories/         → toutes les catégories avec comptage
    - GET /api/store/categories/{id}/    → détail + sous-catégories
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CategorySerializer

    def get_queryset(self):
        return (
            Category.objects
            .filter(is_active=True)
            .annotate(
                products_count_annotated=Count(
                    'products',
                    filter=Q(products__status='active'),
                    distinct=True
                )
            )
            .order_by('name')
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    @action(detail=False, methods=['get'])
    def tree(self, request):
        """Retourne l'arbre complet des catégories (parent + enfants)."""
        root_categories = self.get_queryset().filter(parent__isnull=True)
        serializer = self.get_serializer(root_categories, many=True)
        return Response(serializer.data)


# ============================================================
# ENTREPÔTS PUBLICS (pour la page "Retrait en magasin")
# ============================================================
class PublicWarehouseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API publique pour lister les entrepôts/points de retrait actifs.
    Utilisé dans la page checkout du site.
    """
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Warehouse.objects.filter(is_active=True).order_by('name')

    def list(self, request):
        warehouses = self.get_queryset()
        data = [
            {
                'id': w.id,
                'name': w.name,
                'code': w.code,
                'type': w.type,
                'address': w.address,
                'city': w.city,
                'country': w.country,
                'phone': w.phone,
                'email': w.email,
            }
            for w in warehouses
        ]
        return Response(data)