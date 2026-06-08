from odoo import models, api, _

class StockWarehouseOrderpoint(models.Model):
    _inherit = 'stock.warehouse.orderpoint'

    def action_replenish_wizard(self):
        """Abre el wizard de reabastecimiento con los productos seleccionados."""
        wizard = self.env['replenishment.wizard'].create({
            'line_ids': [(0, 0, {
                'product_id': rec.product_id.id,
                'uom_id': rec.product_uom.id or rec.product_id.uom_id.id,
            }) for rec in self]
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reabastecer productos'),
            'res_model': 'replenishment.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }