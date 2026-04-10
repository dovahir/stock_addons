from odoo import fields, models, api, _
from odoo.exceptions import UserError

class PendingSend(models.Model):
    _inherit = 'stock.move'

    project_id = fields.Many2one(comodel_name='project.project', string='Proyecto', index=True, copy=False)
    task_id = fields.Many2one(comodel_name='project.task', string='Tarea', index=True, copy=False)
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

