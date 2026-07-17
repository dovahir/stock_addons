# -*- coding: utf-8 -*-
from odoo import api, fields, models


class RequisitionProducts(models.Model):
    _inherit = 'requisition.order'

    is_dotation = fields.Boolean(
        compute='_compute_is_dotation',
        string='Aplica historial'
    )
    dotation_display = fields.Char(
        compute='_compute_dotation_display',
        string='Historial',
        store=False
    )

    @api.depends('product_id', 'product_id.categ_id')
    def _compute_is_dotation(self):
        for line in self:
            # Cambia 'Dotaciones' por el nombre exacto de la categoría que desees
            categ_name = line.product_id.categ_id.name or ''
            line.is_dotation = (categ_name == 'EPP')

    def _compute_dotation_display(self):
        for line in self:
            line.dotation_display = ''   # campo soporte para el widget

    def get_last_dotations(self):
        self.ensure_one()
        employee = self.requisition_product_id.employee_id
        if not employee:
            return []
        moves = self.env['stock.move'].search([
            ('product_id', '=', self.product_id.id),
            ('state', '=', 'done'),
            ('picking_id.emp', '=', employee.id),
            ('picking_code', '=', 'outgoing'),
        ], order='date desc', limit=2)
        return [{
            'picking_name': move.picking_id.name,
            'date': move.date.strftime('%d/%m/%Y %H:%M') if move.date else '',
        } for move in moves]