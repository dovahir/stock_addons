# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    requisition_line_id = fields.Many2one(comodel_name='requisition.order', string='Línea de requisición')
    requisition_id = fields.Many2one(comodel_name='employee.purchase.requisition', related='requisition_line_id.requisition_product_id', store=True)

