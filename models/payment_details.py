from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'payment.details'

    order_id = fields.Integer(
        string='Order ID',
        required=False,
        help='Order ID for the payment details',
        index=True,
    )