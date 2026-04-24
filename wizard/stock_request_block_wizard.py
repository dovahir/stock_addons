from odoo import models, fields, api, _

class StockRequestBlockWizard(models.TransientModel):
    _name = 'stock.request.block.wizard'
    _description = 'Ocultar solicitud de suministro'

    request_id = fields.Many2one(comodel_name='stock.request', string='Solicitud', required=True, default=lambda self: self.env.context.get('active_id'))
    create_new = fields.Boolean(string='¿Crear nueva solicitud?', default=False)
    scheduled_date = fields.Datetime(string='Fecha de entrega', required=False)

    @api.onchange('create_new')
    def _onchange_create_new(self):
        self.scheduled_date = False if not self.create_new else self.scheduled_date

    def action_confirm(self):
        self.ensure_one()
        request = self.request_id

        # Bloquear la solicitud actual
        request.write({'is_blocked': True})
        new_name = ''

        # Si se solicita crear una nueva
        if self.create_new:
            vals = {
                'picking_type_id': request.picking_type_id.id,
                'location_id': request.location_id.id,
                'location_dest_id': request.location_dest_id.id,
                'warehouse_id': request.warehouse_id.id,
                'picking_type_dest_id': request.picking_type_dest_id.id,
                'company_id': request.company_id.id,
                'scheduled_date': self.scheduled_date or fields.Datetime.now(),
                'state': 'draft',
                'is_blocked': False,
                'requisition_ids': [(5, 0, 0)],
                'line_ids': [(5, 0, 0)],
                'name': self.env['ir.sequence'].next_by_code('stock.request') or _('Nueva solicitud'),
            }
            new_request = self.env['stock.request'].create(vals)
            new_name = new_request.name

        # Notificación y recarga de la vista actual
        notification = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Solicitud bloqueada'),
                'message': _('La solicitud %s ha sido ocultada.') % request.name + (
                    (' Se ha creado la nueva solicitud %s.' % new_name) if self.create_new else ''),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
        return notification