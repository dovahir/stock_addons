from odoo import fields, models, api, _
from odoo.exceptions import UserError

class PendingSend(models.Model):
    _inherit = 'stock.move'

    # picking_name = fields.Char(related='picking_id.picking_type_id.name', readonly=True)
    project_id = fields.Many2one('project.project', string='Proyecto', index=True, copy=False)
    task_id = fields.Many2one('project.task', string='Tarea', index=True, copy=False)
    requisition_id = fields.Many2one(related='picking_id.requisition_id2', store=True)
    
    is_pending_send = fields.Boolean(
        string='Pendiente de envío',
        compute='_compute_is_pending_send',
        store=True,
        index=True,
    )

    remaining_qty = fields.Float(
        string='Pendiente',
        compute='_compute_remaining',
        store=False,
        digits='Product Unit of Measure'
    )

    @api.depends('state', 'picking_code')
    def _compute_is_pending_send(self):
        for move in self:
            if (move.state not in ('draft', 'done', 'cancel') and
                move.picking_code in ('outgoing', 'internal')):
                move.is_pending_send = True
            else:
                move.is_pending_send = False

    @api.depends('product_uom_qty', 'quantity')
    def _compute_remaining(self):
        for move in self:
            move.remaining_qty = move.product_uom_qty - move.quantity

    def action_new_stock_request(self):
        """Crea una nueva solicitud de stock con los movimientos seleccionados."""
        if not self:
            raise UserError(_("No hay movimientos seleccionados."))
        # Tomar el primer movimiento para datos de cabecera (puedes ajustar según lógica)
        first = self[0]
        # Crear la solicitud
        Request = self.env['hrl.stock.request']
        request = Request.create({
            'name': _('New'),
            'warehouse_id': first.location_id.warehouse_id.id,
            'location_id': first.location_id.id,
            'location_dest_id': first.location_dest_id.id,
            'picking_type_id': first.picking_type_id.id,
            'picking_type_dest_id': first.picking_type_id.id,  # o según corresponda
        })
        # Agregar líneas
        for move in self:
            qty_pending = move.product_uom_qty - move.quantity
            if qty_pending <= 0:
                continue
            # Buscar si ya existe línea con mismo producto
            line = request.line_ids.filtered(lambda l: l.product_id == move.product_id)
            if line:
                line.product_qty += qty_pending
            else:
                request.line_ids.create({
                    'request_id': request.id,
                    'product_id': move.product_id.id,
                    'product_qty': qty_pending,
                    'product_uom_id': move.product_uom.id,
                    'name': move.product_id.display_name,
                })
        # Abrir la solicitud recién creada
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nueva Solicitud'),
            'res_model': 'hrl.stock.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_existing_stock_request(self):
        """Abre un wizard para seleccionar una solicitud existente y agregar los movimientos."""
        if not self:
            raise UserError(_("No hay movimientos seleccionados."))
        # Llamar al wizard (lo definiremos después)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Seleccionar Solicitud'),
            'res_model': 'hrl.stock.request.wizard',  # nombre del wizard
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_ids': [(6, 0, self.ids)],  # guardar los movimientos seleccionados
            },
        }