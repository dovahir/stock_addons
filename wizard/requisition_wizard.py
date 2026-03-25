from odoo import fields, models, api, _
from odoo.exceptions import UserError

class RequisitionWizard(models.TransientModel):
    _name = 'requisition.wizard'
    _description = 'Wizard para enviar líneas de requisición a Stock Request'

    requisition_id = fields.Many2one('employee.purchase.requisition', string='Requisición', required=True)
    line_ids = fields.One2many('requisition.wizard.line', 'wizard_id', string='Líneas')

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            requisition = self.env['employee.purchase.requisition'].browse(active_id)
            res['requisition_id'] = requisition.id
            lines = []
            for line in requisition.requisition_order_ids:
                lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                    'uom_id': line.product_id.uom_id.id,
                    'selected': False,
                }))
            res['line_ids'] = lines
        return res

    def action_create_new_stock_request(self):
        """Crea un nuevo Stock Request con las líneas seleccionadas"""
        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_("No has seleccionado ninguna línea."))

        # Obtener valores por defecto para la nueva solicitud
        company = self.env.company
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
        if not warehouse:
            raise UserError(_("No hay almacenes configurados para la compañía."))
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id)
        ], limit=1)
        if not picking_type:
            picking_type = self.env['stock.picking.type'].search([('code', '=', 'internal')], limit=1)
            if not picking_type:
                raise UserError(_("No hay tipo de operación interno configurado."))

        Request = self.env['stock.request']
        request = Request.create({
            'name': _('New'),
            'warehouse_id': warehouse.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': warehouse.lot_stock_id.id,
            'picking_type_id': picking_type.id,
            'picking_type_dest_id': picking_type.id,
        })

        # Agregar líneas de stock request
        for line in selected_lines:
            request.line_stock_ids.create({
                'request_id': request.id,
                'product_id': line.product_id.id,
                'product_qty': line.quantity,
                'product_uom_id': line.uom_id.id,
                'name': line.product_id.display_name,
                'project_id': self.requisition_id.project_id.id if self.requisition_id.project_id else False,
                'task_id': self.requisition_id.task_id.id if self.requisition_id.task_id else False,
            })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Nuevo Stock Request'),
            'res_model': 'stock.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_add_to_existing_stock_request(self):
        """Abre el wizard para seleccionar un stock request existente"""
        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_("No has seleccionado ninguna línea."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Seleccionar Stock Request'),
            'res_model': 'stock.request.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_requisition_line_ids': [(6, 0, selected_lines.ids)],
            },
        }


class RequisitionWizardLine(models.TransientModel):
    _name = 'requisition.wizard.line'
    _description = 'Línea del wizard de requisición a stock request'

    wizard_id = fields.Many2one('requisition.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    quantity = fields.Float(string='Cantidad', digits='Product Unit of Measure', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unidad', required=True)
    selected = fields.Boolean(string='Seleccionar', default=False)