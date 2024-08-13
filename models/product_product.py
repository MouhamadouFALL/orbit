from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_preorder = fields.Boolean(string="Available for preorder", default=True) # produit disponible pour une précommande
    preorder_deadline = fields.Date(string="preorder expery date") # date à laquelle un produit ne sera plus disponible pour une précommande
    preorder_quantity = fields.Integer(string="Quantité de précommande", default=0) # quantité autorisé à précommandé pour un produit
    preorder_payment_option = fields.Selection([
        ('full', 'Paiement complet'),
        ('partial', 'Paiement partiel')
    ], string="Option de paiement de précommande", default='full') # option de paiment accepté pour valider une précommande

    # la précommande sera activée uniquement lorsque la quantité disponible du produit est inférieure à un seuil défini
    preorder_threshold = fields.Integer(string="Preorder threshold", default=5)

    # champs pour la promotion
    en_promo = fields.Boolean(string="En promo", default=False, store=True)

    # 
    ttc_price = fields.Float(
        'TTC Price',
        default=1.0,
        digits='ttc Price', compute='_compute_ttc_price' , store=True
    )
    
    preorder_price = fields.Float(
        'Preorder Price', digits='preorder Price', help="Price for preorders. This price will be applied when a product is preordered."
    )

    # promo_price = fields.Float(
    #     'Promo Price',
    #     digits='Promo Price',
    #     help="Price for promotions. This price will be applied when a product is in promotion",
    #     compute='_compute_promo_price' ,
    #     store=True
    # )

    #
    # @api.depends('list_price', 'tax_id')
    # def _compute_promo_price(self):
    #     for rec in self:
    #         rec.promo_price = rec.list_price * (1 + rec.tax_id.amount /
    #                                             100)

    @api.depends('list_price')
    def _compute_ttc_price(self):
        for record in self:
            record.ttc_price = record.list_price * 1.18
    


class Product(models.Model):
    _inherit = 'product.product'

    
    # qty_available, virtual_available, free_qty, incoming_qty, outgoing_qty
    qty_available = fields.Float(
        'Quantity On Hand', compute='_compute_quantities', search='_search_qty_available',
        digits='Product Unit of Measure', compute_sudo=False, store=True,
        help="Current quantity of products.\n"
             "In a context with a single Stock Location, this includes "
             "goods stored at this Location, or any of its children.\n"
             "In a context with a single Warehouse, this includes "
             "goods stored in the Stock Location of this Warehouse, or any "
             "of its children.\n"
             "stored in the Stock Location of the Warehouse of this Shop, "
             "or any of its children.\n"
             "Otherwise, this includes goods stored in any Stock Location "
             "with 'internal' type.")
    virtual_available = fields.Float(
        'Forecasted Quantity', compute='_compute_quantities', search='_search_virtual_available',
        digits='Product Unit of Measure', compute_sudo=False, store=True,
        help="Forecast quantity (computed as Quantity On Hand "
             "- Outgoing + Incoming)\n"
             "In a context with a single Stock Location, this includes "
             "goods stored in this location, or any of its children.\n"
             "In a context with a single Warehouse, this includes "
             "goods stored in the Stock Location of this Warehouse, or any "
             "of its children.\n"
             "Otherwise, this includes goods stored in any Stock Location "
             "with 'internal' type.")
    free_qty = fields.Float(
        'Free To Use Quantity ', compute='_compute_quantities', search='_search_free_qty',
        digits='Product Unit of Measure', compute_sudo=False, store=True,
        help="Forecast quantity (computed as Quantity On Hand "
             "- reserved quantity)\n"
             "In a context with a single Stock Location, this includes "
             "goods stored in this location, or any of its children.\n"
             "In a context with a single Warehouse, this includes "
             "goods stored in the Stock Location of this Warehouse, or any "
             "of its children.\n"
             "Otherwise, this includes goods stored in any Stock Location "
             "with 'internal' type.")
    incoming_qty = fields.Float(
        'Incoming', compute='_compute_quantities', search='_search_incoming_qty',
        digits='Product Unit of Measure', compute_sudo=False, store=True,
        help="Quantity of planned incoming products.\n"
             "In a context with a single Stock Location, this includes "
             "goods arriving to this Location, or any of its children.\n"
             "In a context with a single Warehouse, this includes "
             "goods arriving to the Stock Location of this Warehouse, or "
             "any of its children.\n"
             "Otherwise, this includes goods arriving to any Stock "
             "Location with 'internal' type.")
    outgoing_qty = fields.Float(
        'Outgoing', compute='_compute_quantities', search='_search_outgoing_qty',
        digits='Product Unit of Measure', compute_sudo=False, store=True,
        help="Quantity of planned outgoing products.\n"
             "In a context with a single Stock Location, this includes "
             "goods leaving this Location, or any of its children.\n"
             "In a context with a single Warehouse, this includes "
             "goods leaving the Stock Location of this Warehouse, or "
             "any of its children.\n"
             "Otherwise, this includes goods leaving any Stock "
             "Location with 'internal' type.")
    
    # autorisé la précommande pour le produit
    is_preorder_allowed = fields.Boolean(string="précommande Autorisée", compute="_compute_is_preorder_allowed")

    @api.depends('qty_available', 'incoming_qty')
    def _compute_is_preorder_allowed(self):
        for product in self:
            if product.qty_available <= product.preorder_threshold and product.incoming_qty > 0:
                product.is_preorder_allowed = True
            else:
                product.is_preorder_allowed = False
