from odoo import models, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        # Vérifier les stocks avant validation de la livraison
        for picking in self:
            if picking.picking_type_id.code != 'outgoing':
                continue  # Ignorer les mouvements non sortants
            
            for move in picking.move_ids_without_package:
                product = move.product_id
                location = picking.location_id
                available_qty = product.with_context(location=location.id).qty_available

                if available_qty <= 0:
                    raise UserError(_(
                        "La quantité disponible du produit '%s' est insuffisante (%s).\n"
                        "La livraison ne peut pas être validée."
                    ) % (product.name, available_qty))
        
        return super(StockPicking, self).button_validate()
    
    # def action_confirm(self):
    #     # Vérifiez chaque ligne de mouvement avant la confirmation de la livraison
    #     for picking in self:
    #         if picking.picking_type_id.code != 'outgoing':
    #             continue  # Ignorer les types de mouvement non sortants
            
    #         for move in picking.move_ids_without_package:
    #             product = move.product_id
    #             location = picking.location_id
    #             available_qty = product.with_context(location=location.id).qty_available

    #             if available_qty <= 0:
    #                 raise UserError(_(
    #                     "Impossible de confirmer ou livrer le produit '%s' car il n'a pas de stock .\n"
    #                     "Quantité disponible : %s.\n"
    #                     "Vérifiez les stocks avant de confirmer la commande ou la livraison. \n"
    #                     "Vous pouvez également contacter le gestionnaire de stock pour plus d'informations."
    #                 ) % (product.name, available_qty))
        
    #     return super(StockPicking, self).action_confirm()
    