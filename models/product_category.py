from odoo import models, fields, api
import logging
# from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class ProductCategory(models.Model):
    _inherit = 'product.category'
    
    sequence = fields.Integer('Sequence', default=1, help="Used to order categories. Lower is better.")
    
    # _sql_constraints = [
    #     ('unique_sequence', 'unique(sequence)', 'Each category must have a unique sequence!')
    # ]

    # @api.constrains('sequence')
    # def _check_unique_sequence(self):
    #     for record in self:
    #         if self.search_count([('sequence', '=', record.sequence)]) > 1:
    #             raise ValidationError("Each category must have a unique sequence number.")
    
    # name
    # complete_name
    # parent_id
    # parent_path
    # child_id
    # product_count

