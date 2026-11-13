# apps/produits_stocks/filters.py
import django_filters
from .models import Product

class ProductFilter(django_filters.FilterSet):
    # On accepte l'ID (ex: 1) OU le code/slug (ex: high-tech)
    category = django_filters.CharFilter(method='filter_category')

    class Meta:
        model = Product
        fields = ['category', 'status', 'is_featured']

    def filter_category(self, queryset, name, value):
        if not value:
            return queryset
            
        # Si c'est un nombre, on filtre par ID
        if str(value).isdigit():
            return queryset.filter(category_id=value)
        
        # Sinon, on cherche par le code de la catégorie
        # (car votre modèle Category a un champ 'code' et non 'slug')
        return queryset.filter(category__code=value)