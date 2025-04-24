#-*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round, float_compare, formatLang, format_date, pycompat


class StockMove(models.Model):
    _inherit = 'stock.move'
    
    product_id = fields.Many2one(
        'product.product', 'Product',
        check_company=True,
        domain="[('type', 'in', ['product', 'service']), '|', ('company_id', '=', False), ('company_id', '=', company_id)]", index=True, required=False,
        states={'done': [('readonly', True)]})
    
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('picking_id') and vals.get('picking_id')[1] and -\
                self.env['stock.picking'].browse(vals['picking_id'][1]).picking_type_code == 'incoming':
                raise UserError("Ajout de lignes interdit sur les bons de réception.")
        return super().create(vals_list)