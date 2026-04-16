# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

# Clase que hereda al módulo de requisicion
class EmployeePurchaseRequisition(models.Model):
    _inherit = 'employee.purchase.requisition'

    stock_request_count = fields.Integer(string='Solicitudes de suministro',
                                             compute='_compute_stock_request_count')

    # Muestra los stock_request de una requisicion
    def get_stock_request(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitudes de suministro'),
            'view_mode': 'tree,form',
            'res_model': 'stock.request',
            'domain': [('requisition_ids', '=', self.id)],
        }

    # Contador para solicitudes de suministro en requisiciones
    def _compute_stock_request_count(self):
        for record in self:
            self.stock_request_count = self.env['stock.request'].search_count([
                ('requisition_ids', '=', self.id)])
            self._compute_state()