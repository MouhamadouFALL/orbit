# -*- coding: utf-8 -*-
{
    'name': "CCBM SHOP",
    'summary': """ Management three Business: Order, Preorder and creditorder.""",
    'description': """
        Optimising sales flows by effectively managing three categories of transactional processes: 
        standard orders, pre-orders and credit orders.
    """,
    'author': "CCBM DEV",
    'license': "AGPL-3",
    'website': "https://ccbme.sn",
    'category': 'CCBM/',
    'version': '16.0.1.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'product', 'sale', 'sale_crm','crm', 'account', 'purchase', 'stock', 'sale_stock'],

    # always loaded
    'data': [

        'security/orbit_security.xml',
        'security/ir.model.access.csv',
        
        # ***************************** actions planifier ****************
        'data/cron_update_image_count.xml',
        # 'data/cron_sale_order.xml',
        # 'data/preorder_creditorder_inf_remind_email.xml',

        'wizard/preorder_advance_payment_wzd_view.xml',
        'wizard/crm_opportunity_to_quotation_orbit_views.xml',
        'wizard/crm_type_sale_for_quotation_views.xml',

        # ***************************** Dossier views *******************
        'views/orbit_purchase_order.xml',
        'views/res_users_views.xml',
        'views/ir_ui_menu_views.xml',
        'views/res_partner_views.xml',
        'views/affiliate_views.xml',
        'views/product_product.xml',
        'views/sale_order_orbit_views.xml',
        'views/preorder_orbit_views.xml',
        'views/account_move_views.xml',
        'views/crm_lead_views.xml',
        'report/orbit_purchase_order_template.xml',
        'report/orbit_sale_order_template.xml',

        # ***************************** Menu ****************************
        'views/menu_views.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        # 'demo/demo.xml',
    ],
    'license': 'LGPL-3',
    'application': True,
    'installable': True,
    'auto_install': False,
}
