#-*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions
from odoo.exceptions import ValidationError, UserError


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
        # Autoriser spécifiquement l'annulation
        if vals.get('state') in ['draft', 'to approve', 'sent', 'cancel']:
            return super().write(vals)
        
        # Vérifier si la restriction doit être appliquée
        if not self.env.context.get('bypass_purchase_lock'):
            for order in self.filtered(lambda o: o.state in ['purchase', 'done']):
                protected_fields = set(vals.keys()) - self._get_whitelisted_fields()
                if protected_fields:
                    raise ValidationError(
                        _("Opération bloquée ! La commande %s est confirmée (État: %s).") 
                        % (order.name, order.state)
                    )
        return super().write(vals)

    def _get_whitelisted_fields(self):
        """Retourne la liste des champs modifiables après confirmation."""
        return {
            'notes',    # Notes internes
            'state',    # État de la commande
        }

    def button_confirm(self):
        """Confirme le bon de commande et enregistre l'utilisateur qui confirme."""
        res = super().button_confirm()
        # Bypass la restriction lors de la confirmation grâce au contexte
        self.with_context(bypass_purchase_lock=True).write({
            'usr_confirmed': self.env.user.id,
        })
        
        return res