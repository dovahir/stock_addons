# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # Asignar las #Req de las líneas de compra a la recepción
    def _prepare_stock_move_vals(self, picking, price_unit, product_uom_qty, product_oum):
        vals = super()._prepare_stock_move_vals(picking, price_unit, product_uom_qty, product_oum)
        if self.req_ids:
            vals['requisition_ids'] = self.req_ids.ids
        else:
            vals['requisition_ids'] = [(5,)]
        return vals

