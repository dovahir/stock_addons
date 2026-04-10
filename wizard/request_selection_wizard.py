from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError

class RequestSelectionWizard(models.TransientModel):
    _name = 'request.selection.wizard'
    _description = 'Seleccionar solicitud de suministros existente para requisiciones'

    requisition_id = fields.Many2one(comodel_name='employee.purchase.requisition', required=True)
    wizard_line_ids = fields.Many2many(comodel_name='requi.stock.request.wizard.line', string='Líneas a transferir')

    request_date = fields.Datetime(string='Fecha de la solicitud',
                                          related="stock_request_id.request_date")

    scheduled_date = fields.Datetime(string='Fecha de entrega',
                                     related="stock_request_id.scheduled_date")

    state = fields.Selection(string='Estado de solicitud', related="stock_request_id.state")

    stock_request_id = fields.Many2one(comodel_name='stock.request', string='Solicitud de stock', required=True)

    # Campo auxiliar para guardar la ubicación de la requisición
    location_id = fields.Many2one(comodel_name='stock.location', string='Ubicación')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        req_id = self.env.context.get('default_requisition_id')

        if req_id:
            requisition = self.env['employee.purchase.requisition'].browse(req_id)
            if requisition:
                # Guardamos la ubicación en el wizard para el dominio del XML
                res['location_id'] = requisition.location_id.id

                # Buscamos el registro por defecto
                domain = [
                    ('state', 'in', ['draft', 'confirm']),
                    ('location_dest_id', '=', requisition.location_id.id)
                ]
                eligible = self.env['stock.request'].search(domain, order='create_date desc', limit=1)
                if eligible:
                    res['stock_request_id'] = eligible.id
        return res

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
            raise UserError(_("La ubicación destino de la solicitud (%s) no coincide con la de la requisición (%s).\n"
                              "Elija una solicitud que tenga como destino (%s)")
                            % (stock_request.location_dest_id.display_name,
                               req.location_id.display_name,
                               req.location_id.display_name))
        if stock_request.warehouse_dest_id != req.warehouse_id:
            raise UserError(_("El almacén destino de la solicitud (%s) no coincide con el de la requisición (%s).\n"
                              "Elija una solicitud que tenga como destino (%s)")
                            % (stock_request.warehouse_dest_id.display_name,
                               req.warehouse_id.display_name,
                               req.warehouse_id.display_name))

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
                    'requester_name': line.requisition_line_id.requisition_product_id.employee_id.name,
                    'product_id': line.product_id.id,
                    'product_qty': line.product_qty,
                    'product_uom_id': line.uom_id.id,
                    'name': line.product_id.display_name,
                    'requisition_line_id': line.requisition_line_id.id,
                    'note': line.note if line.note else False,
                })
        return {'type': 'ir.actions.act_window_close'}