from odoo import fields, models, api

class PendingSend(models.Model):
    _inherit = 'stock.move'

    # picking_name = fields.Char(related='picking_id.picking_type_id.name', readonly=True)
    project_id = fields.Many2one('project.project', string='Proyecto', index=True, copy=False)
    task_id = fields.Many2one('project.task', string='Tarea', index=True, copy=False)

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