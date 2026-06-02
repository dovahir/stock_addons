# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    # Asignamos un tipo de operación predeterminado para la recepción desde el origen
    # Aplica solo a traslados internos, pues así lo maneja la empresa (Traslado -> Recepción)
    default_dest_picking_type = fields.Many2one(
        comodel_name='stock.picking.type',
        string="Recepción predeterminada",
        help="Selecciona el tipo de operación por defecto que tendrá el destino"
    )

