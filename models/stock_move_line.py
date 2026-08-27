# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    requisition_line_id = fields.Many2one(comodel_name='requisition.order', string='Línea de requisición')
    requisition_id = fields.Many2one(comodel_name='employee.purchase.requisition', related='requisition_line_id.requisition_product_id', store=True)

    ## Evitar que se muestren num de series que no estén en disponibilidad

    # Campo que contiene únicamente las series con stock en el origen
    available_lot_ids = fields.Many2many(
        'stock.lot',
        compute='_compute_available_lot_ids',
        string='Lotes Disponibles en Origen'
    )

    @api.depends('product_id', 'location_id')
    def _compute_available_lot_ids(self):
        for line in self:
            if not line.product_id or not line.location_id:
                line.available_lot_ids = False
                continue

            # Buscar todas las ubicaciones internas del almacén origen
            locations = self.env['stock.location'].search([
                ('id', 'child_of', line.location_id.id),
                ('usage', '=', 'internal'),
            ])

            # Consultar los quants con stock disponible > 0
            quants = self.env['stock.quant'].search([
                ('product_id', '=', line.product_id.id),
                ('location_id', 'in', locations.ids),
                ('quantity', '>', 0),
                ('lot_id', '!=', False),
            ])

            line.available_lot_ids = quants.mapped('lot_id')
