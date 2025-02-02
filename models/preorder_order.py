# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models, api, _, exceptions
from odoo.tools import float_compare
from datetime import date, datetime, timedelta
from . import sale_order

import logging

_logger = logging.getLogger(__name__)


class Preorder(models.Model):
    _description = 'Preorder Order'
    _inherit = 'sale.order'

    account_payment_ids = fields.One2many('account.payment', 'sale_id', string="Pay sale advanced", readonly=True)
    amount_residual = fields.Float(
        "Residual Amount",
        readonly=True,
        compute_sudo=True,
        compute='_compute_advance_payment',
        digits=(16, 2),
        store=True
    )
    amount_payed = fields.Float('Payed Amount', compute_sudo=True, compute='_compute_advance_payment', digits=(16, 2), store=False)
    payment_line_ids = fields.Many2many(
        "account.move.line",
        string="Payment move lines",
        compute_sudo=True,
        compute="_compute_advance_payment",
        store=True,
    )
    advance_payment_status = fields.Selection(
        selection=[
            ("not_paid", "Not Paid"),
            ("paid", "Paid"),
            ("partial", "Partially Paid"),
        ],
        store=True,
        readonly=True,
        copy=False,
        tracking=True,
        compute_sudo=True,
        compute="_compute_advance_payment",
    )
    
    # Gestion des commandes échue
    state_due = fields.Selection(
        selection=[
            ("not_due", "Non échu"),
            ("due", "échu"),
        ],
        default='not_due',
        string="État d'échéance", 
        store=True,
        compute="_compute_is_due", 
        help="Indique si la commande a des échéances à venir ou dépassées"
    )
    days_util_due = fields.Integer(
        string="Jours avant/après échéance", 
        compute="_compute_is_due", 
        store=True,
        help="Négatif pour les échéances à venir (-5 à 0), positif pour les retard"
    )
    overdue_amount = fields.Float(
        string="Montant échu", 
        compute="_compute_is_due", 
        store=True, 
        help="Montant total des échéances dépassées"
    )
    
    payment_count = fields.Float(compute_sudo=True, compute="_compute_advance_payment")

    # Les dates 
    date_approved_creditorder = fields.Datetime("Date confirmation commande credit", store=True)
    first_payment_date = fields.Date("Date du Premier Paiement", compute='_compute_reminder_dates', readonly=False, store=True) # date confirmate date_order
    second_payment_date = fields.Date("Date du Deuxième Paiement", compute='_compute_reminder_dates', readonly=False, store=True) # un mois avant livraison
    third_payment_date = fields.Date("Date du Troisième Paiement", compute='_compute_reminder_dates', readonly=False, store=True) 
    fourth_payment_date = fields.Date("Date du Quatrième Paiement", compute='_compute_reminder_dates', readonly=False, store=True) # date livraison commitment_date

    # Montants à payer
    first_payment_amount = fields.Float("1er amount", compute="_compute_order_data", digits=(16, 2), store=True) 
    second_payment_amount = fields.Float("2nd amount", compute="_compute_order_data", digits=(16, 2), store=True) 
    third_payment_amount = fields.Float("3rd amount", compute="_compute_order_data", digits=(16, 2), store=True)
    fourth_payment_amount = fields.Float("4rd amount", compute="_compute_order_data", digits=(16, 2), store=True)

    # Status de paiements
    first_payment_state = fields.Boolean(string="1er Payment status", compute='_compute_order_data', default=False, store=True)
    second_payment_state = fields.Boolean(string="2nd Payment status", compute='_compute_order_data', default=False, store=True)
    third_payment_state = fields.Boolean(string="3rd Payment status", compute='_compute_order_data', default=False, store=True)
    fourth_payment_state = fields.Boolean(string="4rd Payment status", compute='_compute_order_data', default=False, store=True)

    invoices = fields.One2many('account.move', 'sale_id', string="Invoices Sale Order", readonly=True)

    # Commande à crédit
    validation_rh_state = fields.Selection([
        ('pending', 'Validation en cours'),
        ('validated', 'Validé'),
        ('rejected', 'Rejeté'),
        ('cancelled', 'Annulé'),
    ], string='Validation RH client', required=True, default='pending')
    validation_rh_date = fields.Date(string='Date de Validation RH', readonly=True)
    validation_rh_partner_id = fields.Many2one('res.partner', string="Utilisateur RH", readonly=True)

    validation_admin_state = fields.Selection([
        ('pending', 'En cours de validation'),
        ('validated', 'Validé'),
        ('rejected', 'Rejeté'),
        ('cancelled', 'Annulé'),
    ], string='Validation responsable vente', required=True, default='pending', )
    validation_admin_date = fields.Date(string='Date de Validation Admin', readonly=True)
    validation_admin_user_id = fields.Many2one('res.users', string="Utilisateur Admin",
                                               readonly=True)
    validation_admin_comment = fields.Text(string='Commentaire Admin', readonly=True)


    # ----------------------------------------------- Methodes ------------------------------------------------------
        
    def validate_rh(self):

        for order in self:
            # Vérification de l'appartenance de l'utilisateur au groupe requis
            if self.env.user.has_group("orbit.credit_group_user"):
                entreprise = order.partner_id.parent_id
                _logger.info(f"ID Entreprise de l'employe === : {order.partner_id.parent_id.id}")
                if entreprise and entreprise.id != 2:
                    # Filtrer pour obtenir le responsable principal de la validation
                    user_main = order.partner_id.parent_id.child_ids.filtered(lambda p: p.role == 'main_user')
                    if user_main:
                        user_main = user_main[0]
                        order.write({
                            'validation_rh_state': 'validated',
                            'validation_rh_date': fields.Datetime.now(),
                            'validation_rh_partner_id': user_main.id
                        })
                    else:
                        raise exceptions.ValidationError(_("Aucun utilisateur avec le rôle Principal n'est défini dans l'entreprise associée du client."))
                else:
                    # Si l'entreprise n'est pas définie, utiliser l'utilisateur actuel
                    order.write({
                        'validation_rh_state': 'validated',
                        'validation_rh_date': fields.Datetime.now(),
                        'validation_rh_partner_id': self.env.user.id
                    })
            else:
                raise exceptions.ValidationError(_(
                    "Vous n'avez pas les droits requis pour valider cette commande. "
                    "Veuillez contacter un utilisateur ayant les permissions nécessaires dans le groupe 'Utilisateur Crédit'."
                    ))

    def reject_rh(self):
        for order in self:
            order.write({
                'validation_rh_state': 'rejected',
                'validation_rh_date': fields.Datetime.now(),
                'validation_rh_partner_id': self.partner_id.id
            })

    def approved_responsable(self):
        for order in self:
            order.write({
                'validation_admin_state': 'validated',
                'validation_admin_date': fields.Datetime.now(),
                'validation_admin_user_id': self.env.user.id,
            })

    def rejected_responsable(self):
        for order in self:
            order.write({
                'validation_admin_state': 'rejected',
                'validation_admin_date': fields.Datetime.now(),
                'validation_admin_user_id': self.env.user.id,
            })
    
    def send_resp_client(self):
        self.write({
                'state': 'validation', 
                })
        # for order in self:
        #     order.write({
        #         'state': 'validation', 
        #         })

    @api.depends('order_line.invoice_lines')
    def _get_invoices(self):
        # The invoice_ids are obtained thanks to the invoice lines of the SO
        # lines, and we also search for possible refunds created directly from
        # existing invoices. This is necessary since such a refund is not
        # directly linked to the SO.
        for order in self:
            invoices = order.order_line.invoice_lines.move_id.filtered(lambda r: r.move_type in ('out_invoice', 'out_refund'))
            order.invoices = invoices

    def action_view_payments(self):
        payments = self.mapped("account_payment_ids")
        action_ref = 'account.action_account_payments'
        # action_ref = 'account.action_move_out_invoice_type'
        action = self.env['ir.actions.act_window']._for_xml_id(action_ref)
        action['domain'] = [('id', 'in', payments.ids), ('sale_id', '=', self.id)]
        action['context'] = {
            'default_partner_id': self.partner_id.id,
            'default_sale_id': self.id,
            'default_payment_type': 'inbound',
            'default_ref': self.name,
            'default_date': fields.Datetime.today(),
            }
        
        if self.amount_payed < self.first_payment_amount:
            action['context']['default_amount'] = self.first_payment_amount
        elif self.amount_payed < (self.first_payment_amount + self.second_payment_amount):
            action['context']['default_amount'] = self.second_payment_amount
        else:
            action['context']['default_amount'] = self.third_payment_amount

        return action

    # ------------------------------------------ computes methods ----------------------
    
    @api.model
    def cron_due_orders(self):
        # Récupérer toutes les commandes
        orders = self.search([])
        orders._compute_is_due()
        
    @api.depends('first_payment_date', 'first_payment_state', 'first_payment_amount',
                 'second_payment_date', 'second_payment_state', 'second_payment_amount',
                 'third_payment_date', 'third_payment_state', 'third_payment_amount',
                 'fourth_payment_date', 'fourth_payment_state', 'fourth_payment_amount',
                 'type_sale', 'validity_date', 'amount_residual', 'advance_payment_status')
    def _compute_is_due(self):
        current_date = fields.Date.context_today(self)
        for order in self:
            # Par défaut, on réinitialise les valeurs
            order.state_due = 'not_due'
            order.days_util_due = 0
            order.overdue_amount = 0.0

            # 1. Cas des commandes de type preorder et creditorder
            if order.type_sale in ['preorder', 'creditorder']:
                relevant_diffs = []
                overdue_total = 0.0
                payment_data = [
                    (order.first_payment_date, order.first_payment_state, order.first_payment_amount),
                    (order.second_payment_date, order.second_payment_state, order.second_payment_amount),
                    (order.third_payment_date, order.third_payment_state, order.third_payment_amount),
                    (order.fourth_payment_date, order.fourth_payment_state, order.fourth_payment_amount)
                ]
                for pay_date, pay_state, pay_amount in payment_data:
                    # On considère uniquement les échéances ayant une date et dont l'état n'est pas renseigné (non payé)
                    if pay_date and not pay_state:
                        days_diff = (current_date - pay_date).days
                        relevant_diffs.append(days_diff)
                        # Si l'échéance est dépassée (days_diff >= 0), on cumule le montant correspondant
                        if days_diff >= 0:
                            overdue_total += pay_amount

                if relevant_diffs:
                    # S'il y a au moins une échéance dépassée, on considère la commande comme due
                    overdue_diffs = [d for d in relevant_diffs if d > 0]
                    if overdue_diffs:
                        order.state_due = 'due'
                        # On prend le retard maximal pour information
                        order.days_util_due = max(overdue_diffs)
                        order.overdue_amount = overdue_total
                    else:
                        # Dans le cas où les échéances ne sont pas encore dépassées
                        order.state_due = 'not_due'
                        order.days_util_due = max(relevant_diffs)
                        order.overdue_amount = 0.0

            # 2. Cas des commandes de type order
            elif order.type_sale == 'order' and order.validity_date:
                # Si la date de validité est dépassée
                if order.validity_date < current_date:
                    # Et s'il reste un solde dû ou que le statut de paiement n'est pas "paid"
                    if order.amount_residual > 0 or order.advance_payment_status != 'paid':
                        order.state_due = 'due'
                        # Le nombre de jours en retard est calculé depuis la date de validité
                        order.days_util_due = (current_date - order.validity_date).days
                        # Ici, on considère le montant restant dû comme montant en retard
                        order.overdue_amount = order.amount_residual
                    else:
                        # Si le solde est réglé, on ne considère pas la commande comme due
                        order.state_due = 'not_due'
                        order.days_util_due = 0
                        order.overdue_amount = 0.0

            # 3. Pour les autres cas, on laisse les valeurs par défaut : non due
            else:
                order.state_due = 'not_due'
                order.days_util_due = 0
                order.overdue_amount = 0.0    
        
                    
    @api.depends(
            'order_line.price_subtotal', 
            'order_line.price_tax', 
            'order_line.price_total', 
            'account_payment_ids', 
            'amount_residual',
            'date_approved_creditorder'
    )
    def _compute_order_data(self):
        for order in self:
            order_lines = order.order_line.filtered(lambda x: not x.is_downpayment)
            if order_lines:
                sale_amount_total = sum(order_lines.mapped('price_subtotal')) + sum(order_lines.mapped('price_tax'))

                if order.type_sale == 'preorder':
                    # les montants des paiements
                    amount1 = round(sale_amount_total * 0.3, 2)
                    amount2 = round(sale_amount_total * 0.3, 2)
                    amount3 = round(sale_amount_total * 0.4, 2)

                    order.first_payment_amount = amount1
                    order.second_payment_amount = amount2
                    order.third_payment_amount = amount3

                    payments_amount = sum(order.account_payment_ids.filtered(lambda x: x.state == 'posted').mapped('amount'))

                    if payments_amount >= round(amount1):
                        order.first_payment_state = True
                    else:
                        order.first_payment_state = False

                    if payments_amount >= round(amount2 + amount1):
                        order.second_payment_state = True
                    else:
                        order.second_payment_state = False

                    if payments_amount >= order.amount_total and order.amount_residual <= 0:
                        order.third_payment_state = True
                    else:
                        order.third_payment_state = False
                
                if order.type_sale == 'creditorder':
                    # les montants des paiements
                    amount1 = round(sale_amount_total * 0.5, 2)
                    amount2 = round(sale_amount_total * 0.2, 2)
                    amount3 = round(sale_amount_total * 0.15, 2)
                    amount4 = round(sale_amount_total * 0.15, 2)

                    order.first_payment_amount = amount1
                    order.second_payment_amount = amount2
                    order.third_payment_amount = amount3
                    order.fourth_payment_amount = amount4

                    payments_amount = sum(order.account_payment_ids.filtered(lambda x: x.state == 'posted').mapped('amount'))

                    if payments_amount >= round(amount1):
                        order.first_payment_state = True
                    else:
                        order.first_payment_state = False

                    if payments_amount >= round(amount2 + amount1):
                        order.second_payment_state = True
                    else:
                        order.second_payment_state = False
                    
                    if payments_amount >= round(amount3 + amount2 + amount1):
                        order.third_payment_state = True
                    else:
                        order.third_payment_state = False

                    if payments_amount >= order.amount_total and order.amount_residual <= 0:
                        order.fourth_payment_state = True
                    else:
                        order.fourth_payment_state = False

            else:
                order.first_payment_amount = 0.0
                order.second_payment_amount = 0.0
                order.third_payment_amount = 0.0
                order.fourth_payment_amount = 0.0

                order.first_payment_state = False
                order.second_payment_state = False
                order.third_payment_state = False
                order.fourth_payment_state = False


    @api.depends('date_order', 'commitment_date', 'date_approved_creditorder')
    def _compute_reminder_dates(self):
        for order in self:
            if order.type_sale == 'preorder':
                if order.date_order and order.commitment_date:
                    order.first_payment_date = order.date_order
                    order.second_payment_date = order.commitment_date - timedelta(days=30)
                    order.third_payment_date = order.commitment_date  # Date de Livraison
                else:
                    order.first_payment_date = False
                    order.second_payment_date = False
                    order.third_payment_date = False
            
            if order.type_sale == 'creditorder':
                if order.date_approved_creditorder:
                    order.first_payment_date = order.date_approved_creditorder
                    order.second_payment_date = order.date_approved_creditorder + timedelta(days=30)
                    order.third_payment_date = order.date_approved_creditorder  + timedelta(days=60)
                    order.fourth_payment_date = order.date_approved_creditorder  + timedelta(days=90) # Date de Livraison
                else:
                    order.first_payment_date = False
                    order.second_payment_date = False
                    order.third_payment_date = False
                    order.fourth_payment_date = False

    @api.depends(
        'currency_id',
        'company_id',
        'amount_total',
        'account_payment_ids',
        'account_payment_ids.state',
        'account_payment_ids.move_id',
        'account_payment_ids.move_id.line_ids',
        'account_payment_ids.move_id.line_ids.date',
        'account_payment_ids.move_id.line_ids.debit',
        'account_payment_ids.move_id.line_ids.credit',
        'account_payment_ids.move_id.line_ids.currency_id',
        'account_payment_ids.move_id.line_ids.amount_currency',
        'invoice_ids.amount_residual'
    )
    
    @api.depends('account_payment_ids.move_id.line_ids', 'invoice_ids', 'amount_total', 'currency_id', 'company_id')
    def _compute_advance_payment(self):
        """
        Calcule les paiements anticipés d'un bon de commande en prenant en compte :
          - Les paiements directement associés au bon (via account_payment_ids).
          - Les paiements réalisés sur les factures liées (invoice_ids).
        
        Les étapes sont les suivantes :
          1. Pour chaque ligne de paiement (issue de account_payment_ids), on récupère le montant résiduel 
             (en devise de la ligne) et on le convertit dans la devise du bon si nécessaire.
          2. Pour chaque facture liée (invoice_ids), on calcule le montant payé sur la facture 
             (montant total - montant résiduel).
          3. Le montant résiduel du bon est calculé par : montant total - (paiements directs + paiements sur facture).
          4. L'état du paiement est déduit en fonction du montant résiduel.
        """
        for order in self:
            # 1. Traitement des paiements directs
            payment_lines = order.account_payment_ids.mapped("move_id.line_ids").filtered(
                lambda line: line.account_id.account_type == "asset_receivable" and line.parent_state == "posted"
            )
            advance_amount = 0.0
            for line in payment_lines:
                # Utilisation de la devise de la ligne, sinon celle de la société
                line_currency = line.currency_id or line.company_id.currency_id
                # Récupération du montant résiduel de la ligne (inverser le signe pour obtenir un montant positif)
                line_amount = line.amount_residual_currency if line.currency_id else line.amount_residual
                line_amount = -line_amount
                # Conversion dans la devise du bon de commande si nécessaire
                if line_currency != order.currency_id:
                    conversion_date = line.date or fields.Date.context_today(order)
                    line_amount = line_currency._convert(
                        line_amount, order.currency_id, order.company_id, conversion_date
                    )
                advance_amount += line_amount

            # 2. Traitement des paiements sur factures liées
            invoice_paid_amount = 0.0
            for invoice in order.invoice_ids.filtered(lambda inv: inv.move_type in ('out_invoice', 'out_refund')):
                invoice_paid_amount += invoice.amount_total - invoice.amount_residual

            # 3. Calcul du montant résiduel du bon de commande
            computed_amount_residual = order.amount_total - advance_amount - invoice_paid_amount

            # 4. Détermination de l'état de paiement
            if payment_lines or order.invoice_ids:
                cmp_result = float_compare(
                    computed_amount_residual, 0.0, precision_rounding=order.currency_id.rounding
                )
                if cmp_result <= 0:
                    payment_state = "paid"
                else:
                    payment_state = "partial"
            else:
                payment_state = "not_paid"

            # Mise à jour des champs du bon de commande
            order.payment_line_ids = payment_lines
            order.payment_count = len(payment_lines)
            order.amount_payed = order.amount_total - computed_amount_residual
            order.amount_residual = computed_amount_residual
            order.advance_payment_status = payment_state

    def action_cancel(self):
        res = super(Preorder, self).action_cancel()

        if self.type_sale == 'creditorder':
            self.write({
                'validation_rh_state': 'cancelled',
                'validation_admin_state': 'cancelled',
            })
            return res
        else:
            return res
    
    def action_confirm(self):
        res = super(Preorder, self).action_confirm()
        
        for order in self:
            
            if order.amount_residual <= 0:
                order.write({
                    'state': 'to_delivered'	
                })
            
            # Enregistre l'utilisateur connecté
            order.usr_confirmed = self.env.user

        if self.type_sale == 'order':
            # date = fields.Datetime.now()
            # self._create_invoices(date).action_post()
            self.message_post(body="La commande a été confirmée avec succès.")
            return res
        
        if self.type_sale == 'preorder':
            dates = [self.first_payment_date, self.second_payment_date, self.third_payment_date]
            amounts = [self.first_payment_amount, self.second_payment_amount, self.third_payment_amount]
            self._create_advance_invoices(dates, amounts)
            self.message_post(body="La commande a été confirmée avec succès.")

            return res
        
        if self.type_sale == 'creditorder':
            if self.validation_rh_state == 'validated':
                if self.validation_admin_state == 'validated':
                    if self.first_payment_state:
                        self.date_approved_creditorder = fields.Datetime.now()
                        return res
                    else:
                        raise exceptions.ValidationError(_("Veuillez procéder au paiement du premier acompte pour valider la commande à crédit."))
                else:
                    raise exceptions.ValidationError(_(
                        "La validation du responsable de vente est requise pour finaliser la commande à crédit." 
                        "Veuillez contacter un responsable pour approbation."
                        ))
            else:
                raise exceptions.ValidationError(_(
                    "La commande à crédit nécessite l'approbation du service des ressources humaines." 
                    "Veuillez contacter le responsable RH pour validation."
                    ))
        
    # @api.onchange('amount_residual')
    # def _onchange_state(self):
    #     if self.amount_residual <= 0:
    #         return self.write({ 'state': 'to_delivered' })

    def _create_advance_invoices(self, dates, amounts):
        for order in self:
            self.env['sale.advance.payment.inv'].create({
                'sale_order_ids': [(6, 0, order.ids)],
                'advance_payment_method': 'fixed',
                'fixed_amount': amounts[0],
            })._create_invoices(order, dates, amounts)

    @api.depends('invoices', 'invoice_ids')
    def check_invoices_paid(self):
        for order in self:
            for invoice in order.invoices:
                if invoice.payment_state != 'paid':
                    _logger.info(f"Status de paiements {invoice.payment_state}")
                    return False
        return True
    
    def action_to_delivered(self):
        for order in self:
            _logger.info(f"Status de paiements {order.check_invoices_paid()}")
            if order.type_sale == 'order':
                if order.amount_residual <= 0:
                    return order.write({ 'state': 'to_delivered' })  
                else:
                    raise exceptions.ValidationError(_("Veuillez effectuer les paiements"))
            if order.type_sale == 'preorder':
                if order.amount_residual <= 0 and order.advance_payment_status == 'paid':
                    return order.write({ 'state': 'to_delivered' })
                else:
                    raise exceptions.ValidationError(_("Veuillez effectuer les paiements"))
            if order.type_sale == 'creditorder':
                if order.validation_admin_state == 'validated' and order.first_payment_state:
                    return order.write({ 'state': 'to_delivered' })
                else:
                    raise exceptions.ValidationError(_("Veuillez effectuer le paiement du premier acompte"))
                
    @api.onchange('order_line.qty_delivered')
    def action_delivered(self):
        for order in self:
            undelivered_lines = order.order_line.filtered(lambda line: line.qty_delivered < line.product_uom_qty)
            if undelivered_lines:
                undelivered_produts = ", ".join(undelivered_lines.mapped('product_id.name'))
                raise exceptions.ValidationError(_("Veuillez effectuer la livraison des produits non livrés : {0}".format(undelivered_produts)))
            else:
            #  order._create_invoices()
               return order.write({'state': 'delivered'})
            
    def action_delivered_a(self):
        for order in self:
            undelivered_lines = order.order_line.filtered(lambda line: line.qty_delivered < line.product_uom_qty)
            if undelivered_lines and order.delivery_status != 'full':
                undelivered_produts = ", ".join(undelivered_lines.mapped('product_id.name'))
                raise exceptions.ValidationError(_("Veuillez effectuer la livraison des produits non livrés : {0}".format(undelivered_produts)))
            elif order.delivery_status == 'full':
               return order.write({ 'state': 'delivered' })
            
    # -------------------------------------------------- Envoyer un email de rappel -------------------------------------
    
    @api.model
    def action_send_due_emails(self):
        """ 
        Envoie :
          - Pour les commandes de type 'preorder' et 'creditorder' :
              * Un email informatif 2 jours avant une date d'échéance (sur l'une des échéances de paiement non réglées).
              * Un email de rappel 5 jours après, si la commande est échu (state_due = 'due' et délai de retard >= 5 jours).
          - Pour les commandes de type 'order' :
              * Un email de rappel 3 jours après la date d'échéance (basé sur validity_date) si la commande est échu.
        """
        current_date = fields.Date.context_today(self)
        sale_order_obj = self.env['sale.order']

        # --- Pour les commandes de type 'preorder' et 'creditorder' ---
        orders_pre = sale_order_obj.search([
            ('type_sale', 'in', ['preorder', 'creditorder']),
            # On peut affiner la recherche éventuellement sur les commandes non payées
        ])

        for order in orders_pre:
            # 1. Email informatif 2 jours AVANT l'échéance pour une échéance non encore réglée.
            # On vérifie pour chacune des échéances de paiement renseignées.
            send_informative = False
            payment_dates = [
                (order.first_payment_date, order.first_payment_state),
                (order.second_payment_date, order.second_payment_state),
                (order.third_payment_date, order.third_payment_state),
                (order.fourth_payment_date, order.fourth_payment_state)
            ]
            for pay_date, pay_state in payment_dates:
                if pay_date and not pay_state:
                    # Si la date d'échéance est dans 2 jours exactement
                    if (pay_date - current_date).days == 2:
                        send_informative = True
                        break

            if send_informative:
                # On utilise un modèle d'email préconfiguré pour l'information
                template = self.env.ref('orbit.preorder_creditorder_informative_template', raise_if_not_found=False)
                if template:
                    template.send_mail(order.id, force_send=True)

            # 2. Email de rappel 5 jours APRÈS l'échéance si la commande est échu
            # On se base sur le champ calculé "days_util_due" qui indique le nombre de jours de retard
            if order.state_due == 'due' and order.days_util_due >= 5:
                template = self.env.ref('orbit.preorder_creditorder_reminder_template', raise_if_not_found=False)
                if template:
                    template.send_mail(order.id, force_send=True)

        # --- Pour les commandes de type 'order' ---
        orders_order = sale_order_obj.search([
            ('type_sale', '=', 'order'),
            ('validity_date', '!=', False),  # On s'assure que la date d'échéance est renseignée
            ('state_due', '=', 'due')
        ])
        for order in orders_order:
            # Si la commande est échue, on envoie un email 3 jours APRÈS la date d'échéance (validity_date)
            if (current_date - order.validity_date).days >= 3:
                template = self.env.ref('orbit.order_overdue_reminder_template', raise_if_not_found=False)
                if template:
                    template.send_mail(order.id, force_send=True)
                    
        


