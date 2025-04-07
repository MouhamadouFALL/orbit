#-*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    attachment_ids = fields.Many2many('ir.attachment', 'orbit_attachment_rel', 'orbit_id', 'attachment_id', string="Pieces jointes", store=True, help="Attach files related to this order")

    usr_confirmed = fields.Many2one('res.users', string="Confirmé par", readonly=True)
    
    is_locked = fields.Boolean(string="Verrouillé", default=False, store=False, help="Indique si le bon d'achat est verrouillé en lecture seule.")
    
    @api.depends('state')
    def _compute_is_locked(self):
        for order in self:
            if order.state in ['purchase', 'done']:
                order.is_locked = True
            else:
                order.is_locked = False

    def write(self, vals):
        # Autoriser les opérations système et pièces jointes
        system_context = self.env.context.get('tracking_disable') or self._context.get('bypass_purchase_lock')
        if system_context or self.env.user.has_group('base.group_system'):
            return super().write(vals)
        
        # Autoriser spécifiquement l'annulation
        if self.state in ['draft', 'to approve', 'sent', 'cancel']:
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
            
        # # Vérifier si la restriction doit être appliquée
        # if not self.env.context.get('bypass_purchase_lock'):
        #     for order in self.filtered(lambda o: o.state in ['purchase', 'done']):
        #         protected_fields = set(vals.keys()) - self._get_whitelisted_fields()
        #         if protected_fields:
        #             raise UserError(_("Vous ne pouvez plus modifier un bon d'achat confirmé"))


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
        
        try:
            return super(PurchaseOrder, self.with_context(
                bypass_purchase_lock=True,
                tracking_disable=True
            )).button_confirm()
        finally:
            self.write({'usr_confirmed': self.env.user.id})
            
        # self = self.with_context(bypass_purchase_lock=True)
        # res = super().button_confirm()
        
        # Validation personnalisée avant confirmation
        # self._check_confirm_validation()
        
        # Mise à jour en masse pour optimiser les performances
        # self.write({
        #     'confirmed_by_user_id': self.env.user.id,
        #     'date_approve': fields.Datetime.now()  # Optionnel : date de confirmation
        # })
        
        # return res