from odoo import fields, models, api, _
from odoo.exceptions import UserError

class PendingSend(models.Model):
    _inherit = 'stock.move'

    project_id = fields.Many2one(comodel_name='project.project', string='Proyecto', index=True, copy=False)
    task_id = fields.Many2one(comodel_name='project.task', string='Tarea', index=True, copy=False)
    requisition_id = fields.Many2one(related='picking_id.requisition_id2', store=True)

    remaining_qty = fields.Float(
        string='Pendiente',
        compute='_compute_remaining',
        store=False,
        digits='Product Unit of Measure'
    )

    # Calcula la cantidad de un producto pendiente por enviar
    @api.depends('product_uom_qty', 'quantity')
    def _compute_remaining(self):
        for move in self:
            move.remaining_qty = move.product_uom_qty - move.quantity

