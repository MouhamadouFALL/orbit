from odoo import models, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_confirm(self):
        # Vérifiez chaque ligne de mouvement avant la confirmation de la livraison
        for picking in self:
            if picking.picking_type_id.code != 'outgoing':
                continue  # Ignorer les types de mouvement non sortants
            
            for move in picking.move_ids_without_package:
                product = move.product_id
                location = picking.location_id
                available_qty = product.with_context(location=location.id).qty_available

                if available_qty <= 0:
                    raise UserError(_(
                        "Impossible de livrer le produit '%s'.\n"
                        "Quantité disponible : %s (≤ 0).\n"
                        "Vérifiez les stocks avant de confirmer la livraison."
                    ) % (product.name, available_qty))
        
        return super(StockPicking, self).action_confirm()
    