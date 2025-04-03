#-*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions
from odoo.exceptions import ValidationError, UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    attachment_ids = fields.Many2many('ir.attachment', 'orbit_attachment_rel', 'orbit_id', 'attachment_id', string="Pieces jointes", store=True, help="Attach files related to this order")

    usr_confirmed = fields.Many2one('res.users', string="Confirmé par", readonly=True)

    def write(self, vals):
        # Autoriser spécifiquement l'annulation
        if vals.get('state') == 'cancel':
            return super().write(vals)
        
        if not self.env.context.get('bypass_purchase_lock'):
            for order in self.filtered(lambda o: o.state in ['purchase', 'done']):
                if order.state in ['purchase', 'done']:
                    # if not self.env.user.has_group('purchase.group_purchase_manager'):
                    protected_fields = set(vals.keys()) - self._get_whitelisted_fields()
                    if protected_fields:
                        raise ValidationError(_("Opération bloquée ! La commande %s est confirmée (État: %s).") % (order.name, order.state))
        
        return super().write(vals)

    def _get_whitelisted_fields(self):
        """Champs modifiables après confirmation"""
        return {
            'notes',        # Notes internes
            # 'date_planned',  # Dates logistiques
            # 'incoterm_id',
            # 'priority'      # Priorité logistique
        }

    def button_confirm(self):
        """Overrides the confirm button method to record the user who confirmed."""
        res = super(PurchaseOrder, self).button_confirm()
        for order in self:
            # Enregistre l'utilisateur connecté
            order.usr_confirmed = self.env.user  
        return res