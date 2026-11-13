# apps/ventes_clients/utils/emails.py
# ============================================================
# ENVOI D'EMAILS POUR LES COMMANDES E-COMMERCE
# ============================================================

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone

logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================
def _get_frontend_url():
    """Retourne l'URL frontend normalisée (toujours avec / à la fin)."""
    url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173/')
    return url if url.endswith('/') else url + '/'


def _get_payment_method_display(vente):
    """Retourne le libellé du mode de paiement (safe, pas de crash)."""
    if not vente.payment_method:
        return 'Non spécifié'

    # ⚠️ Le modèle Vente n'a PAS de choices sur payment_method
    # On utilise un mapping manuel
    mapping = {
        'cash': 'Espèces',
        'card': 'Carte bancaire',
        'check': 'Chèque',
        'transfer': 'Virement',
        'mobile_money': 'Mobile Money',
        'credit': 'Crédit',
        'wallet': 'Porte-monnaie électronique',
    }
    return mapping.get(vente.payment_method, vente.payment_method)


def _get_client_email(vente):
    """
    Récupère l'email du destinataire de manière safe.
    Priorité : client_email > user.email
    """
    if vente.client_email:
        return vente.client_email

    if vente.client and vente.client.user and vente.client.user.email:
        return vente.client.user.email

    return None


# ============================================================
# UTILITAIRE GÉNÉRIQUE D'ENVOI
# ============================================================
def _send_email(subject, template_name, context, to_email):
    """
    Envoie un email HTML.
    Retourne True si succès, False sinon.
    """
    if not to_email:
        logger.warning(f"⚠️ Pas d'email destinataire pour : {subject}")
        return False

    try:
        html_message = render_to_string(template_name, context)
        plain_message = strip_tags(html_message)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.EMAIL_HOST_USER,
            to=[to_email],
        )
        msg.attach_alternative(html_message, "text/html")
        msg.send(fail_silently=False)

        logger.info(f"✅ Email envoyé à {to_email} : {subject}")
        return True

    except Exception as e:
        logger.exception(f"❌ Erreur envoi email à {to_email} : {e}")
        return False


# ============================================================
# CONTEXTE COMMUN
# ============================================================
def _build_base_context(vente):
    """Construit le contexte de base partagé par tous les emails."""
    frontend_url = _get_frontend_url()

    return {
        # Objet complet (utile pour debug)
        'order': vente,

        # Identifiants
        'invoice_number': vente.invoice_number,
        'order_number': vente.order_number,

        # Client
        'client_name': vente.client_name or 'Client',
        'client_email': vente.client_email,
        'client_phone': vente.client_phone,
        'client_address': vente.client_address or vente.delivery_address,

        # Dates
        'sale_date': vente.sale_date,
        'delivery_date': vente.delivery_date,

        # Montants
        'total': vente.total,
        'subtotal': vente.subtotal,
        'tax_amount': vente.tax_amount,
        'shipping_fee': vente.shipping_fee,
        'amount_paid': vente.amount_paid,
        'amount_due': vente.amount_due,

        # Paiement
        'payment_method': vente.payment_method,
        'payment_method_display': _get_payment_method_display(vente),
        'payment_status': vente.payment_status,

        # Livraison
        'delivery_method': vente.delivery_method,
        'delivery_address': vente.delivery_address,
        'tracking_number': vente.tracking_number,

        # Notes
        'notes': vente.notes,

        # Lignes
        'lines': list(vente.lines.select_related('product').all()),

        # URLs
        'tracking_url': f"{frontend_url}client/orders/{vente.id}",
        'site_url': frontend_url,

        # Branding
        'site_name': 'ZonACha',
        'year': timezone.now().year,
    }


# ============================================================
# 1. EMAIL : CONFIRMATION DE COMMANDE (à la création)
# ============================================================
def send_order_confirmation_email(vente):
    """
    Envoyé IMMÉDIATEMENT après le checkout.
    Confirme au client que sa commande a été reçue.
    """
    context = _build_base_context(vente)
    context.update({
        'email_type': 'confirmation',
        'title': 'Votre commande a bien été reçue !',
        'subtitle': f"Commande {vente.invoice_number}",
        'intro_text': (
            f"Bonjour {vente.client_name or 'Client'},<br><br>"
            f"Nous avons bien reçu votre commande et nous vous en remercions. "
            f"Notre équipe va maintenant la vérifier et vous contactera pour la suite."
        ),
        'status_badge': 'En attente de confirmation',
        'status_color': '#f59e0b',  # orange
    })

    return _send_email(
        subject=f"✅ Confirmation de commande {vente.invoice_number} - ZonACha",
        template_name="emails/order_confirmation.html",
        context=context,
        to_email=_get_client_email(vente),
    )


# ============================================================
# 2. EMAIL : COMMANDE CONFIRMÉE
# ============================================================
def send_order_confirmed_email(vente):
    """Envoyé quand l'admin confirme la commande."""
    context = _build_base_context(vente)
    context.update({
        'email_type': 'confirmed',
        'title': 'Votre commande est confirmée ! 🎉',
        'subtitle': f"Commande {vente.invoice_number}",
        'intro_text': (
            f"Bonjour {vente.client_name or 'Client'},<br><br>"
            f"Excellente nouvelle ! Votre commande a été confirmée par notre équipe. "
            f"Elle est maintenant en cours de préparation."
        ),
        'status_badge': 'Confirmée',
        'status_color': '#10b981',  # vert
    })

    return _send_email(
        subject=f"🎉 Commande {vente.invoice_number} confirmée - ZonACha",
        template_name="emails/order_confirmation.html",
        context=context,
        to_email=_get_client_email(vente),
    )


# ============================================================
# 3. EMAIL : COMMANDE EN COURS DE LIVRAISON
# ============================================================
def send_order_delivering_email(vente):
    """Envoyé quand la commande part en livraison."""
    context = _build_base_context(vente)
    context.update({
        'email_type': 'delivering',
        'title': 'Votre commande est en route ! 🚚',
        'subtitle': f"Commande {vente.invoice_number}",
        'intro_text': (
            f"Bonjour {vente.client_name or 'Client'},<br><br>"
            f"Votre commande est en cours de livraison. "
            f"Vous devriez la recevoir très bientôt."
        ),
        'status_badge': 'En livraison',
        'status_color': '#3b82f6',  # bleu
    })

    return _send_email(
        subject=f"🚚 Votre commande {vente.invoice_number} est en route - ZonACha",
        template_name="emails/order_confirmation.html",
        context=context,
        to_email=_get_client_email(vente),
    )


# ============================================================
# 4. EMAIL : COMMANDE LIVRÉE
# ============================================================
def send_order_delivered_email(vente):
    """Envoyé quand la commande est livrée."""
    context = _build_base_context(vente)
    context.update({
        'email_type': 'delivered',
        'title': 'Votre commande est livrée ! 📦✨',
        'subtitle': f"Commande {vente.invoice_number}",
        'intro_text': (
            f"Bonjour {vente.client_name or 'Client'},<br><br>"
            f"Votre commande a été livrée avec succès. "
            f"Merci pour votre confiance et à bientôt sur ZonACha !"
        ),
        'status_badge': 'Livrée',
        'status_color': '#059669',  # vert foncé
    })

    return _send_email(
        subject=f"📦 Commande {vente.invoice_number} livrée - ZonACha",
        template_name="emails/order_confirmation.html",
        context=context,
        to_email=_get_client_email(vente),
    )


# ============================================================
# 5. EMAIL : COMMANDE ANNULÉE
# ============================================================
def send_order_cancelled_email(vente, reason=None):
    """Envoyé quand la commande est annulée."""
    context = _build_base_context(vente)
    context.update({
        'email_type': 'cancelled',
        'title': 'Votre commande a été annulée',
        'subtitle': f"Commande {vente.invoice_number}",
        'intro_text': (
            f"Bonjour {vente.client_name or 'Client'},<br><br>"
            f"Nous vous informons que votre commande a été annulée."
            + (f"<br><br><strong>Raison :</strong> {reason}" if reason else "")
            + "<br><br>Si vous n'êtes pas à l'origine de cette annulation, "
            f"contactez-nous rapidement."
        ),
        'status_badge': 'Annulée',
        'status_color': '#ef4444',  # rouge
        'cancellation_reason': reason,
    })

    return _send_email(
        subject=f"❌ Commande {vente.invoice_number} annulée - ZonACha",
        template_name="emails/order_confirmation.html",
        context=context,
        to_email=_get_client_email(vente),
    )