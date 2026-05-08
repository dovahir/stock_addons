# noinspection PyStatementEffect
{
    'name': 'Complementos para Inventario',
    'version': '1.0',
    'category': 'Stock',
    'author': 'Aldahir',
    'summary': 'Conjunto de complementos para el modulo de inventario.'
               'Incluye: '
               '    Proceso para solicitar suministro a base'
               '    Quitar reservas automáticamente a ordenes de entrega y trasferencias',
    'depends': ['stock', 'employee_purchase_requisition', 'product'],
    'data': [
        'security/stock_addons_security.xml',
        'security/ir.model.access.csv',
        'views/pending_send_view.xml',
        'data/ir_sequence_data.xml',
        'views/stock_picking_view.xml',
        'views/stock_request_view.xml',
		'wizard/requi_to_stock_request_wizard_view.xml',
		'wizard/request_selection_wizard_view.xml',
		'wizard/stock_request_cancel_wizard_view.xml',
        'wizard/stock_request_block_wizard_view.xml',
        'report/paper_format.xml',
        'report/traspaso_report.xml',
        'views/stock_quant_view.xml',
        'views/stock_quant_report_view.xml',
        'views/menu_view.xml',
],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'icon': '/stock_addons/static/description/icon.png',
}