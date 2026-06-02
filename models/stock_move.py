# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    stock_request_line_id = fields.Many2one(comodel_name="stock.request.line", string="Stock Request List")
    requisition_line_id = fields.Many2one(comodel_name='requisition.order', string='Línea de requisición (origen)')
    requisition_id = fields.Many2one(comodel_name='employee.purchase.requisition', related='requisition_line_id.requisition_product_id', store=True)

    requisition_ids = fields.Many2many(
        comodel_name='employee.purchase.requisition',
        string='Requisiciones origen',
        help='Requisiciones que contribuyen a este movimiento'
    )

