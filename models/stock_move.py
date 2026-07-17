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

    line_number = fields.Integer(compute='_compute_line_number', string='N.º Línea', store=False)

    @api.depends('picking_id', 'picking_id.move_ids', 'sequence')
    def _compute_line_number(self):
        for move in self:
            if not move.picking_id:
                move.line_number = 1  # sin picking, asigna 1
                continue
            ordered = move.picking_id.move_ids.sorted(key=lambda m: (m.sequence, m.id or 0))
            # Intentar encontrar la posición del movimiento actual por su ID
            try:
                pos = ordered.ids.index(move.id)
                move.line_number = pos + 1
            except ValueError:
                # Si no está en la lista asigna el número siguiente al último, para que nunca sea 0
                move.line_number = len(ordered) + 1

    # Evitar fusionar líneas de SR
    def _prepare_merge_moves_distinct_fields(self):
        distinct_fields = super()._prepare_merge_moves_distinct_fields()
        # Añadimos el campo que diferencia líneas de solicitud
        distinct_fields.append('stock_request_line_id')
        return distinct_fields