from odoo import fields, models, api, _
from odoo.exceptions import UserError

class ReplenishmentWizard(models.TransientModel):
    _name = 'replenishment.wizard'
    _description = 'Reabastecer productos desde Base'

    purchase_order_id = fields.Many2one(
        comodel_name='purchase.order',
        string='Cotización existente',
        domain="[('state', 'in', ['draft', 'sent'])]"
    )
    line_ids = fields.One2many(
        comodel_name='replenishment.wizard.line',
        inverse_name='wizard_id',
        string='Productos'
    )

    def action_add_to_order(self):
        self.ensure_one()
        order = self.purchase_order_id
        if not order:
            raise UserError(_('Debe seleccionar una cotización existente.'))

        lines = self.line_ids.filtered(lambda l: l.product_qty > 0)
        if not lines:
            raise UserError(_('Ingrese una cantidad mayor a 0 en al menos un producto.'))

        for line in lines:
            existing = order.order_line.filtered(lambda ol: ol.product_id == line.product_id)
            if existing:
                # Si el producto ya está en la orden, suma la cantidad a la primera línea encontrada
                existing[0].product_qty += line.product_qty
            else:
                self.env['purchase.order.line'].create({
                    'order_id': order.id,
                    'product_id': line.product_id.id,
                    'product_qty': line.product_qty,
                    'product_uom': line.uom_id.id,
                    'note': line.note or '',
                })

        order.message_post(body=_("Se agregaron productos desde Reabastecimiento Manual."))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Completado'),
                'message': _('Productos agregados a la cotización %s.') % order.name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

class ReplenishmentWizardLine(models.TransientModel):
    _name = 'replenishment.wizard.line'
    _description = 'Línea de reabastecimiento'

    wizard_id = fields.Many2one('replenishment.wizard')
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    product_qty = fields.Float(string='Cantidad a solicitar', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unidad', readonly=True)
    note = fields.Char(string='Notas')