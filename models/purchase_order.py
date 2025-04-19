#-*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    attachment_ids = fields.Many2many('ir.attachment', 'orbit_attachment_rel', 'orbit_id', 'attachment_id', string="Pieces jointes", store=True, help="Attach files related to this order")

    usr_confirmed = fields.Many2one('res.users', string="Confirmé par", readonly=True)
    
    payment_count = fields.Integer(
        string='Nombre de paiements',
        compute='_compute_payments',
        store=True)
    payment_total = fields.Monetary(
        string='Total versé',
        compute='_compute_payments',
        store=True,
        currency_field='currency_id')
    
    def _get_valid_payments(self):
        """Retourne les paiements fournisseurs postés réconciliés avec ce bon d'achat."""
        self.ensure_one()
        # On cherche soit sur les factures liées, soit sur la référence du PO
        # invoice_refs = self.invoice_ids.mapped('name')
        # domain = [
        #     ('state', '=', 'posted'),
        #     ('is_internal_transfer', '=', False),
        #     '|',
        #     ('invoice_ids', 'in', self.invoice_ids.ids),
        #     ('ref', 'in', invoice_refs + [self.name]),
        # ]
        # return self.env['account.payment'].search(domain, order='date desc')
        
        # On ne traite que les factures fournisseur publiées
        for inv in self.invoice_ids.filtered(lambda i: i.state == 'posted' and i.is_invoice()):
            # Pour chaque ligne de la facture, on parcourt les réconciliations
            for line in inv.line_ids:
                recs = line.matched_debit_ids | line.matched_credit_ids
                for rec in recs:
                    # Chaque reconciliation référence deux lignes : debit_move_id et credit_move_id
                    for move_line in (rec.debit_move_id, rec.credit_move_id):
                        if move_line.payment_id:
                            payments |= move_line.payment_id

        # Ne garder que les paiements effectivement postés et non‐internes
        return payments.filtered(lambda p: p.state == 'posted' and not p.is_internal_transfer)
    
    @api.depends('invoice_ids.state', 'invoice_ids.line_ids.matched_debit_ids.credit_move_id.payment_id.state')
    def _compute_payments(self):
        for order in self:
            payments = self._get_valid_payments()
            # On ne prend que les factures publiées ou payées
            # invoices = order.invoice_ids.filtered(lambda inv: inv.state in ('posted', 'paid'))
            # for inv in invoices:
            #     # Récupère les paiements via la réconciliation des lignes de mouvement
            #     pm = inv.line_ids \
            #             .mapped('matched_debit_ids') \
            #             .mapped('credit_move_id') \
            #             .mapped('payment_id')
            #     payments |= pm
            order.payment_count = len(payments)
            order.payment_total = sum(payments.mapped('amount'))
            
    def action_view_payments(self):
        self.ensure_one()
        # Recherche des paiements déjà identifiés
        # payments = self.env['account.payment'].search([
        #     ('id', 'in', self.invoice_ids
        #                     .mapped('line_ids')
        #                     .mapped('matched_debit_ids')
        #                     .mapped('credit_move_id')
        #                     .mapped('payment_id')
        #                     .ids)
        # ])
        # return {
        #     'name': 'Paiements fournisseur',
        #     'view_mode': 'tree,form',
        #     'res_model': 'account.payment',
        #     'domain': [('id', 'in', payments.ids)],
        #     'type': 'ir.actions.act_window',
        # }
        
        payments = self._get_valid_payments()
        if not payments:
            raise UserError(_("Aucun paiement trouvé pour ce bon d'achat"))

        action = self.env.ref('account.action_account_payments').read()[0]
        action.update({
            'domain': [('id', 'in', payments.ids)],
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_ref': self.name,
                'default_date': fields.Date.context_today(self),
                'search_default_group_by_payment_type': True,
            },
            'views': [(False, 'tree'), (False, 'form')],
        })
        return action

    def write(self, vals):
        # Autoriser les opérations système et pièces jointes
        system_context = self.env.context.get('tracking_disable') or self._context.get('bypass_purchase_lock')
        if system_context or self.env.user.has_group('base.ccbmshop_purchase_group_manager'):
            return super().write(vals)
        
        # Autoriser spécifiquement l'annulation
        if vals.get('state') in ['draft', 'to approve', 'sent', 'cancel']:
            return super().write(vals)
        
        # Vérifier si la restriction doit être appliquée
        if not self.env.context.get('bypass_purchase_lock'):
            for order in self.filtered(lambda o: o.state in ['purchase', 'done']):
                # Whitelist étendue avec champs techniques nécessaires
                allowed_fields = self._get_whitelisted_fields()
                if not set(vals.keys()).issubset(allowed_fields):
                    _logger.warning(f"Tentative de modification non autorisée par {self.env.user.name} sur {order.name}")
                    raise UserError(_("Modification non autorisée sur le bon de commande %s confirmé ! (État: %s).") % (order.name, order.state))
        
        return super().write(vals)
            
    def _get_whitelisted_fields(self):
        """Retourne la liste des champs modifiables après confirmation."""
        return {
            
            'notes',    # Notes internes
            'state',    # État de la commande
            'priority',  # Priorité de la commande
            'attachment_ids',  # Pièces jointes
            
            'message_main_attachment_id',  # Champ critique pour les pièces jointes
            'activity_ids',                # Gestion des activités
            'message_ids'                 # Historique de messages
            'write_uid',
            'write_date',
        }
    
    def button_confirm(self):
        """Confirme le bon de commande et enregistre l'utilisateur qui confirme."""
        # Validation personnalisée avant confirmation
        self._check_confirm_validation()
        
        self = self.with_context(bypass_purchase_lock=True)
        res = super().button_confirm()
        
        # Mise à jour en masse pour optimiser les performances
        self.write({
            'usr_confirmed': self.env.user.id,
            'date_approve': fields.Datetime.now()  # Optionnel : date de confirmation
        })
        
        _logger.info(f" [{fields.Datetime.now()}] +++ Bon de commande {self.name} confirmé par {self.env.user.name}")
        
        return res
    
    # Validation optionelle avant confirmation (à personnaliser)
    def _check_confirm_validation(self):
        """Add custom validation rules before confirmation"""
        
        # Vérification du groupe utilisateur
        if not self.env.user.has_group('orbit.ccbmshop_purchase_group_manager'):
            raise UserError(_("Permission refusée - user: %s - Contactez un manager pour confirmer.")%(self.env.user.name))
        
