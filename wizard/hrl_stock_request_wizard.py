from odoo import fields, models, api, _

class HrlStockRequestWizard(models.TransientModel):
    _name = 'hrl.stock.request.wizard'
    _description = 'Wizard para agregar movimientos a solicitud existente'

    request_id = fields.Many2one('hrl.stock.request', string='Solicitud', required=True)
    move_ids = fields.Many2many('stock.move', string='Movimientos')

    def action_add_moves(self):
        """Agrega los movimientos seleccionados a la solicitud elegida."""
        self.ensure_one()
        for move in self.move_ids:
            qty_pending = move.product_uom_qty - move.quantity
            if qty_pending <= 0:
                continue
            line = self.request_id.line_ids.filtered(lambda l: l.product_id == move.product_id)
            if line:
                line.product_qty += qty_pending
            else:
                self.request_id.line_ids.create({
                    'request_id': self.request_id.id,
                    'product_id': move.product_id.id,
                    'product_qty': qty_pending,
                    'product_uom_id': move.product_uom.id,
                    'name': move.product_id.display_name,
                })
        return {'type': 'ir.actions.act_window_close'}