from odoo import fields, models, api, _
from odoo.exceptions import UserError

class StockRequestWizard(models.TransientModel):
    _name = 'stock.request.wizard'
    _description = 'Wizard para agregar movimientos a solicitud existente desde vista pending_send'

    request_id = fields.Many2one(comodel_name='stock.request',
                                 string='Solicitud',
                                 required=True,
                                 domain=[('state', 'not in', ('validate', 'cancel'))])

    move_ids = fields.Many2many(comodel_name='stock.move', string='Movimientos')

    # Boton que añade los movimientos seleccionados en un stock_request existente
    def action_add_moves(self):
        self.ensure_one()

        # Validar que todos los movimientos sean de tipo interno (traslado)
        invalid_moves = self.move_ids.filtered(lambda m: m.picking_type_id.code != 'internal')
        if invalid_moves:
            raise UserError(_("Solo se pueden agregar traslados internos. Los siguientes movimientos no lo son: \n%s")
                            % '\n'.join(invalid_moves.mapped('name')))

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
                    # 'analytic_distribution': move.analytic_distribution,
                    # 'project_id': move.project_id.id if move.project_id else False,
                    # 'task_id': move.task_id.id if move.task_id else False,
                    'requisition_id': move.picking_id.requisition_id2.id if hasattr(move, 'requisition_id') else False,
                    'source_move_id': move.id,
                })

        return {'type': 'ir.actions.act_window_close'}
