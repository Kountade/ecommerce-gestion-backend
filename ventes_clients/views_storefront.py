# apps/ventes_clients/views_storefront.py
# ============================================================
# API CLIENT - FAVORIS + COMMANDES POUR LE SITE E-COMMERCE
# ============================================================

import logging
from datetime import date, timedelta
from decimal import Decimal

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Sum, Q, Count
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

# ✅ IMPORT DU MODÈLE ORDERMESSAGE
from .models import Client, Vente, LigneVente, Favorite, Facture, Paiement, OrderMessage
from .serializers import VenteListSerializer, VenteDetailSerializer
from produits_stocks.models import Product, Lot, Stock, Warehouse

# ✅ NOUVEAU : import des fonctions d'email
from .utils.emails import (
    send_order_confirmation_email,
    send_order_confirmed_email,
    send_order_delivering_email,
    send_order_delivered_email,
    send_order_cancelled_email,
)

logger = logging.getLogger(__name__)


# ============================================================
# FAVORIS
# ============================================================
class FavoriteViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _get_favorites_qs(self):
        return (
            Favorite.objects
            .filter(user=self.request.user)
            .select_related('product', 'product__category', 'product__unit')
            .order_by('-created_at')
        )

    def list(self, request):
        favorites = self._get_favorites_qs()
        results = []
        for fav in favorites:
            product = fav.product
            stock = product.lots.filter(
                status__in=['good', 'expiring'],
                is_blocked=False
            ).aggregate(t=Sum('current_quantity'))['t'] or 0

            results.append({
                'id': fav.id,
                'product_id': product.id,
                'product_name': product.name,
                'product_code': product.code,
                'product_price': str(product.selling_price),
                'product_promo_price': str(product.promo_price) if product.promo_price else None,
                'product_image': product.image.url if product.image else None,
                'product_category': product.category.name if product.category else None,
                'in_stock': stock > 0,
                'stock_quantity': stock,
                'created_at': fav.created_at,
            })

        return Response({'count': len(results), 'results': results})

    @action(detail=False, methods=['get'])
    def ids(self, request):
        ids = list(self._get_favorites_qs().values_list('product_id', flat=True))
        return Response({'product_ids': ids, 'count': len(ids)})

    @action(detail=False, methods=['post'])
    def toggle(self, request):
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'error': 'product_id est requis'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            product = Product.objects.get(id=product_id, status='active')
        except Product.DoesNotExist:
            return Response({'error': 'Produit introuvable'},
                            status=status.HTTP_404_NOT_FOUND)

        fav, created = Favorite.objects.get_or_create(
            user=request.user, product=product)

        if created:
            return Response({
                'status': 'added',
                'message': f'{product.name} ajouté aux favoris',
                'product_id': product.id,
                'is_favorite': True,
            })
        else:
            fav.delete()
            return Response({
                'status': 'removed',
                'message': f'{product.name} retiré des favoris',
                'product_id': product.id,
                'is_favorite': False,
            })

    @action(detail=False, methods=['post'])
    def clear(self, request):
        count, _ = Favorite.objects.filter(user=request.user).delete()
        return Response({
            'status': 'success',
            'message': f'{count} favori(s) supprimé(s)',
            'deleted_count': count,
        })


# ============================================================
# CHECKOUT
# ============================================================
@method_decorator(csrf_exempt, name='dispatch')
class StoreCheckoutViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _get_client(self, request):
        client = Client.get_or_create_for_user(request.user)
        if not client:
            raise ValueError("Impossible de créer/récupérer le profil client")
        return client

    @action(detail=False, methods=['post'], url_path='validate-cart')
    def validate_cart(self, request):
        items = request.data.get('items', [])
        if not items:
            return Response(
                {'valid': False, 'errors': ['Le panier est vide'], 'items': []},
                status=status.HTTP_400_BAD_REQUEST)

        errors = []
        items_validated = []
        total = Decimal('0.00')

        for item in items:
            product_id = item.get('product_id')
            qty = item.get('quantity', 0)

            try:
                qty = int(qty)
            except (ValueError, TypeError):
                errors.append(f"Quantité invalide pour product_id={product_id}")
                continue

            if qty <= 0:
                errors.append(f"Quantité > 0 pour product_id={product_id}")
                continue

            try:
                product = Product.objects.get(id=product_id, status='active')
            except Product.DoesNotExist:
                errors.append(f"Produit {product_id} introuvable")
                continue

            stock = product.lots.filter(
                status__in=['good', 'expiring'],
                is_blocked=False
            ).aggregate(t=Sum('current_quantity'))['t'] or 0

            if stock < qty:
                errors.append(
                    f"Stock insuffisant pour {product.name} "
                    f"(disponible: {stock}, demandé: {qty})")
                continue

            unit_price = product.promo_price if product.promo_price else product.selling_price
            line_total = unit_price * qty
            total += line_total

            items_validated.append({
                'product_id': product.id,
                'product_name': product.name,
                'product_code': product.code,
                'quantity': qty,
                'unit_price': str(unit_price),
                'line_total': str(line_total),
                'available_stock': stock,
                'is_available': True,
            })

        return Response({
            'valid': len(errors) == 0,
            'errors': errors,
            'items': items_validated,
            'total': str(total) if len(errors) == 0 else None,
        })

    @action(detail=False, methods=['post'])
    def checkout(self, request):
        try:
            items = request.data.get('items', [])
            if not items:
                return Response(
                    {'error': 'Le panier est vide'},
                    status=status.HTTP_400_BAD_REQUEST)

            try:
                client = self._get_client(request)
            except ValueError as e:
                return Response({'error': str(e)},
                                status=status.HTTP_400_BAD_REQUEST)

            if client.statut == 'bloque':
                return Response(
                    {'error': 'Votre compte est bloqué.'},
                    status=status.HTTP_403_FORBIDDEN)

            errors = []
            lignes_data = []
            total = Decimal('0.00')

            for item in items:
                product_id = item.get('product_id')
                try:
                    qty = int(item.get('quantity', 0))
                except (ValueError, TypeError):
                    errors.append(f"Quantité invalide pour product_id={product_id}")
                    continue

                if qty <= 0:
                    errors.append(f"Quantité > 0 pour product_id={product_id}")
                    continue

                try:
                    product = Product.objects.get(id=product_id, status='active')
                except Product.DoesNotExist:
                    errors.append(f"Produit {product_id} introuvable")
                    continue

                stock = product.lots.filter(
                    status__in=['good', 'expiring'],
                    is_blocked=False
                ).aggregate(t=Sum('current_quantity'))['t'] or 0

                if stock < qty:
                    errors.append(
                        f"Stock insuffisant pour {product.name} "
                        f"(disponible: {stock}, demandé: {qty})")
                    continue

                unit_price = product.promo_price if product.promo_price else product.selling_price
                line_total = unit_price * qty
                total += line_total

                lignes_data.append({
                    'product': product,
                    'quantity': qty,
                    'unit_price': unit_price,
                    'total': line_total,
                })

            if errors:
                return Response(
                    {'error': 'Certains produits ne sont pas disponibles',
                     'details': errors},
                    status=status.HTTP_400_BAD_REQUEST)

            if not lignes_data:
                return Response(
                    {'error': 'Aucune ligne valide dans le panier'},
                    status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                year = date.today().year
                last = Vente.objects.filter(
                    invoice_number__startswith=f"CMD-{year}-"
                ).order_by('-id').first()

                if last:
                    try:
                        num = int(last.invoice_number.split('-')[-1]) + 1
                    except (ValueError, IndexError):
                        num = 1
                else:
                    num = 1

                order_number = f"CMD-{year}-{num:04d}"

                default_warehouse = Warehouse.objects.filter(is_active=True).first()
                if not default_warehouse:
                    return Response(
                        {'error': "Aucun entrepôt actif."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                vente = Vente.objects.create(
                    invoice_number=order_number,
                    client=client,
                    client_name=client.name,
                    client_phone=client.phone or request.user.phone_number or '',
                    client_email=request.user.email,
                    client_address=request.data.get('delivery_address') or client.address,
                    warehouse=default_warehouse,
                    subtotal=total,
                    total=total,
                    status='draft',
                    payment_method=request.data.get('payment_method', 'mobile_money'),
                    payment_status='pending',
                    amount_paid=Decimal('0.00'),
                    amount_due=total,
                    delivery_method=request.data.get('delivery_method', 'livraison'),
                    delivery_address=request.data.get('delivery_address', ''),
                    delivery_status='pending',
                    notes=request.data.get('notes', ''),
                    internal_notes='Commande passée depuis le site web',
                    created_by=request.user,
                )

                for ligne in lignes_data:
                    LigneVente.objects.create(
                        sale=vente,
                        product=ligne['product'],
                        quantity=ligne['quantity'],
                        unit_price=ligne['unit_price'],
                        price_type='detail',
                        total=ligne['total'],
                    )

                vente.calculate_totals()
                vente.generate_qr_code()
                vente.save()

                logger.info(
                    f"✅ Commande web créée : {vente.invoice_number} "
                    f"par {request.user.email} - Total : {vente.total}")

                # ✅ NOUVEAU : Envoi de l'email de confirmation
                # transaction.on_commit : l'email n'est envoyé QUE si la transaction réussit
                transaction.on_commit(
                    lambda: send_order_confirmation_email(vente)
                )

                return Response({
                    'status': 'success',
                    'message': 'Commande créée avec succès',
                    'order_id': vente.id,
                    'order_number': vente.invoice_number,
                    'total': str(vente.total),
                    'status_order': vente.status,
                    'payment_status': vente.payment_status,
                    'estimated_delivery': (date.today() + timedelta(days=3)).isoformat(),
                    'email_sent': True,
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.exception("Erreur création commande web")
            return Response(
                {'error': f"Erreur: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='my-orders')
    def my_orders(self, request):
        try:
            client = self._get_client(request)
        except ValueError as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        orders = Vente.objects.filter(client=client).order_by('-sale_date')

        status_param = request.query_params.get('status')
        if status_param:
            status_list = [s.strip() for s in status_param.split(',') if s.strip()]
            orders = orders.filter(status__in=status_list)

        payment_status = request.query_params.get('payment_status')
        if payment_status:
            orders = orders.filter(payment_status=payment_status)

        serializer = VenteListSerializer(
            orders, many=True, context={'request': request})

        return Response({
            'count': orders.count(),
            'results': serializer.data
        })

    @action(detail=True, methods=['get'], url_path='my-orders/(?P<order_id>[^/.]+)')
    def order_detail(self, request, pk=None, order_id=None):
        try:
            client = self._get_client(request)
        except ValueError as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            vente = Vente.objects.get(id=order_id, client=client)
        except Vente.DoesNotExist:
            return Response(
                {'error': 'Commande introuvable'},
                status=status.HTTP_404_NOT_FOUND)

        serializer = VenteDetailSerializer(
            vente, context={'request': request})
        return Response(serializer.data)

    # ✅ ENDPOINT POUR LE NOMBRE DE MESSAGES NON LUS
    @action(detail=False, methods=['get'], url_path='unread-messages-count')
    def unread_messages_count(self, request):
        try:
            client = self._get_client(request)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        count = OrderMessage.objects.filter(
            vente__client=client,
            is_read=False
        ).count()

        return Response({'unread_count': count})

    # ✅ MESSAGES D'UNE COMMANDE (URL : /store/checkout/{id}/messages/)
    @action(detail=True, methods=['get'], url_path='messages')
    def order_messages(self, request, pk=None):
        try:
            client = self._get_client(request)
            vente = Vente.objects.get(id=pk, client=client)
        except (ValueError, Vente.DoesNotExist):
            return Response({'error': 'Commande introuvable'}, status=status.HTTP_404_NOT_FOUND)

        # On récupère les messages depuis la table OrderMessage
        db_messages = OrderMessage.objects.filter(vente=vente).order_by('created_at')
        
        messages = [
            {
                'id': msg.id,
                'text': msg.content,
                'date': msg.created_at,
                'is_read': msg.is_read
            } for msg in db_messages
        ]

        return Response({
            'order_number': vente.invoice_number,
            'status': vente.status,
            'messages': messages
        })

    @action(detail=True, methods=['post'], url_path='my-orders/(?P<order_id>[^/.]+)/cancel')
    def cancel_order(self, request, pk=None, order_id=None):
        try:
            client = self._get_client(request)
        except ValueError as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            vente = Vente.objects.get(id=order_id, client=client)
        except Vente.DoesNotExist:
            return Response({'error': 'Commande introuvable'},
                            status=status.HTTP_404_NOT_FOUND)

        if vente.status != 'draft':
            return Response(
                {'error': 'Commande déjà traitée'},
                status=status.HTTP_400_BAD_REQUEST)

        vente.status = 'cancelled'
        vente.internal_notes = (
            (vente.internal_notes or '') +
            f"\n[{timezone.now().strftime('%Y-%m-%d %H:%M')}] Annulée par le client")
        vente.save(update_fields=['status', 'internal_notes', 'updated_at'])

        # ✅ NOUVEAU : Email d'annulation (le client a annulé sa propre commande)
        transaction.on_commit(
            lambda: send_order_cancelled_email(vente, reason="Annulée par le client")
        )

        return Response({
            'status': 'success',
            'message': 'Commande annulée',
            'order_number': vente.invoice_number,
        })

    @action(detail=False, methods=['get'], url_path='my-stats')
    def my_stats(self, request):
        try:
            client = self._get_client(request)
        except ValueError as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        orders = Vente.objects.filter(client=client)

        by_status = dict(
            orders.values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        )

        total_spent = orders.exclude(status='cancelled').aggregate(
            t=Sum('total'))['t'] or Decimal('0.00')

        pending_payment = orders.filter(
            payment_status__in=['pending', 'partial']
        ).exclude(status='cancelled').aggregate(
            t=Sum('amount_due'))['t'] or Decimal('0.00')

        return Response({
            'client': {
                'id': client.id,
                'code': client.code,
                'name': client.name,
                'type': client.type,
                'statut': client.statut,
            },
            'stats': {
                'total_orders': orders.count(),
                'total_spent': str(total_spent),
                'pending_payment': str(pending_payment),
                'by_status': by_status,
            },
            'favorites_count': Favorite.objects.filter(user=request.user).count(),
        })


# ============================================================
# MES FACTURES
# ============================================================
class MyInvoicesViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _get_client(self, request):
        client = Client.get_or_create_for_user(request.user)
        if not client:
            raise ValueError("Impossible de récupérer le profil client")
        return client

    def list(self, request):
        try:
            client = self._get_client(request)
        except ValueError as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        from .serializers import FactureSerializer

        invoices = (
            Facture.objects
            .filter(client=client)
            .select_related('sale')
            .order_by('-invoice_date')
        )

        serializer = FactureSerializer(
            invoices, many=True, context={'request': request})

        return Response({
            'count': invoices.count(),
            'results': serializer.data
        })

    def retrieve(self, request, pk=None):
        try:
            client = self._get_client(request)
        except ValueError as e:
            return Response({'error': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        from .serializers import FactureSerializer

        try:
            facture = Facture.objects.get(id=pk, client=client)
        except Facture.DoesNotExist:
            return Response({'error': 'Facture introuvable'},
                            status=status.HTTP_404_NOT_FOUND)

        serializer = FactureSerializer(
            facture, context={'request': request})
        return Response(serializer.data)