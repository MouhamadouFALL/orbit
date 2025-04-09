#-*- coding: utf-8 -*-
from odoo import models, fields, api, _


class StockWarehoure(models.Model):
    _inherit = "stock.warehouse"
    
    is_restricted = fields.Boolean(string="Is Restricted", default=False)