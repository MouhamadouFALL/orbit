from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_preorder = fields.Boolean(string="Disponible en précommande", default=False) # produit disponible pour une précommande
    is_creditorder = fields.Boolean(string="Disponible pour commande à crédit", default=False) # produit disponible pour commande à crédit
    preorder_deadline = fields.Date(string="preorder expery date") # date à laquelle un produit ne sera plus disponible pour une précommande
    preorder_quantity_allow = fields.Integer(string="Quantité de précommande", default=0) # quantité autorisé à précommandé pour un produit
    preorder_payment_option = fields.Selection([
        ('full', 'Paiement complet'),
        ('partial', 'Paiement partiel')
    ], string="Option de paiement de précommande", default='full') # option de paiment accepté pour valider une précommande

    # la précommande sera activée uniquement lorsque la quantité disponible du produit est inférieure à un seuil défini
    preorder_threshold = fields.Integer(string="Preorder threshold", default=5)

    preorder_price = fields.Float('Prix précommande', digits=(16, 2),
        help="Prix pour les précommandes. Ce prix sera appliqué lorsqu'un produit est précommandé."
    )

    creditorder_price = fields.Float('Prix commande à crédit', digits=(16, 2),
        help="Prix pour les commandes à crédit. Ce prix sera appliqué lorsqu'un produit est disponible pour une commande à crédit."
    )
    
    
    # tag produit selon l'événement
    # event_tag = fields.Many2one('product.event.tag', string="Tag événement")
    

    # ------------------ Gestion des prix sur le produit ------------------
    # gestion des prix du produit en promotion
    en_promo = fields.Boolean(string="En promo", default=False, store=True)
    rate_price = fields.Float("Taux de promotion")

    promo_price = fields.Float(
        'Promo Price',
        digits=(16, 2),
        help="Price for promotions. This price will be applied when a product is in promotion",
        compute='_compute_promo_price',
        readonly=False,
        store=True
    )

    preordered_qty = fields.Float('Preordered Quantity', compute='_compute_preordered_qty', store=True, 
                                  help="Total quantity of products that have been preordered by customers but not yet delivered."
                                  )
    
    creditorder_qty = fields.Float('Creditorder Quantity', compute='_compute_creditorder_qty', store=True, 
                                  help="Total quantity of products that have been creditordered by customers but not yet delivered."
                                  )
    
    ordered_qty = fields.Float('Ordered Quantity', compute='_compute_ordered_qty', store=True, 
                                  help="Total quantity of products that have been ordered by customers but not yet delivered."
                                  )
    
    free_qty = fields.Float(
        'Free To Use Quantity ', related='product_variant_ids.free_qty',
        digits='Product Unit of Measure', store=True,
        help="Forecast quantity (computed as Quantity On Hand "
             "- reserved quantity)\n"
             "In a context with a single Stock Location, this includes "
             "goods stored in this location, or any of its children.\n"
             "In a context with a single Warehouse, this includes "
             "goods stored in the Stock Location of this Warehouse, or any "
             "of its children.\n"
             "Otherwise, this includes goods stored in any Stock Location "
             "with 'internal' type.")
    
    
    # ------------------ Gestion des images pour les produits et les variantes de produits ------------------ 
    image_1 = fields.Binary(string='Image 1')
    image_2 = fields.Binary(string='Image 2')
    image_3 = fields.Binary(string='Image 3')
    image_4 = fields.Binary(string='Image 4')
    
    # Nombre d'images enregistré pour un produit
    image_count = fields.Integer("Nombre d'images", compute="_compute_image_count", store=True, help="Total number of images associated with this product.")
    
    # ------------------ Gestion des prix sur le produit ------------------
    
    # gestion du prix de vente du produit
    markup_percentage = fields.Float(
        string="Marge (%)",
        default=lambda self: self._get_default_markup(),
        digits='Product Price', 
        help="Pourcentage de marge appliqué au coût standard pour déterminer le prix de vente."
    )
    
    @api.model
    def _get_default_markup(self):
        """ Récupère la marge globale définie dans res.config.settings """
        return float(self.env['ir.config_parameter'].sudo().get_param('product.global_markup_percentage', default=15))
    
    @api.model
    def update_product_prices(self):
        """ Met à jour automatiquement le prix de vente si inférieur au prix calculé """
        products = self.search([])
        for product in products:
            if product.markup_percentage:
                min_price = product.standard_price * (1 + product.markup_percentage / 100)
            else:
                min_price = product.standard_price * 1.15  # Calcul du prix minimum
            if product.list_price < min_price:
                product.list_price = min_price  # Mise à jour du prix de vente
                    
    @api.onchange('markup_percentage')
    def _onchange_markup_percentage(self):
        """ Met à jour list_price si le taux de marge est modifié """
        for product in self:
            if product.standard_price > 0:
                product.list_price = product.standard_price * (1 + product.markup_percentage / 100)
                # min_price = product.standard_price * (1 + product.markup_percentage / 100)
                # if product.list_price < min_price:
                #     product.list_price = min_price
        
    @api.depends_context('company')
    @api.depends('product_variant_ids', 'product_variant_ids.standard_price')
    def _compute_standard_price(self):
        """
        Calcule le coût standard en fonction des variantes et met à jour le prix de vente.
        NOTA : On ne dépend plus de markup_percentage pour éviter que la modification du taux
        ne déclenche une réinitialisation du standard_price pour les templates à variantes multiples.
        """
        # Sélection des templates ayant une seule variante
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.standard_price = template.product_variant_ids.standard_price
            template.list_price = template.standard_price * (1 + template.markup_percentage / 100)
            # min_price = template.standard_price * (1 + template.markup_percentage / 100)
            # if template.list_price < min_price:
            #     template.list_price = min_price

        # Pour les templates à plusieurs variantes, vous pouvez choisir la logique souhaitée.
        # Ici, on ne souhaite pas écraser un éventuel standard_price existant lors de la modification du taux,
        # donc on ne force pas la valeur à 0.
        for template in (self - unique_variants):
            # Si vous souhaitez conserver la valeur existante, commentez la ligne suivante.
            # template.standard_price = 0.0
            pass

            
    def _set_standard_price(self):
        """Met à jour le coût des variantes et recalcule le prix de vente."""
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.standard_price = template.standard_price
                # Mise à jour du prix de vente après modification du coût
                min_price = template.standard_price * (1 + template.markup_percentage / 100)
                if template.list_price < min_price:
                    template.list_price = min_price

    @api.depends('image_1920', 'product_variant_ids.image_variant_1920', 'image_1', 'image_2', 'image_3', 'image_4')
    def _compute_image_count(self):
        for template in self:
            # Comptage des images du template
            images = [template.image_1920, template.image_1, template.image_2, template.image_3, template.image_4]
            count = sum(1 for image in images if image)

            # Comptage des images des variantes
            count += len(template.product_variant_ids.filtered(lambda p: p.image_variant_1920))
            template.image_count = count
            
    # def write(self, vals):
    #     """ Met à jour le compteur d'images à chaque modification """
    #     res = super(ProductTemplate, self).write(vals)
    #     if any(field in vals for field in ['image_1920', 'image_1', 'image_2', 'image_3', 'image_4']):
    #         self._compute_image_count()
    #     return res
    
    @api.model
    def cron_update_image_count(self):
        """ Recalcul périodique du nombre d'images via une tâche cron """
        products = self.search([])
        products._compute_image_count()
        self._cr.commit()  # Forcer la sauvegarde en base pour éviter les pertes si la tâche plante
            
    @api.depends('rate_price')
    def _compute_promo_price(self):
        for prod in self:
            if prod.rate_price > 0.0 and prod.list_price > 1.0:
                prod.promo_price = prod.list_price * (1 - (prod.rate_price / 100))
            else:
                prod.promo_price = prod.list_price
    
    @api.depends('qty_available', 'outgoing_qty')
    def _compute_preordered_qty(self):
        for product in self:
            # Filtrer les lignes de commande client qui sont dans un état de précommande (par exemple, 'preorder')
            preordered_lines = self.env['sale.order.line'].search([
                ('product_id.product_tmpl_id', '=', product.id),
                ('order_id.state', 'in', ['sale', 'to_delivered']),
                ('order_id.type_sale', '=', 'preorder')
                # Assumant que 'preorder' est l'état d'une précommande
            ])
            #if preordered_lines.
            product.preordered_qty = sum(line.product_uom_qty for line in preordered_lines) - sum(line.qty_delivered for line in preordered_lines)

    @api.depends('qty_available', 'outgoing_qty')
    def _compute_creditorder_qty(self):
        for product in self:
            # Filtrer les lignes de commande client qui sont dans un état de commande crédit (par exemple, 'creditorder')
            creditorder_lines = self.env['sale.order.line'].search([
                ('product_id.product_tmpl_id', '=', product.id),
                ('order_id.state', 'in', ['sale', 'to_delivered']),
                ('order_id.type_sale', '=', 'creditorder')
                # Assumant que 'preorder' est l'état d'une précommande
            ])
            #if preordered_lines.
            product.creditorder_qty = sum(line.product_uom_qty for line in creditorder_lines) - sum(line.qty_delivered for line in creditorder_lines)
            
            
    @api.depends('qty_available', 'outgoing_qty')
    def _compute_ordered_qty(self):
        for product in self:
            # Filtrer les lignes de commande client qui sont dans un état de précommande (par exemple, 'preorder')
            ordered_lines = self.env['sale.order.line'].search([
                ('product_id.product_tmpl_id', '=', product.id),
                ('order_id.state', 'in', ['sale', 'to_delivered']),
                ('order_id.type_sale', '=', 'order')
                # Assumant que 'preorder' est l'état d'une précommande
            ])
            #if preordered_lines.
            product.ordered_qty = sum(line.product_uom_qty for line in ordered_lines) - sum(line.qty_delivered for line in ordered_lines)
            
    
    @api.depends('qty_available', 'outgoing_qty')
    def _compute_preordered_qty_dev(self):
        for product in self:
            # Filtrer les lignes de commande client qui sont dans un état de précommande (par exemple, 'preorder')
            preordered_lines = self.env['sale.order.line'].search([
                ('product_id.product_tmpl_id', '=', product.id),
                ('order_id.state', 'in', ['sale', 'to_delivered']),
                ('order_id.type_sale', '=', 'preorder')
                # Assumant que 'preorder' est l'état d'une précommande
            ])

            preorder_lines_delivered = self.env['sale.order.line'].search([
                ('product_id.product_tmpl_id', '=', product.id),
                ('order_id.state', 'in', ['delivered']),
                ('order_id.type_sale', '=', 'preorder')
                # Assumant que 'preorder' est l'état d'une précommande
            ])

            # _logger.info(f"line sale ====> {preordered_lines} ")
            # Calculer la somme des quantités précommandées

            product.preordered_qty = sum(line.product_uom_qty for line in preordered_lines) - sum(line.qty_delivered for line in preorder_lines_delivered)
            
            # preordered_qty_delivered = 0.0
            # preordered_qty_undelivered = 0.0
            # if preordered_lines:
            #     preordered_qty_undelivered = sum(line.product_uom_qty for line in preordered_lines)

            # if preorder_lines_delivered:
            #     preordered_qty_delivered = sum(line.qty_delivered for line in preorder_lines_delivered)

            # if (preordered_qty_undelivered > preordered_qty_delivered):
                #product.preordered_qty = preordered_qty_undelivered - preordered_qty_delivered
                

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
                
    # image_count = fields.Integer("Nombre d'images", compute="_compute_image_count", store=True, help="Total number of images associated with this product.")
    
    # def _compute_image_count(self):
    #     """Get the image from the template if no image is set on the variant."""
    #     for record in self:
    #         record.image_count = record.product_tmpl_id.image_count
