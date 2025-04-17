#-*- coding: utf-8 -*-
from odoo import models, fields, api, _


class StockMove(models.Model):
    _inherit = 'stock.move'
    
    product_id = fields.Many2one(
        'product.product', 'Product',
        check_company=True,
        domain="[('type', 'in', ['product', 'service']), '|', ('company_id', '=', False), ('company_id', '=', company_id)]", index=True, required=False,
        states={'done': [('readonly', True)]})