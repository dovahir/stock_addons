from odoo import fields, models, api, _
from odoo.exceptions import UserError

# Heredamos campos a stock.picking y stock.move para trazabilidad

class StockPicking(models.Model):
    _inherit = "stock.picking"

    stock_request_id = fields.Many2one(comodel_name="stock.request", string="Solicitudes de suministro")

    def _prepare_backorder_values(self, picking):
        values = super()._prepare_backorder_values(picking)
        if picking.stock_request_id:
            values['stock_request_id'] = picking.stock_request_id.id
        return values

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

    can_be_returned = fields.Boolean(compute='_compute_can_be_returned')

    @api.depends('stock_request_id.state', 'stock_request_id')
    def _compute_can_be_returned(self):
        for picking in self:
            if picking.stock_request_id and picking.stock_request_id.state in ('done_exact', 'done_partial',
                                                                               'done_adjusted'):
                picking.can_be_returned = False
            else:
                picking.can_be_returned = True

    # Sobreescritura de la validacion en un picking
    def _action_done(self):
        res = super(StockPicking, self)._action_done()

        for picking in self:
            # Interceptamos cuando el movimiento de stock finaliza para actualizar el stock_request
            if picking.stock_request_id and picking.state == 'done':
                picking.stock_request_id._process_picking_validation(picking)

            # Un picking es devolución si tiene un 'return_id' (campo que Odoo asigna al crear devolución)
            # O si sus movimientos tienen 'origin_returned_move_id'
            # if picking.return_id and picking.return_id.stock_request_id:
            #     # picking.return_id es el picking original del que se devuelve
            #     original_picking = picking.return_id
            #     stock_request = original_picking.stock_request_id
            #     if stock_request and stock_request.state not in ('delivery_returned', 'cancel'):
            #         stock_request.action_set_delivery_returned(picking)
            # # Alternativa: buscar a través de los movimientos
            # elif picking.move_ids:
            #     for move in picking.move_ids:
            #         if move.origin_returned_move_id and move.origin_returned_move_id.picking_id:
            #             original_picking = move.origin_returned_move_id.picking_id
            #             if original_picking and original_picking.stock_request_id:
            #                 stock_request = original_picking.stock_request_id
            #                 if stock_request and stock_request.state not in ('delivery_returned', 'cancel'):
            #                     stock_request.action_set_delivery_returned(picking)
            #                     break

        return res

    # Devuelve True si el picking es una devolución
    # (tiene return_id o sus movimientos tienen origin_returned_move_id)
    def _is_return_picking(self):
        if self.return_id:
            return True
        for move in self.move_ids:
            if move.origin_returned_move_id:
                return True
        return False

    # Interceptamos la cancelación para notificar al stock_request
    def action_cancel(self):
        res = super(StockPicking, self).action_cancel()

        for picking in self:
            if picking.stock_request_id and picking.state == 'cancel':
                picking.stock_request_id._process_picking_cancel(picking)

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