# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models, api, _, exceptions
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from . import sale_order

import logging

_logger = logging.getLogger(__name__)

def chaine_vers_valeur(chaine):
    valeur = 0
    for caract in chaine:
        valeur = valeur * 26 + (ord(caract) - ord('a') + 1)
    return valeur

CODES = {
    'validated': chaine_vers_valeur('validated'),
    'rejected': 5678,
    'cancelled': 91011,
}
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
            ("not_paid", "Non Payé"),
            ("paid", "Payé"),
            ("partial", "Paiemnt en cours"),
        ],
        store=True,
        readonly=True,
        copy=False,
        string="Etat Paiements",
        help="Indicates the status of the advance payment for this order.",
        tracking=True,
        compute_sudo=True,
        compute="_compute_advance_payment",
    )
    payment_count = fields.Float(compute_sudo=True, compute="_compute_advance_payment")
    
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
        string="Avant/Après échéance", 
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

    code_rh = fields.Integer(
        string='Code de validation RH', 
        compute='_compute_validation_codes', 
        store=False
    )

    code_resp = fields.Integer(
        string='Code de validation Responsable Vente',
        compute='_compute_validation_codes', 
        store=False
    )
    
    # paramétrables dynamiquement les montants et les dates pour les commandes à crédit
    creditorder_month_count = fields.Integer(
        string="Nombre d'échéance",
        default=4,
        help="Nombre de paiements mensuels pour une commande à crédit."
    )
    
    credit_month_rate = fields.Char(
        string="Taux d'Acompte (%)",
        default='50',
        help="Taux de répartition des montants pour chaque mois, séparés par des virgules (ex: 50,20,15,15)"
    )
    
    credit_payment_ids = fields.One2many(
        'sale.order.credit.payment',
        'order_id',
        domain="[('order_id', '=', id)]",
        string="Échéances de paiement crédit",
        compute='_compute_credit_payment_duedate_data',
        readonly=True,
        store=True,
    )
    
    # is_credit_customer = fields.Boolean('Crédit à Personnaliser', store=True)
                
    # ----------------------------------------------- Methodes ------------------------------------------------------
    @api.depends('validation_rh_state', 'validation_admin_state')
    def _compute_validation_codes(self):
        for order in self:
            order.code_rh = CODES.get(order.validation_rh_state, 0)
            order.code_resp = CODES.get(order.validation_admin_state, 0)
            
            
    def validate_rh(self):
        self._valid_rh()
        return True
    
    def approve_rh(self):
        self._valid_rh()
        return True
        
    def _valid_rh(self):
        """ Validation RH (gestion des droits et logique métier) """
        for order in self:
            # Vérification de l'appartenance de l'utilisateur au groupe requis
            if not self.env.user.has_group("orbit.credit_group_user"):
                raise exceptions.ValidationError(_(
                    "Vous n'avez pas les droits requis pour valider cette commande. "
                    "Veuillez contacter votre manager."
                    ))
                
            entreprise = order.partner_id.parent_id
            _logger.info(f"ID Entreprise de l'employe === : {order.partner_id.parent_id.id}")
            if entreprise and entreprise.id != 2:
                # Filtrer pour obtenir le responsable principal de la validation
                user_main = order.partner_id.parent_id.child_ids.filtered(lambda child: child.role == 'main_user')
                if user_main:
                    # order.code_rh = order.str_to_val("validated")
                    user_main = user_main[0]
                    order.write({
                        'validation_rh_state': 'validated',
                        'validation_rh_date': fields.Datetime.now(),
                        'validation_rh_partner_id': user_main.id
                    })
                    _logger.info(f"Utilisateur principal RH {user_main.name} vient de valider la commande.")
                    
                    return True
                     
                elif self.env.user.has_group("orbit.ccbmshop_credit_sale_order_group_manager"):
                    order.write({
                        'validation_rh_state': 'validated',
                        'validation_rh_date': fields.Datetime.now(),
                        'validation_rh_partner_id': self.env.user.partner_id.id
                    })
                    _logger.info(f"le manager des commandes à crédit {self.env.user.name} vient de valider la commande.")
                    
                    return True
                
                else:
                    raise exceptions.ValidationError(_("Aucun utilisateur avec le rôle Principal n'est défini dans l'entreprise associée du client."))
            else:
                
                raise exceptions.ValidationError(_("Le client doit contacter son entreprise associée ou contactez le manager des commandes à crédits ."))

    def reject_rh(self):
        self._reject_rh()
        
    def _reject_rh(self):
        for order in self:
            order.write({
                'validation_rh_state': 'rejected',
                'validation_rh_date': fields.Datetime.now(),
                'validation_rh_partner_id': self.partner_id.id
            })

    def approved_responsable(self):
        self._approved_responsable()
        
    def approve_res_vente(self):
        self._approved_responsable()
        
    def _approved_responsable(self):
        
        for order in self:
            if not self.env.user.has_group("orbit.ccbmshop_credit_sale_order_group_manager"):
                raise exceptions.ValidationError(_(
                    "Vous n'avez pas les droits requis pour valider cette commande. "
                    "Veuillez contacter votre manager."
                    ))
                
            order.write({
                'validation_admin_state': 'validated',
                'validation_admin_date': fields.Datetime.now(),
                'validation_admin_user_id': self.env.user.id,
            })
            
        return True
    

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
        """Action pour visualiser les paiements liés"""
              
        if not self._get_valid_payments():
            raise UserError(_("Aucun paiement trouvé pour cette commande"))

        payments = self._get_valid_payments()
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_account_payments')
        action.update({
            'domain': [('id', 'in', payments.ids)],
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_ref': self.name,
                'default_date': fields.Date.context_today(self),
                'default_amount': self._get_next_payment_amount(),
                'search_default_group_by_payment_type': True
            },
            'views': [(False, 'list'), (False, 'form')]
        })
        
        return action
    
    def _get_valid_payments(self):
        """ Retourne les paiements valides liés à la commande par les factures ou via la référence du bon de commande """
        self.ensure_one()
        invoice_names = self.invoice_ids.mapped('name')
        domain = [
            ('is_internal_transfer', '=', False), 
            ('state', '=', 'posted'), 
            '|', 
            ('ref', 'in', invoice_names), 
            ('ref', 'ilike', self.mapped('name')), 
            # ('ref', 'in', self.mapped('name'))
        ]
        
        payments = self.env['account.payment'].search(domain, order="date desc")
        
        return payments
    
    def _get_next_payment_amount(self):
        """Calcule dynamiquement le montant du prochain paiement attendu"""
        payments = self._get_valid_payments()
        paid = sum(payments.mapped('amount'))
        thresholds = [
            self.first_payment_amount,
            self.first_payment_amount + self.second_payment_amount,
            self.amount_total
        ]
        
        for threshold in thresholds:
            if paid < threshold:
                return threshold - paid
        return 0.0

    # ------------------------------------------ computes methods ----------------------
    
    @api.model
    def cron_due_orders(self):
        # Récupérer toutes les commandes
        orders = self.search([])
        orders._compute_is_due()
        
    @api.depends(
        'credit_payment_ids.due_date',
        'credit_payment_ids.state',
        'credit_payment_ids.amount',
        'type_sale',
        'validity_date',
        'amount_residual',
        'advance_payment_status'
    )
    def _compute_is_due(self):
        current_date = fields.Date.context_today(self)

        for order in self:
            # Valeurs par défaut
            order.state_due = 'not_due'
            order.days_util_due = 0
            order.overdue_amount = 0.0

            if order.type_sale in ['preorder', 'creditorder']:
                relevant_diffs = []
                overdue_total = 0.0

                for line in order.credit_payment_ids:
                    if line.due_date and not line.state:
                        days_diff = (current_date - line.due_date).days
                        relevant_diffs.append(days_diff)
                        if days_diff >= 0:
                            overdue_total += line.amount

                if relevant_diffs:
                    overdue_diffs = [d for d in relevant_diffs if d > 0]
                    if overdue_diffs:
                        order.state_due = 'due'
                        order.days_util_due = max(overdue_diffs)
                        order.overdue_amount = overdue_total
                    else:
                        order.state_due = 'not_due'
                        order.days_util_due = max(relevant_diffs)
                        order.overdue_amount = 0.0

            elif order.type_sale == 'order' and order.validity_date:
                if order.validity_date < current_date:
                    if order.amount_residual > 0 or order.advance_payment_status != 'paid':
                        order.state_due = 'due'
                        order.days_util_due = (current_date - order.validity_date).days
                        order.overdue_amount = order.amount_residual
                    else:
                        order.state_due = 'not_due'
                        order.days_util_due = 0
                        order.overdue_amount = 0.0
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
            order.payment_count = len(order._get_valid_payments())
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
            # Enregistre l'utilisateur connecté
            order.usr_confirmed = self.env.user

        if self.type_sale == 'order':
            self.message_post(body="La commande a été confirmée avec succès.")
            return res
        
        if self.type_sale == 'preorder':
            self.message_post(body="La commande a été confirmée avec succès.")

            return res
        
        if self.type_sale == 'creditorder':
            # Vérification des validations RH et Responsable de vente
            secret_code = CODES.get('validated', 0)
            if self.code_rh == secret_code:
                if self.code_resp == secret_code:
                    if self.first_payment_state or self.env.user.has_group("orbit.ccbmshop_sale_order_credit_manager"):
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
                # En cas de commande de type 'order' qui n'a pas de paiement résiduel
                return order.write({ 'state': 'to_delivered' })
              
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
                    if (pay_date - current_date).days < 0 and (pay_date - current_date).days >= -2:
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
                                
    # @api.onchange('is_credit_customer')
    # def _onchange_credit_customization(self):
    #     for order in self:
    #         if order.type_sale != 'creditorder':
    #             continue # Ne rien faire

    #         # Supprimer/Réinitialiser les lignes si personnalisation activée
    #         order.credit_payment_ids = [(5, 0, 0)]  
    #         if not order.is_credit_customer:
    #             # Recalculer les lignes automatiquement
    #             order._compute_credit_payment_duedate_data()
                

    @api.depends(
        'type_sale',
        'date_approved_creditorder',
        'creditorder_month_count',
        'order_line.price_total',
        'credit_payment_ids.rate',
        'credit_month_rate'
    )
    def _compute_credit_payment_duedate_data(self):
        for order in self:
            if order.type_sale != 'creditorder':
                order.credit_payment_ids = [(5, 0, 0)]
                continue

            # if order.is_credit_customer:
            #     # En mode personnalisation, ne pas recalculer sauf cas spécial
            #     month_count = order.creditorder_month_count
            #     if not order.credit_month_rate or month_count < 1:
            #         continue

            #     try:
            #         rates_raw = [float(rate.strip()) for rate in order.credit_month_rate.split(',')]
            #     except ValueError:
            #         continue

            #     rates_list = []
            #     provided_len = len(rates_raw)
            #     sum_provided = sum(rates_raw)

            #     if provided_len < month_count:
            #         remaining = max(0.0, 100.0 - sum_provided)
            #         remaining_slots = month_count - provided_len
            #         if remaining_slots > 0:
            #             equal_rate = round(remaining / remaining_slots, 2)
            #             rates_list = rates_raw + [equal_rate] * remaining_slots
            #             diff = round(100.0 - sum(rates_list), 2)
            #             rates_list[-1] += diff
            #         else:
            #             rates_list = rates_raw
            #     else:
            #         rates_list = rates_raw[:month_count]

            #     # Compléter si encore insuffisant
            #     if len(rates_list) < month_count:
            #         rates_list += [0.0] * (month_count - len(rates_list))

            #     base_date = order.date_approved_creditorder or fields.Datetime.now()
            #     commands = []

            #     for i in range(month_count):
            #         due_date = base_date + relativedelta(months=i)
            #         commands.append((0, 0, {
            #             'sequence': i + 1,
            #             'due_date': due_date.date(),
            #             'rate': rates_list[i],
            #             'amount': 0.0,
            #             'state': False
            #         }))
            #     order.credit_payment_ids = commands
            #     continue  # pas de calcul de montant ici

            # Mode automatique (is_credit_customer == False)
            # Récupérer les lignes produits hors acompte
            order_lines = order.order_line.filtered(lambda x: not x.is_downpayment)
            total_amount = sum(order_lines.mapped('price_total')) or 0.0
            month_count = order.creditorder_month_count
            base_date = order.date_approved_creditorder or fields.Datetime.now()

            try:
                rates_raw = [float(rate.strip()) for rate in order.credit_month_rate.split(',')]
            except ValueError:
                rates_raw = [100.0]  # fallback

            rates_list = []
            provided_len = len(rates_raw)
            sum_provided = sum(rates_raw)

            if provided_len < month_count:
                remaining = max(0.0, 100.0 - sum_provided)
                remaining_slots = month_count - provided_len
                if remaining_slots > 0:
                    equal_rate = round(remaining / remaining_slots, 2)
                    rates_list = rates_raw + [equal_rate] * remaining_slots
                    diff = round(100.0 - sum(rates_list), 2)
                    rates_list[-1] += diff
                else:
                    rates_list = rates_raw
            else:
                rates_list = rates_raw[:month_count]

            if len(rates_list) < month_count:
                rates_list += [0.0] * (month_count - len(rates_list))

            # Réutiliser les échéances existantes
            existing_installments = {inst.sequence: inst for inst in order.credit_payment_ids}
            total_rate = 0.0
            manual_amounts = 0.0

            for month in range(1, month_count + 1):
                rate = rates_list[month - 1]
                if month in existing_installments and existing_installments[month].is_amount_manual:
                    manual_amounts += existing_installments[month].amount
                else:
                    total_rate += rate

            remaining_amount = total_amount - manual_amounts
            commands = []

            for month in range(1, month_count + 1):
                due_date = base_date + relativedelta(months=month - 1)
                rate = rates_list[month - 1]
                if month in existing_installments:
                    inst = existing_installments[month]
                    update_vals = {'due_date': due_date.date(), 'rate': rate}
                    if not inst.is_amount_manual:
                        update_vals['amount'] = remaining_amount * (rate / total_rate) if total_rate else 0.0
                    commands.append((1, inst.id, update_vals))
                else:
                    installment_amount = remaining_amount * (rate / total_rate) if total_rate else 0.0
                    commands.append((0, 0, {
                        'sequence': month,
                        'due_date': due_date.date(),
                        'rate': rate,
                        'amount': installment_amount,
                        'state': False
                    }))

            # Supprimer les échéances excédentaires
            valid_sequences = set(range(1, month_count + 1))
            for seq, inst in existing_installments.items():
                if seq not in valid_sequences:
                    commands.append((2, inst.id, 0))

            # Ajustement final pour corriger les arrondis
            amounts_sum = 0.0
            for cmd in commands:
                if cmd[0] == 0:
                    amounts_sum += cmd[2].get('amount', 0.0)
                elif cmd[0] == 1:
                    inst = existing_installments.get(cmd[1])
                    if inst:
                        if inst.is_amount_manual:
                            amounts_sum += inst.amount
                        else:
                            amounts_sum += cmd[2].get('amount', inst.amount)

            diff = total_amount - (amounts_sum + manual_amounts)
            if abs(diff) > 0.01:
                # Trouver la dernière échéance non manuelle
                last_seq = None
                for month in range(month_count, 0, -1):
                    if month in existing_installments:
                        if not existing_installments[month].is_amount_manual:
                            last_seq = month
                            break
                    else:
                        last_seq = month
                        break
                if last_seq:
                    for idx, cmd in enumerate(commands):
                        if (cmd[0] == 1 and existing_installments.get(cmd[1]) and existing_installments[cmd[1]].sequence == last_seq) \
                        or (cmd[0] == 0 and cmd[2]['sequence'] == last_seq):
                            if cmd[0] == 1:
                                cmd[2]['amount'] += diff
                            else:
                                cmd[2]['amount'] += diff
                            break

            order.credit_payment_ids = commands

    @api.onchange('credit_payment_ids', 'order_line')
    def _onchange_installments(self):
        for order in self:
            if order.type_sale != 'creditorder' or not order.credit_payment_ids:
                return
                
            # Calculer le total
            order_lines = order.order_line.filtered(lambda x: not x.is_downpayment)
            total_amount = sum(order_lines.mapped('price_total')) or 0.0
            
            # Calculer la somme des échéances
            installments_total = sum(order.credit_payment_ids.mapped('amount'))
            
            # Ajuster la dernière échéance si différence
            if abs(total_amount - installments_total) > 0.01:
                last_installment = max(order.credit_payment_ids, key=lambda x: x.sequence)
                if not last_installment.is_amount_manual:
                    last_installment.amount += total_amount - installments_total
                    last_installment.is_amount_manual = True

# ------------------------------------------ Modèle pour les paiements mensuels des commandes à crédit ----------------------
class SaleOrderPaymentInstallment(models.Model):
    _name = 'sale.order.credit.payment'
    _description = "Installment de paiement pour commande à crédit"
    _order = 'sequence'

    _sql_constraints = [
        ('unique_sequence_per_order', 'UNIQUE(order_id, sequence)', 'La séquence doit être unique par commande!')
    ]

    sequence = fields.Integer(string="Mois", required=True)
    due_date = fields.Date(string="Date d'échéance")
    amount = fields.Float(string="Montant", digits=(16, 2))
    state = fields.Boolean(string="Payé", compute='_compute_paid_amount_and_state', store=True)
    order_id = fields.Many2one('sale.order', string="Commande", ondelete='cascade')
    rate = fields.Float(string="Taux (%)", digits=(5,2), default=0.0)
    is_amount_manual = fields.Boolean(string="Montant modifié", default=False)
    
    currency_id = fields.Many2one(related='order_id.currency_id', string="Devise", readonly=True, store=True)
    paid_amount = fields.Monetary(string="Montant payé", compute='compute_paid_amount_and_state', store=True)
    # is_paid = fields.Boolean(string="Payée ?", compute='_compute_paid_amount', store=True)
    
    
    @api.onchange('order_id')
    def _onchange_order_id_currency(self):
        for rec in self:
            if rec.order_id:
                rec.currency_id = rec.order_id.currency_id
                
    @api.depends(
        'order_id.account_payment_ids.state',
        'order_id.account_payment_ids.amount',
        'order_id.invoice_ids.payment_state',
        'order_id.invoice_ids.amount_residual',
        'order_id.invoice_ids.amount_total',
    )
    def _compute_paid_amount_and_state(self):
        for record in self:
            order = record.order_id

            # Paiements liés à la commande
            cmd_payments = order.account_payment_ids.filtered(lambda p: p.state == 'posted')
            cmd_paid_amount = sum(cmd_payments.mapped('amount'))

            # Paiements sur factures liées
            invoices = order.invoice_ids.filtered(lambda inv: inv.state == 'posted')
            inv_paid_amount = sum(inv.amount_total - inv.amount_residual for inv in invoices)

            total_paid = cmd_paid_amount + inv_paid_amount

            # Attribution des paiements aux lignes
            # payment_lines = order.credit_payment_ids.sorted('id')
            payment_lines = sorted(order.credit_payment_ids, key=lambda l: l.id if isinstance(l.id, int) else 0)
            paid_so_far = 0.0

            for line in payment_lines:
                if total_paid >= paid_so_far + line.amount:
                    line.paid_amount = line.amount
                    line.state = True
                    paid_so_far += line.amount
                elif total_paid > paid_so_far:
                    # Paiement partiel
                    line.paid_amount = total_paid - paid_so_far
                    line.state = False
                    paid_so_far = total_paid
                else:
                    line.paid_amount = 0.0
                    line.state = False


    
    @api.constrains('order_id', 'rate', 'amount')
    def _check_credit_rate_total(self):
        for order in self.mapped('order_id'):
            if order.type_sale != 'creditorder':
                continue
            
            commands = order.credit_payment_ids.sorted('sequence')
            total_rate = sum(commands.mapped('rate'))
    
    @api.onchange('rate', 'order_id.order_line')
    def _onchange_rate_update_amount(self):
        for rec in self:
            if not rec.order_id or not rec.order_id.order_line:
                continue
            total = sum(rec.order_id.order_line.filtered(lambda l: not l.is_downpayment).mapped('price_total'))
            if total and not rec.is_amount_manual:
                rec.amount = round((rec.rate / 100.0) * total, 2)
            
    @api.onchange('amount')
    def _onchange_amount_update_rate(self):
        for rec in self:
            if not rec.order_id or not rec.order_id.order_line:
                continue
            total = sum(rec.order_id.order_line.filtered(lambda l: not l.is_downpayment).mapped('price_total'))
            if total:
                rec.rate = round((rec.amount / total) * 100.0, 2)
                rec.is_amount_manual = True
                