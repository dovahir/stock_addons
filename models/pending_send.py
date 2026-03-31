from odoo import fields, models, api, _
from odoo.exceptions import UserError

class PendingSend(models.Model):
    _inherit = 'stock.move'

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

    # Metodo que "filtra" o determina si un producto debe mostrarse en la vista
    @api.depends('state', 'picking_code', 'stock_request_line_id')
    def _compute_is_pending_send(self):
        for move in self:
            # Si el movimiento fue generado desde una solicitud de stock, no se muestra
            if move.stock_request_line_id:
                move.is_pending_send = False
                continue
            if (move.state not in ('draft', 'done', 'cancel') and
                move.picking_code in ('outgoing', 'internal')):
                move.is_pending_send = True
            else:
                move.is_pending_send = False

    # Calcula la cantidad de un producto pendiente por enviar
    @api.depends('product_uom_qty', 'quantity')
    def _compute_remaining(self):
        for move in self:
            move.remaining_qty = move.product_uom_qty - move.quantity

################ Metodos para stock_request desde pending_send #########################################

    # Boton que agrega los productos seleccionados a un stock_request
    def action_new_stock_request(self):
        if not self:
            raise UserError(_("No hay movimientos seleccionados."))

        # Validar que todos los movimientos sean de tipo interno (traslado)
        invalid_moves = self.filtered(lambda m: m.picking_type_id.code != 'internal')
        if invalid_moves:
            raise UserError(_("Solo se pueden agregar traslados internos. Los siguientes movimientos no lo son: \n%s")
                            % '\n'.join(invalid_moves.mapped('name')))

        # Tomar el primer movimiento para datos del form
        first = self[0]

        # Almacén del primer movimiento
        warehouse = first.location_id.warehouse_id

        # Obtener la ubicación por defecto del almacén
        location = warehouse.lot_stock_id

        # Obtener un tipo de operación interno asociado a este almacén
        picking_type = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', warehouse.id),
            ('code', '=', 'internal')
        ], limit=1)

        if not picking_type:
            raise UserError(_("No hay tipos de operación internos configurados."))

        # Crear la solicitud
        Request = self.env['stock.request']
        request = Request.create({
            # 'name': _('New'),
            'warehouse_id': warehouse.id,
            'location_id': location.id,
            'location_dest_id': location.id,  # inicialmente mismo destino
            'picking_type_id': picking_type.id,
            'picking_type_dest_id': picking_type.id,
        })

        # Agregar líneas al stock_request
        for move in self:
            qty_pending = move.product_uom_qty - move.quantity
            if qty_pending <= 0:
                continue

            # Buscar si ya existe línea con mismo producto
            line = request.line_ids.filtered(lambda l: l.product_id == move.product_id)
            if line: # Si lo hay, lo suma
                line.product_qty += qty_pending
            else: # Si no, lo crea y asigna valor a sus campos
                request.line_ids.create({
                    'request_id': request.id,
                    'product_id': move.product_id.id,
                    'product_qty': qty_pending,
                    'product_uom_id': move.product_uom.id,
                    'name': move.product_id.display_name,
                    'project_id': move.project_id.id if move.project_id else False,
                    'task_id': move.task_id.id if move.task_id else False,
                    # 'analytic_distribution': move.analytic_distribution,
                    'requisition_id': move.picking_id.requisition_id2.id if hasattr(move, 'requisition_id') else False,
                    'source_move_id': move.id,
                })
        # Abrir la solicitud recién creada
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nueva Solicitud'),
            'res_model': 'stock.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # Abre un wizard para seleccionar una solicitud existente y agregar los stock.move.
    def action_existing_stock_request(self):
        if not self:
            raise UserError(_("No hay movimientos seleccionados."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Seleccionar Solicitud'),
            'res_model': 'stock.request.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_ids': [(6, 0, self.ids)],  # guardar los movimientos seleccionados
            },
        }