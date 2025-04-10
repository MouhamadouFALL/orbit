# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, tools, SUPERUSER_ID
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Product",
        change_default=True, ondelete='set null', check_company=True, index='btree_not_null',
        domain="[('sale_ok', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    
    state = fields.Selection(
        related='order_id.state',
        string="Order Status",
        copy=False, store=True, precompute=True)

    # @api.model_create_multi
    # def create(self, vals_list):
        
            
        # if self.product_id.is_preorder == False or self.product_id.is_preorder_allowed == False:
        # if not self.product_id.is_preorder:
        #     raise UserError(_("Ce produit n'est pas disponible en précommande"))
        
        # return super(SaleOrderLine, self).create(vals_list)

    # @api.model_create_multi
    # def create(self, vals_list):
    #     for vals in vals_list:

    #         # product_id = vals.get('product_id')
        
    #         # Récupérer le produit si product_id n'est pas dans vals
    #         # if not product_id:
    #         #     sale_order = self.env['sale.order'].browse(vals.get('order_id'))
    #         #     if sale_order:
    #         #         product = self.env['product.product'].search([('id', '=', sale_order.order_line.product_id.id)])
    #         #     else:
    #         #         raise UserError(_("Impossible de trouver le produit pour la précommande"))
    #         # else:
    #         #     product = self.env['product.product'].browse(vals.get('product_id'))

    #         # Assurez-vous que product existe
    #         # if not product:
    #         #     raise UserError(_("Produit introuvable"))
            
    #         if product.is_preorder and not product.is_preorder_allowed:
    #             raise UserError(_("Ce produit n'est pas disponible en précommande"))
    #     return super(SaleOrderLine, self).create(vals)
