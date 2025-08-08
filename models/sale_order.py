# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models, api, _, tools, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

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

    active = fields.Boolean("Active", default=True)
    
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
    
    partial_delivery_done = fields.Boolean(
        string="Livraison partielle effectuée",
        compute='_compute_partial_delivery',
        store=True
    )
    
    # payment_details_ids = fields.One2many('payment.details', 'sale_order_id', string="Payment Details")
    
    
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

    def action_invoice_create(self):
        for order in self:
            if not order.partial_delivery_done:
                raise UserError(_("Impossible de facturer avant livraison complète/partielle des produits !"))
        return super().action_invoice_create()
    

    @api.depends('order_line.qty_delivered')
    def _compute_partial_delivery(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for order in self:
            order.partial_delivery_done = any(
                float_compare(line.qty_delivered, 0.0, precision_digits=precision) > 0
                for line in order.order_line
                if line.product_id.type in ['consu', 'product']
            )
            
                