# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models, api, _, tools, SUPERUSER_ID

import logging

_logger = logging.getLogger(__name__)


STATE = [
    ('draft', "Quotation"),
    ('sent', "Sent"),
    ('validation', "Validation"),
    ('sale', "Commande/Precommande"),
    ('to_delivered', "à livré"),
    ('delivered', "Livré"),
    ('done', "Locked"),
    ('cancel', "Cancelled"),
]

ORDER_STATE = [
    ('draft', "Quotation"),
    ('sent', "Sent"),
    ('validation', "Validation"),
    ('sale', "Commande"),
    ('to_delivered', "à livré"),
    ('delivered', "Livré"),
    ('done', "Locked"),
    ('cancel', "Cancelled"),
]

PREORDER_STATE = [
    ('draft', "Quotation"),
    ('sent', "Sent"),
    ('validation', "Validation"),
    ('sale', "Pre-commande"),
    ('to_delivered', "à livré"),
    ('delivered', "Livré"),
    ('done', "Locked"),
    ('cancel', "Cancelled"),
]

CREDITORDER_STATE = [
    ('draft', "Quotation"),
    ('sent', "Sent"),
    ('validation', "Validation"),
    ('sale', "Commande-credit"),
    ('to_delivered', "à livré"),
    ('delivered', "Livré"),
    ('done', "Locked"),
    ('cancel', "Cancelled"),
]

TYPE_SALE = [
    ('order', "Commande"),
    ('preorder', "Precommande"),
    ('creditorder', "Commande credit"),
]

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_steps(self):
        ctx = dict(self.env.context)
        selection = []
        if 'default_type_sale' in ctx:
            if ctx.get('default_type_sale') == 'order':
                selection = ORDER_STATE
            if ctx.get('default_type_sale') == 'preorder':
                selection = PREORDER_STATE
            if ctx.get('default_type_sale') == 'creditorder':
                selection = CREDITORDER_STATE
        else:
            selection = STATE

        return selection

    # type de vente (type de business)
    type_sale = fields.Selection(
        selection=TYPE_SALE,
        string="Type Sale", required=True, readonly=True, copy=False, index=True,
        default = lambda self: self.env.context.get('default_type_sale', 'order'), 
        store=True
    )

    state = fields.Selection(
        selection=_get_steps,
        string="Status", readonly=True,
        copy=False, index=True,
        tracking=3, default='draft')

    usr_confirmed = fields.Many2one('res.users', string="Confirmé par", readonly=True)
    
    def get_type_sale_label(self):
        return dict(self._fields['type_sale'].selection).get(self.type_sale)
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'type_sale' not in vals and 'default_type_sale' in self.env.context:
                vals['type_sale'] = self.env.context['default_type_sale']

        return super(SaleOrder, self).create(vals_list)

    @api.depends("amount_residual")
    def action_delivered(self):
        for order in self:
            if order.amount_residual <= 0:
                order.write({
                    'state': 'to_delivered'
                })

                