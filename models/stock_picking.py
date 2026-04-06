from odoo import models, fields, api, _

# Heredamos campos a stock.picking y stock.move para trazabilidad

class StockPicking(models.Model):
    _inherit = "stock.picking"

    stock_request_id = fields.Many2one(comodel_name="stock.request", string="Solicitudes de suministro")

class StockMove(models.Model):
    _inherit = "stock.move"

    stock_request_line_id = fields.Many2one(comodel_name="stock.request.line", string="Stock Request List")

class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    default_dest_picking_type = fields.Many2one(
        comodel_name='stock.picking.type',
        string="Tipo de destino predeterminado",
        help="Selecciona el tipo de operación por defecto que tendrá el destino"
    )