from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError

class RequestSelectionWizard(models.TransientModel):
    _name = 'request.selection.wizard'
    _description = 'Seleccionar solicitud de stock existente'

    requisition_id = fields.Many2one('employee.purchase.requisition', required=True)
    wizard_line_ids = fields.Many2many('requi.stock.request.wizard.line', string='Líneas a transferir')
    stock_request_id = fields.Many2one('stock.request', string='Solicitud de stock', required=True,
                                       domain="[('state', 'in', ['draft', 'confirm'])]")

    def action_add_to_request(self):
        self.ensure_one()
        req = self.requisition_id
        stock_request = self.stock_request_id

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
                    # 'analytic_distribution': line.analytic_distribution,
                    'requisition_line_id': line.requisition_line_id.id,
                    'note': line.note if line.note else False,
                })
        return {'type': 'ir.actions.act_window_close'}