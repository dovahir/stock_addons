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

    line_number = fields.Integer(compute='_compute_line_number', string='N.º Línea')

    def _compute_line_number(self):
        for move in self:
            if move.picking_id:
                moves = move.picking_id.move_ids.sorted(key=lambda m: (m.sequence, m.id))
                move.line_number = list(moves).index(move) + 1
            else:
                move.line_number = 0

