from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError

class RequiStockRequestWizard(models.TransientModel):
    _name = 'requi.stock.request.wizard'
    _description = 'Wizard para transferir líneas de requisición a solicitud de stock'

    requisition_id = fields.Many2one(
        'employee.purchase.requisition',
        string='Requisición',
        required=True
    )

    line_ids = fields.One2many(
        'requi.stock.request.wizard.line',
        'wizard_id',
        string='Líneas de requisición'
    )

    def action_create_stock_request(self):
        self.ensure_one()

        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_('Debe seleccionar al menos una línea.'))

        req = self.requisition_id

        warehouse_dest = req.warehouse_id
        location_dest = req.location_id

        picking_type = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', warehouse_dest.id),
            ('code', '=', 'internal')
        ], limit=1)

        if not picking_type:
            raise UserError(_('No hay tipo de operación interno configurado para el almacén %s') % warehouse_dest.name)

        stock_request = self.env['stock.request'].create({
            'warehouse_id': warehouse_dest.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': location_dest.id,
            'picking_type_id': picking_type.id,
            'picking_type_dest_id': picking_type.id,
            'scheduled_date': fields.Datetime.now(),
            'requisition_ids': [(4, self.requisition_id.id)],
        })

        for line in selected_lines:
            self._add_line_to_request(stock_request, line)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitud de Stock'),
            'res_model': 'stock.request',
            'res_id': stock_request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _add_line_to_request(self, stock_request, wizard_line):
        existing = stock_request.line_ids.filtered(lambda l:
            l.product_id == wizard_line.product_id and
            l.product_uom_id == wizard_line.uom_id and
            l.project_id == wizard_line.project_id and
            l.task_id == wizard_line.task_id
        )

        if existing:
            existing.product_qty += wizard_line.product_qty
        else:
            self.env['stock.request.line'].create({
                'request_id': stock_request.id,
                'product_id': wizard_line.product_id.id,
                'product_qty': wizard_line.product_qty,
                'product_uom_id': wizard_line.uom_id.id,
                'name': wizard_line.product_id.display_name,
                'project_id': wizard_line.project_id.id,
                'task_id': wizard_line.task_id.id,
                'requisition_line_id': wizard_line.requisition_line_id.id,
            })


class RequiStockRequestWizardLine(models.TransientModel):
    _name = 'requi.stock.request.wizard.line'
    _description = 'Línea del wizard para transferir requisición'

    wizard_id = fields.Many2one('requi.stock.request.wizard')
    requisition_line_id = fields.Many2one('requisition.order', string='Línea de requisición')
    selected = fields.Boolean(string='Seleccionar', default=False)
    product_id = fields.Many2one('product.product', string='Producto')
    product_qty = fields.Float(string='Cantidad')
    uom_id = fields.Many2one('uom.uom', string='Unidad')
    project_id = fields.Many2one('project.project', string='Proyecto')
    task_id = fields.Many2one('project.task', string='Tarea')
    # analytic_distribution = fields.Json(string='Distribución analítica')

class PurchaseRequisitionExt(models.Model):
    _inherit = 'employee.purchase.requisition'

    def action_open_stock_request_wizard(self):
        self.ensure_one()

        # Pre-crear el wizard con sus líneas, quedan guardadas en DB
        wizard = self.env['requi.stock.request.wizard'].create({
            'requisition_id': self.id,
            'line_ids': [(0, 0, {
                'requisition_line_id': line.id,
                'product_id': line.product_id.id,
                'product_qty': line.quantity,
                'uom_id': line.product_id.uom_id.id,
                'project_id': line.project_id.id if line.project_id else False,
                'task_id': line.task_id.id if line.task_id else False,
                'selected': False,
            }) for line in self.requisition_order_ids],
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Crear Solicitud de Stock'),
            'res_model': 'requi.stock.request.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }