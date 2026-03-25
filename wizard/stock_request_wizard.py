from odoo import fields, models, api, _
from odoo.exceptions import UserError

class StockRequestWizard(models.TransientModel):
    _name = 'stock.request.wizard'
    _description = 'Wizard para agregar movimientos a solicitud existente'

    request_id = fields.Many2one('stock.request',
                                 string='Solicitud',
                                 required=True,
                                 domain=[('state', 'not in', ('validate', 'cancel'))])
    move_ids = fields.Many2many('stock.move', string='Movimientos')

    requisition_line_ids = fields.Many2many(
        'requisition.wizard.line',
        string='Líneas de requisición')

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
            line = self.request_id.line_stock_ids.filtered(lambda l: l.product_id == move.product_id)
            if line:
                line.product_qty += qty_pending
            else:
                self.request_id.line_stock_ids.create({
                    'request_id': self.request_id.id,
                    'product_id': move.product_id.id,
                    'product_qty': qty_pending,
                    'product_uom_id': move.product_uom.id,
                    'name': move.product_id.display_name,
                    'source_move_id': move.id,
                })

        # --- Procesar líneas de requisición (requisition.wizard.line) ---
        for line in self.requisition_line_ids:
            if line.quantity <= 0:
                continue

            # Buscar línea existente con el mismo producto
            existing_line = self.request_id.line_stock_ids.filtered(
                lambda l: l.product_id == line.product_id
            )
            if existing_line:
                existing_line.product_qty += line.quantity
            else:
                self.request_id.line_stock_ids.create({
                    'request_id': self.request_id.id,
                    'product_id': line.product_id.id,
                    'product_qty': line.quantity,
                    'product_uom_id': line.uom_id.id,
                    'name': line.product_id.display_name,
                    # Copiar proyecto/tarea desde la requisición original,
                    # Acceder a ella a través de self.requisition_id (si la tienes en el contexto)
                    # o a través de un campo relacionado en line.
                    # Por simplicidad, dejamos False
                    'project_id': False,
                    'task_id': False,
                })

        return {'type': 'ir.actions.act_window_close'}
