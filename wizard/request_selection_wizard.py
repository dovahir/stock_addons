from zeep.xsd import default_types

from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError

class RequestSelectionWizard(models.TransientModel):
    _name = 'request.selection.wizard'
    _description = 'Seleccionar solicitud de suministros existente para requisiciones'

    requisition_id = fields.Many2one(comodel_name='employee.purchase.requisition', required=True)
    wizard_line_ids = fields.Many2many(comodel_name='requi.stock.request.wizard.line', string='Líneas a transferir')
    stock_request_id = fields.Many2one(comodel_name='stock.request',
                                       string='Solicitud de stock', required=True,
                                       domain="[('state', 'in', ['draft', 'confirm'])]",
                                       default=lambda self: self._get_lastest_stock_request()
                                       )

    request_date = fields.Datetime(string='Fecha de la solicitud',
                                          related="stock_request_id.request_date")

    scheduled_date = fields.Datetime(string='Fecha de entrega',
                                     related="stock_request_id.scheduled_date")

    state = fields.Selection(string='Estado actual', related="stock_request_id.state")

    def _get_lastest_stock_request(self):
        latest = self.env['stock.request'].search([], order='create_date desc', limit=1)
        return latest.id if latest else False

    def action_add_to_request(self):
        self.ensure_one()
        req = self.requisition_id
        stock_request = self.stock_request_id

        # Validar que esté en estado borrador o confirmado
        if stock_request.state not in ['draft', 'confirm']:
            raise UserError(_("Esta solicitud no es valida, seleccione solicitudes en estado borrador o confirmadas.\n"
                              "En caso de ser necesario, cree una nueva"))

        # Validar que las ubicaciones destino coincidan
        if stock_request.location_dest_id != req.location_id:
            raise UserError(_('La ubicación destino de la solicitud (%s) no coincide con la de la requisición (%s).')
                            % (stock_request.location_dest_id.display_name, req.location_id.display_name))
        if stock_request.warehouse_dest_id != req.warehouse_id:
            raise UserError(_('El almacén destino de la solicitud (%s) no coincide con el de la requisición (%s).')
                            % (stock_request.warehouse_dest_id.display_name, req.warehouse_id.display_name))

        # Agregar la requisición a la solicitud si aún no está
        if self.requisition_id not in stock_request.requisition_ids:
            stock_request.requisition_ids = [(4, self.requisition_id.id)]

        # Agregar líneas seleccionadas a la solicitud
        for line in self.wizard_line_ids:
            # Verificar si ya existe línea con mismo producto
            existing = stock_request.line_ids.filtered(lambda l: l.product_id == line.product_id)
            if existing:
                existing.product_qty += line.product_qty
            else:
                self.env['stock.request.line'].create({
                    'request_id': stock_request.id,
                    'product_id': line.product_id.id,
                    'product_qty': line.product_qty,
                    'product_uom_id': line.uom_id.id,
                    'name': line.product_id.display_name,
                    'project_id': line.project_id.id,
                    'task_id': line.task_id.id,
                    'analytic_distribution': line.analytic_distribution,
                    'requisition_line_id': line.requisition_line_id.id,
                    'note': line.note if line.note else False,
                })
        return {'type': 'ir.actions.act_window_close'}