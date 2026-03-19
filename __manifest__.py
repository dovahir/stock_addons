# noinspection PyStatementEffect
{
    'name': 'Complementos para Inventario',
    'version': '1.0',
    'category': 'Stock',
    'author': 'Aldahir',
    'summary': 'Un conjunto de complementos para el modulo de inventario.',
    'depends': ['stock', 'employee_purchase_requisition'],
    'data': [
        # 'security/stock_addons_security.xml',
        # 'security/ir.model.access.csv',
        'views/pending_send_views.xml',
],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'icon': '/stock_addons/static/description/icon.png',
}