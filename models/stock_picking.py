from odoo import fields, models, api, _
from odoo.exceptions import UserError

# Heredamos campos a stock.picking y stock.move para trazabilidad

class StockPicking(models.Model):
    _inherit = "stock.picking"

    stock_request_id = fields.Many2one(comodel_name="stock.request", string="Solicitudes de suministro")

    # Action para smartbutton en un picking
    def action_open_stock_request(self):
        self.ensure_one()
        if not self.stock_request_id:
            raise UserError(_('Este movimiento no está vinculado a ninguna solicitud de stock.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitud de stock'),
            'res_model': 'stock.request',
            'res_id': self.stock_request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # Interceptamos cuando el movimiento de stock finaliza para actualizar el stock_request
    def _action_done(self):
        res = super(StockPicking, self)._action_done()

        for picking in self:
            if picking.stock_request_id and picking.state == 'done':
                picking.stock_request_id._process_picking_validation(picking)

        return res

class StockMove(models.Model):
    _inherit = "stock.move"

    stock_request_line_id = fields.Many2one(comodel_name="stock.request.line", string="Stock Request List")

class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    # Asignamos un tipo de operación predeterminado para la recepción desde el origen
    # Aplica solo a traslados internos pues así lo maneja la empresa (Traslado -> Recepción)
    default_dest_picking_type = fields.Many2one(
        comodel_name='stock.picking.type',
        string="Recepción predeterminada",
        help="Selecciona el tipo de operación por defecto que tendrá el destino"
    )