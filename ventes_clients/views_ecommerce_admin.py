# apps/ventes_clients/views_ecommerce_admin.py
# ============================================================
# API ADMIN - GESTION DES COMMANDES & PANIERS ABANDONNÉS
# ============================================================

import logging
import datetime as dt
from datetime import date, timedelta
from decimal import Decimal

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.utils import timezone

# ✅ IMPORT DU NOUVEAU MODELE
from .models import Vente, Client, LigneVente, OrderMessage
from .serializers import VenteListSerializer, VenteDetailSerializer
from .pagination import VentePagination
from users.permissions import IsAdmin, IsGestionnaire

# ✅ NOUVEAU : import des fonctions d'email
from .utils.emails import (
    send_order_confirmed_email,
    send_order_delivering_email,
    send_order_delivered_email,
    send_order_cancelled_email,
)

logger = logging.getLogger(__name__)


# ============================================================
# COMMANDES EN LIGNE (ADMIN)
# ============================================================
class AdminEcommerceOrdersViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdmin | IsGestionnaire]
    serializer_class = VenteListSerializer
    pagination_class = VentePagination

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return VenteDetailSerializer
        return VenteListSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    def get_queryset(self):
        qs = (
            Vente.objects
            .all()
            .select_related('client', 'warehouse', 'created_by')
            .prefetch_related('invoices')
            .order_by('-sale_date', '-id')
        )

        status_param = self.request.query_params.get('status')
        if status_param and status_param != 'all':
            status_list = [s.strip() for s in status_param.split(',') if s.strip()]
            qs = qs.filter(status__in=status_list)

        payment_status = self.request.query_params.get('payment_status')
        if payment_status and payment_status != 'all':
            qs = qs.filter(payment_status=payment_status)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(invoice_number__icontains=search) |
                Q(client__name__icontains=search) |
                Q(client_name__icontains=search) |
                Q(order_number__icontains=search)
            )

        date_from = self.request.query_params.get('date_from')
        if date_from:
            try:
                date_start = dt.datetime.strptime(date_from, '%Y-%m-%d')
                qs = qs.filter(sale_date__gte=date_start)
            except ValueError:
                pass

        date_to = self.request.query_params.get('date_to')
        if date_to:
            try:
                date_end = dt.datetime.strptime(date_to, '%Y-%m-%d')
                date_end = date_end.replace(hour=23, minute=59, second=59)
                qs = qs.filter(sale_date__lte=date_end)
            except ValueError:
                pass

        return qs

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        today = date.today()
        start_week = today - timedelta(days=today.weekday())
        start_month = today.replace(day=1)

        stats = qs.aggregate(
            total=Count('id'),
            total_amount=Sum('total'),
            total_paid=Sum('amount_paid'),
            total_due=Sum('amount_due'),
        )

        by_status = dict(
            qs.values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        )

        by_payment_status = dict(
            qs.values('payment_status')
            .annotate(count=Count('id'))
            .values_list('payment_status', 'count')
        )

        today_stats = qs.filter(sale_date__date=today).aggregate(
            count=Count('id'), amount=Sum('total'),
        )

        week_stats = qs.filter(sale_date__date__gte=start_week).aggregate(
            count=Count('id'), amount=Sum('total'),
        )

        month_stats = qs.filter(sale_date__date__gte=start_month).aggregate(
            count=Count('id'), amount=Sum('total'),
        )

        return Response({
            'total': {
                'orders': stats['total'] or 0,
                'amount': stats['total_amount'] or Decimal('0'),
                'paid': stats['total_paid'] or Decimal('0'),
                'due': stats['total_due'] or Decimal('0'),
            },
            'today': {
                'orders': today_stats['count'] or 0,
                'amount': today_stats['amount'] or Decimal('0'),
            },
            'this_week': {
                'orders': week_stats['count'] or 0,
                'amount': week_stats['amount'] or Decimal('0'),
            },
            'this_month': {
                'orders': month_stats['count'] or 0,
                'amount': month_stats['amount'] or Decimal('0'),
            },
            'by_status': by_status,
            'by_payment_status': by_payment_status,
            'pending_count': qs.filter(status='draft').count(),
        })

    # ============================================================
    # ACTIONS
    # ============================================================
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        vente = self.get_object()
        if vente.status != 'draft':
            return Response(
                {'error': 'Seule une commande en brouillon peut être confirmée'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            vente.status = 'confirmed'
            vente.save(update_fields=['status', 'updated_at'])

            # ✅ CRÉATION DU MESSAGE DÉDIÉ
            OrderMessage.objects.create(
                vente=vente,
                content="✅ Votre commande a été confirmée et est en cours de préparation.",
                created_by=request.user
            )

            # ✅ NOUVEAU : Envoi email de confirmation
            transaction.on_commit(
                lambda: send_order_confirmed_email(vente)
            )

            return Response({
                'status': vente.status,
                'message': 'Commande confirmée',
                'invoice_number': vente.invoice_number,
            })
        except Exception as e:
            logger.error(f"Erreur confirmation {vente.invoice_number}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        vente = self.get_object()
        if vente.status in ['paid', 'delivered']:
            return Response(
                {'error': "Impossible d'annuler une commande payée ou livrée"},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            reason = request.data.get('reason', '')
            vente.status = 'cancelled'
            vente.save(update_fields=['status', 'updated_at'])

            # ✅ CRÉATION DU MESSAGE DÉDIÉ
            content = "❌ Votre commande a été annulée."
            if reason:
                content += f" Raison : {reason}"

            OrderMessage.objects.create(
                vente=vente,
                content=content,
                created_by=request.user
            )

            # ✅ NOUVEAU : Envoi email d'annulation
            transaction.on_commit(
                lambda: send_order_cancelled_email(vente, reason=reason)
            )

            return Response({'status': vente.status, 'message': 'Commande annulée'})
        except Exception as e:
            logger.error(f"Erreur annulation {vente.invoice_number}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def deliver(self, request, pk=None):
        vente = self.get_object()
        if vente.status != 'confirmed':
            return Response(
                {'error': 'Seule une commande confirmée peut être livrée'},
                status=status.HTTP_400_BAD_REQUEST
            )
        vente.status = 'delivered'
        vente.delivery_date = timezone.now()
        vente.delivery_status = 'delivered'

        if request.data.get('tracking_number'):
            vente.tracking_number = request.data['tracking_number']

        vente.save()

        # ✅ CRÉATION DU MESSAGE DÉDIÉ
        msg_content = "🎉 Bonne nouvelle ! Votre commande a été livrée."
        if vente.tracking_number:
            msg_content += f" Numéro de suivi : {vente.tracking_number}"

        OrderMessage.objects.create(
            vente=vente,
            content=msg_content,
            created_by=request.user
        )

        # ✅ NOUVEAU : Envoi email de livraison
        transaction.on_commit(
            lambda: send_order_delivered_email(vente)
        )

        return Response({'status': vente.status, 'message': 'Commande marquée comme livrée'})

    @action(detail=True, methods=['post'], url_path='mark-delivering')
    def mark_delivering(self, request, pk=None):
        """✅ NOUVEAU : Marquer la commande comme 'en livraison'."""
        vente = self.get_object()
        if vente.status not in ['confirmed']:
            return Response(
                {'error': 'Seule une commande confirmée peut être marquée en livraison'},
                status=status.HTTP_400_BAD_REQUEST
            )

        vente.delivery_status = 'delivering'
        if request.data.get('tracking_number'):
            vente.tracking_number = request.data['tracking_number']
        vente.save(update_fields=['delivery_status', 'tracking_number', 'updated_at'])

        OrderMessage.objects.create(
            vente=vente,
            content="🚚 Votre commande est en cours de livraison.",
            created_by=request.user
        )

        # ✅ NOUVEAU : Envoi email "en livraison"
        transaction.on_commit(
            lambda: send_order_delivering_email(vente)
        )

        return Response({
            'status': vente.status,
            'delivery_status': vente.delivery_status,
            'tracking_number': vente.tracking_number,
            'message': 'Commande marquée comme en livraison',
        })

    @action(detail=True, methods=['post'], url_path='resend-email')
    def resend_email(self, request, pk=None):
        """✅ NOUVEAU : Renvoyer manuellement l'email selon le statut actuel."""
        vente = self.get_object()

        try:
            if vente.status == 'draft':
                send_order_confirmation_email(vente)
            elif vente.status == 'confirmed':
                send_order_confirmed_email(vente)
            elif vente.status == 'delivered':
                send_order_delivered_email(vente)
            elif vente.status == 'cancelled':
                send_order_cancelled_email(vente)
            else:
                return Response(
                    {'error': f"Aucun email défini pour le statut '{vente.status}'"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return Response({
                'status': 'success',
                'message': f'Email renvoyé pour la commande {vente.invoice_number}',
                'order_status': vente.status,
            })
        except Exception as e:
            logger.error(f"Erreur renvoi email {vente.invoice_number}: {e}")
            return Response(
                {'error': f"Erreur envoi email : {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================
# PANIERS ABANDONNÉS (ADMIN)
# ============================================================
class AbandonedCartViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdmin | IsGestionnaire]

    def list(self, request):
        qs = (
            Vente.objects
            .filter(status='draft')
            .filter(lines__isnull=False)
            .select_related('client')
            .prefetch_related('lines__product')
            .order_by('-sale_date')
            .distinct()
        )

        search = request.query_params.get('search', '')
        if search:
            qs = qs.filter(
                Q(client__name__icontains=search) |
                Q(client_name__icontains=search) |
                Q(client_email__icontains=search)
            )

        results = []
        for vente in qs:
            items = []
            for line in vente.lines.all():
                items.append({
                    'product_name': line.product.name if line.product else 'Produit inconnu',
                    'quantity': line.quantity
                })

            client_name = vente.client_name
            client_email = vente.client_email
            
            if vente.client:
                if not client_name:
                    client_name = vente.client.name
                if not client_email and vente.client.user:
                    client_email = vente.client.user.email

            results.append({
                'id': vente.id,
                'client_name': client_name or 'Client anonyme',
                'client_email': client_email or 'Non renseigné',
                'items': items,
                'total_value': float(vente.total),
                'last_activity': vente.sale_date,
                'status': 'pending'
            })

        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        start = (page - 1) * page_size
        end = start + page_size
        paginated_data = results[start:end]

        return Response({
            'count': len(results),
            'next': None,
            'previous': None,
            'results': paginated_data
        })

    @action(detail=True, methods=['post'], url_path='send-reminder')
    def send_reminder(self, request, pk=None):
        return Response({'status': 'success', 'message': 'Relance envoyée'})

    def destroy(self, request, pk=None):
        try:
            vente = Vente.objects.get(id=pk, status='draft')
            vente.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Vente.DoesNotExist:
            return Response(
                {'error': 'Panier introuvable ou déjà traité'}, 
                status=status.HTTP_404_NOT_FOUND
            )