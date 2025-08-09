# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    # ==================== CHAMPS ====================

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'orbit_purchase_attachment_rel',  # Table de relation renommée pour éviter les conflits
        'purchase_id',
        'attachment_id',
        string="Pièces jointes",
        help="Fichiers joints à ce bon de commande"
    )

    usr_confirmed = fields.Many2one(
        'res.users',
        string="Confirmé par",
        readonly=True,
        tracking=True,
        help="Utilisateur qui a confirmé le bon de commande"
    )

    payment_count = fields.Integer(
        string='Nombre de paiements',
        compute='_compute_payments',
        store=True,
        help="Nombre de paiements liés à ce bon de commande"
    )

    payment_total = fields.Monetary(
        string='Total versé',
        compute='_compute_payments',
        store=True,
        currency_field='currency_id',
        help="Montant total des paiements effectués"
    )

    # État de validation personnalisé
    state = fields.Selection([
        ('draft', 'Demande de Prix'),
        ('sent', 'DDP Envoyée'),
        ('to_validate', 'En Validation'),
        ('to_approve', 'À Approuver'),
        ('purchase', 'Bon de Commande'),
        ('done', 'Verrouillé'),
        ('cancel', 'Annulé')
    ], string='Statut', readonly=True, index=True, copy=False,
        default='draft', tracking=True)

    # ==================== MÉTHODES DE VALIDATION ====================

    def action_to_validation(self):
        """Envoie une demande de validation pour le bon de commande."""
        self.ensure_one()

        if self.state != 'draft':
            raise UserError(_("Seuls les bons de commande en brouillon peuvent être envoyés en validation."))

        # Vérifications préalables
        self._check_validation_requirements()

        self.write({'state': 'to_validate'})

        # Récupération du template d'email
        template = self.env.ref(
            'orbit.email_template_purchase_order_validation',
            raise_if_not_found=False
        )

        if not template:
            _logger.warning("Template d'email de validation introuvable")
            return

        # Récupération des emails des managers
        email_values = self._get_manager_emails()

        if email_values.get('email_to'):
            try:
                template.send_mail(
                    self.id,
                    force_send=True,
                    raise_exception=False,
                    email_values=email_values
                )
                _logger.info(f"Demande de validation envoyée pour {self.name}")

                # Message de suivi interne
                self.message_post(
                    body=_("Demande de validation envoyée aux managers d'achat."),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
            except Exception as e:
                _logger.error(f"Erreur envoi email validation {self.name}: {e}")
                raise UserError(_("Erreur lors de l'envoi de la demande de validation."))
        else:
            raise UserError(_("Aucun manager d'achat configuré pour recevoir les validations."))

    def _check_validation_requirements(self):
        """Vérifie les prérequis pour la validation."""
        if not self.order_line:
            raise UserError(_("Impossible de valider un bon de commande sans lignes."))

        if not self.partner_id:
            raise UserError(_("Veuillez sélectionner un fournisseur."))

        # Vérification des montants
        if any(line.price_unit <= 0 for line in self.order_line):
            raise UserError(_("Toutes les lignes doivent avoir un prix unitaire positif."))

    @api.model
    def send_validation_reminders(self):
        """Envoie des rappels de validation via cron job."""
        template = self.env.ref(
            'orbit.email_template_purchase_order_validation',
            raise_if_not_found=False
        )

        if not template:
            _logger.warning("Template de rappel introuvable")
            return

        # Recherche des bons de commande en attente de validation
        purchase_orders = self.search([('state', '=', 'to_validate')])

        if not purchase_orders:
            return

        email_values = self._get_manager_emails()

        for order in purchase_orders:
            try:
                template.send_mail(
                    order.id,
                    force_send=False,
                    raise_exception=False,
                    email_values=email_values
                )
                _logger.info(f"Rappel de validation envoyé pour {order.name}")
            except Exception as e:
                _logger.error(f"Erreur rappel validation {order.name}: {e}")

    def _get_manager_emails(self):
        """Récupère les emails des managers d'achat."""
        try:
            group = self.env.ref('orbit.ccbmshop_purchase_group_manager')

            # Recherche optimisée des utilisateurs actifs avec email
            managers = self.env['res.users'].search([
                ('groups_id', 'in', [group.id]),
                ('email', '!=', False),
                ('active', '=', True)
            ])

            emails = [user.email for user in managers if user.email]

            if not emails:
                _logger.warning("Aucun manager d'achat avec email configuré")
                return {}

            return {
                'email_to': ','.join(set(emails)),  # Suppression des doublons
                'email_from': self.env.company.email or 'shop@ccbm.sn',
            }

        except Exception as e:
            _logger.error(f"Erreur récupération emails managers: {e}")
            return {}

    # ==================== GESTION DES PAIEMENTS ====================

    def _get_valid_payments(self):
        """Retourne les paiements valides liés à ce bon d'achat."""
        self.ensure_one()

        if not self.invoice_ids:
            return self.env['account.payment']

        payments = self.env['account.payment']

        # Recherche dans les factures validées
        posted_invoices = self.invoice_ids.filtered(
            lambda inv: inv.state == 'posted' and inv.move_type == 'in_invoice'
        )

        for invoice in posted_invoices:
            # Recherche des paiements via les lignes réconciliées
            receivable_lines = invoice.line_ids.filtered(
                lambda line: line.account_id.account_type in ('asset_receivable', 'liability_payable')
            )

            for line in receivable_lines:
                # Paiements via matched_debit_ids et matched_credit_ids
                for matched in (line.matched_debit_ids | line.matched_credit_ids):
                    move_lines = [matched.debit_move_id, matched.credit_move_id]
                    for move_line in move_lines:
                        if (move_line.payment_id and
                                move_line.payment_id.state == 'posted' and
                                not move_line.payment_id.is_internal_transfer):
                            payments |= move_line.payment_id

        return payments.sudo()  # Accès en mode sudo pour éviter les restrictions

    @api.depends('invoice_ids.state', 'invoice_ids.payment_state')
    def _compute_payments(self):
        """Calcul des statistiques de paiement."""
        for order in self:
            try:
                payments = order._get_valid_payments()
                order.payment_count = len(payments)
                order.payment_total = sum(payments.mapped('amount')) if payments else 0.0
            except Exception as e:
                _logger.warning(f"Erreur calcul paiements {order.name}: {e}")
                order.payment_count = 0
                order.payment_total = 0.0

    def action_view_payments(self):
        """Ouvre la vue des paiements liés."""
        self.ensure_one()

        payments = self._get_valid_payments()

        if not payments:
            raise UserError(_("Aucun paiement trouvé pour ce bon d'achat."))

        action = self.env.ref('account.action_account_payments_payable').read()[0]

        if len(payments) == 1:
            action.update({
                'views': [(False, 'form')],
                'res_id': payments.id,
                'domain': [],
                'context': {},
            })
        else:
            action.update({
                'domain': [('id', 'in', payments.ids)],
                'context': {
                    'default_partner_id': self.partner_id.id,
                    'default_ref': self.name,
                },
            })

        return action

    # ==================== GESTION DES MODIFICATIONS ====================

    def write(self, vals):
        """Contrôle des modifications sur les bons de commande confirmés."""

        # Contextes d'autorisation système
        system_contexts = [
            'tracking_disable',
            'bypass_purchase_lock',
            'mail_activity_automation_skip',
            'mail_notrack'
        ]

        if any(self.env.context.get(ctx) for ctx in system_contexts):
            return super().write(vals)

        # Autorisation pour les managers
        if self.env.user.has_group('orbit.ccbmshop_purchase_group_manager'):
            return super().write(vals)

        # États où les modifications sont toujours autorisées
        if vals.get('state') in ['draft', 'sent', 'to_validate', 'to_approve', 'cancel']:
            return super().write(vals)

        # Contrôle des modifications sur les bons confirmés
        locked_orders = self.filtered(lambda o: o.state in ['purchase', 'done'])

        if locked_orders and vals:
            allowed_fields = self._get_whitelisted_fields()
            restricted_fields = set(vals.keys()) - allowed_fields

            if restricted_fields:
                order_names = ', '.join(locked_orders.mapped('name'))
                _logger.warning(
                    f"Tentative de modification non autorisée par {self.env.user.name} "
                    f"sur {order_names}. Champs: {restricted_fields}"
                )
                raise UserError(_(
                    "Modification non autorisée sur le(s) bon(s) de commande confirmé(s): %s.\n"
                    "Champs non modifiables: %s"
                ) % (order_names, ', '.join(restricted_fields)))

        return super().write(vals)

    def _get_whitelisted_fields(self):
        """Champs modifiables après confirmation."""
        return {
            # Champs utilisateur
            'notes', 'priority', 'attachment_ids',

            # Champs système (critiques pour le bon fonctionnement)
            'state', 'message_main_attachment_id', 'activity_ids',
            'message_ids', 'write_uid', 'write_date', 'payment_count',
            'payment_total', 'message_partner_ids', '__last_update',

            # Champs de tracking et d'audit
            'usr_confirmed', 'date_approve', 'message_follower_ids'
        }

    # ==================== CONFIRMATION ET APPROBATION ====================

    def button_confirm(self):
        """Confirmation du bon de commande avec contrôles personnalisés."""

        # Vérification des permissions
        if not self.env.user.has_group('orbit.ccbmshop_purchase_group_manager'):
            raise UserError(_(
                "%s - Vous n'avez pas les droits nécessaires pour confirmer un bon de commande. "
                "Contactez un manager pour confirmer."
            ) % self.env.user.name)

        # Validation des données avant confirmation
        for order in self:
            order._check_confirm_validation()

        # Confirmation avec contexte d'autorisation
        self = self.with_context(bypass_purchase_lock=True)
        result = super().button_confirm()

        # Post-traitement après confirmation
        for order in self:
            if order.state in ['draft', 'sent', 'to_validate']:
                continue

            try:
                # Validation de la distribution analytique
                order.order_line._validate_analytic_distribution()

                # Ajout du fournisseur aux produits si nécessaire
                order._add_supplier_to_product()

                # Gestion de la double validation
                if order._approval_allowed():
                    order.button_approve()
                    order.write({'usr_confirmed': self.env.user.id})
                    _logger.info(
                        f"[{fields.Datetime.now()}] Bon de commande {order.name} "
                        f"confirmé par {self.env.user.name}"
                    )
                else:
                    order.write({'state': 'to_approve'})

                # Abonnement automatique du fournisseur aux notifications
                if order.partner_id not in order.message_partner_ids:
                    order.message_subscribe([order.partner_id.id])

            except Exception as e:
                _logger.error(f"Erreur post-confirmation {order.name}: {e}")
                # Ne pas bloquer la confirmation, juste logger l'erreur

        return result

    def _check_confirm_validation(self):
        """Validations personnalisées avant confirmation."""
        self.ensure_one()

        # Vérification des lignes de commande
        if not self.order_line:
            raise UserError(_("Impossible de confirmer un bon de commande sans lignes."))

        # Vérification du fournisseur
        if not self.partner_id:
            raise UserError(_("Veuillez sélectionner un fournisseur avant de confirmer."))

        # Vérification des prix
        zero_price_lines = self.order_line.filtered(lambda l: l.price_unit <= 0)
        if zero_price_lines:
            products = ', '.join(zero_price_lines.mapped('product_id.name'))
            raise UserError(_(
                "Les produits suivants ont un prix nul ou négatif: %s"
            ) % products)

        # Vérification des quantités
        zero_qty_lines = self.order_line.filtered(lambda l: l.product_qty <= 0)
        if zero_qty_lines:
            products = ', '.join(zero_qty_lines.mapped('product_id.name'))
            raise UserError(_(
                "Les produits suivants ont une quantité nulle ou négative: %s"
            ) % products)

    # ==================== MÉTHODES UTILITAIRES ====================

    @api.model
    def _cron_cleanup_validation_requests(self):
        """Nettoyage automatique des demandes de validation anciennes."""
        cutoff_date = fields.Datetime.now() - timedelta(days=30)
        old_requests = self.search([
            ('state', '=', 'to_validate'),
            ('write_date', '<', cutoff_date)
        ])

        if old_requests:
            _logger.info(f"Nettoyage de {len(old_requests)} anciennes demandes de validation")
            old_requests.write({'state': 'draft'})

    def action_reset_to_draft(self):
        """Remet le bon de commande en brouillon (managers uniquement)."""
        if not self.env.user.has_group('orbit.ccbmshop_purchase_group_manager'):
            raise UserError(_("Seuls les managers peuvent remettre en brouillon."))

        for order in self:
            if order.state == 'purchase':
                raise UserError(_(
                    "Impossible de remettre en brouillon un bon de commande confirmé: %s"
                ) % order.name)

        self.write({'state': 'draft', 'usr_confirmed': False})
        return True