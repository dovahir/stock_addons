from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError


class RequiToStockRequestWizard(models.TransientModel):
    _name = 'requi.stock.request.wizard'
    _description = 'Wizard para transferir líneas de la requisición a una stock_request nueva'

    # Relacion con la requisición de origen
    requisition_id = fields.Many2one(
        comodel_name='employee.purchase.requisition',
        string='Requisición',
        required=True
    )

    # Lineas que se muestran en la tabla del wizard para seleccionar
    line_ids = fields.One2many(
        comodel_name='requi.stock.request.wizard.line',
        inverse_name='wizard_id',
        string='Líneas de requisición'
    )

    has_requests = fields.Boolean(compute='_compute_has_requests')

    def _compute_has_requests(self):
        for wizard in self:
            if wizard.requisition_id:
                location = wizard.requisition_id.location_id
                count = self.env['stock.request'].search_count([
                    ('state', 'in', ['draft', 'confirm']),
                    ('location_dest_id', '=', location.id)
                ])
                wizard.has_requests = count > 0
            else:
                wizard.has_requests = False

    # metodo para crear un stock_request con las líneas seleccionadas
    def action_create_stock_request(self):
        self.ensure_one()

        # Filtra solo las líneas marcadas
        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_('Debe seleccionar al menos una línea.'))

        # Validar que las cantidades no excedan la original de la requisición
        for line in selected_lines:
            if line.product_qty > line.requisition_line_id.quantity:
                raise UserError(_(
                    'La cantidad solicitada para el producto "%s" (%s) excede la cantidad original de la requisición (%s).'
                ) % (line.product_id.display_name, line.product_qty, line.requisition_line_id.quantity))

        # Verificacion para no pedir mas cantidad que la disponible en almacén
        # for line in selected_lines:
        #     if line.product_qty > line.available_qty:
        #         raise UserError(_(
        #             'La cantidad solicitada para "%s" (%s) supera la cantidad disponible en el almacén destino (%s).'
        #         ) % (line.product_id.display_name, line.product_qty, line.available_qty))

        # Usar el almacén base como origen predeterminado
        warehouse_default = self.env['stock.warehouse'].search([('name', 'ilike', 'base')], limit=1)
        if not warehouse_default:
            raise UserError(_('No se encontró el almacén "Base".'))

        # Buscar el tipo de operación interna para ese almacén
        picking_type = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', warehouse_default.id),
            ('code', '=', 'internal'),
            ('name', 'ilike', 'enviar')
        ], limit=1)
        if not picking_type:
            raise UserError(
                _('No hay tipo de operación interno configurado para el almacén %s') % warehouse_default.name)

        # Usamos los campos de la requi para almacen y destino
        req = self.requisition_id
        warehouse_dest_default = req.warehouse_id
        location_dest_default = req.location_id

        # Buscar el tipo de operación interna para ese almacén
        picking_type_dest = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', warehouse_dest_default.id),
            ('code', '=', 'incoming'),
            ('name', 'ilike', 'recepcion')  # Que el nombre coincida con recepcion
        ], limit=1)
        if not picking_type_dest:
            raise UserError(
                _('No hay tipo de operación interno configurado para el almacén %s') % warehouse_dest_default.name)

        # Creación del form stock_request
        stock_request = self.env['stock.request'].create({
            'warehouse_id': warehouse_default.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': location_dest_default.id,
            'picking_type_id': picking_type.id,
            'picking_type_dest_id': picking_type_dest.id,
            'scheduled_date': fields.Datetime.now(),
            'requisition_ids': [(4, self.requisition_id.id)],  # Relación con las requisiciones (Many2Many)
        })

        # Agregar cada línea seleccionada a la solicitud creada
        for line in selected_lines:
            self.add_line_to_request(stock_request, line) # Llamamos otro metodo para esto

        # Retornar la vista de la nueva solicitud creada
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitud de Stock'),
            'res_model': 'stock.request',
            'res_id': stock_request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # Metodo para insertar líneas evitando duplicados (suma cantidades)
    def add_line_to_request(self, stock_request, wizard_line):
        existing = stock_request.line_ids.filtered(lambda l:
                                                   l.product_id == wizard_line.product_id and
                                                   l.product_uom_id == wizard_line.uom_id
                                                   )

        if existing:
            # Si el producto ya existe en el documento, se suma la cantidad
            existing.product_qty += wizard_line.product_qty
        else:
            # Si no existe, se crea una línea nueva
            self.env['stock.request.line'].create({
                'request_id': stock_request.id,
                'requester_name': wizard_line.requisition_line_id.requisition_product_id.employee_id.sudo().name,
                'product_id': wizard_line.product_id.id,
                'product_qty': wizard_line.product_qty,
                'product_uom_id': wizard_line.uom_id.id,
                'name': wizard_line.product_id.display_name,
                'note' : wizard_line.note,
                'requisition_line_id': wizard_line.requisition_line_id.id,
                'is_manual': False,
            })

    # Boton para redirigir a otro wizard y elegir una solicitud ya existente
    def action_add_to_existing_request(self):
        self.ensure_one()

        selected_lines = self.line_ids.filtered('selected')

        if not selected_lines:
            raise UserError(_('Debe seleccionar al menos una línea.'))

        for line in selected_lines:
            if line.product_qty <= 0:
                raise UserError(_("La cantidad del producto no puede ser 0.\n"
                                  'Producto: "%s"')
                                % line.product_id.display_name)
            # Validar que las cantidades no excedan la original de la requisición
            if line.product_qty > line.requisition_line_id.quantity:
                raise UserError(_(
                    'La cantidad solicitada para el producto "%s" (%s) excede la cantidad original de la requisición (%s).'
                ) % (line.product_id.display_name, line.product_qty, line.requisition_line_id.quantity))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Seleccionar Solicitud Existente'),
            'res_model': 'request.selection.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_requisition_id': self.requisition_id.id,
                'default_wizard_line_ids': [(6, 0, selected_lines.ids)],
            }
        }

class RequiStockRequestWizardLine(models.TransientModel):
    _name = 'requi.stock.request.wizard.line'
    _description = 'Línea del wizard para transferir de requisición a stock_request'

    wizard_id = fields.Many2one('requi.stock.request.wizard')
    requisition_line_id = fields.Many2one(comodel_name='requisition.order', string='Línea de requisición')
    selected = fields.Boolean(string='Seleccionar', default=False) # Checkbox
    product_id = fields.Many2one(comodel_name='product.product', string='Producto')
    requisition_qty = fields.Float(string='Cantidad requerida', readonly=True,
                                   related='requisition_line_id.quantity')
    available_qty = fields.Float(string='Disponible en destino', readonly=True,
                                 compute='_compute_available_qty')
    product_qty = fields.Float(string='Cantidad')
    uom_id = fields.Many2one(comodel_name='uom.uom', string='Unidad')
    note = fields.Char(string='Notas')

    def _compute_available_qty(self):
        for line in self:
            qty = 0.0
            requisition = line.wizard_id.requisition_id
            if requisition and line.product_id and requisition.warehouse_id:
                # Ubicación de existencias del almacén destino
                stock_location = requisition.warehouse_id.lot_stock_id
                if stock_location:
                    product = line.product_id.with_context(location=stock_location.id)
                    # product.free_qty para disponible real, descontando reservas
                    # usar product.qty_available para disponibles sin contar reservas
                    qty = product.qty_available
            line.available_qty = qty

class PurchaseRequisitionExt(models.Model):
    _inherit = 'employee.purchase.requisition'

    # Metodo que lanza el wizard y lo pre-carga de datos
    def action_open_stock_request_wizard(self):
        self.ensure_one()

        # Crea el registro del wizard y sus líneas segun los datos de la requisicion
        wizard = self.env['requi.stock.request.wizard'].create({
            'requisition_id': self.id,
            'line_ids': [(0, 0, {
                'requisition_line_id': line.id,
                'selected': False,  # Inician desmarcadas por defecto
                'product_id': line.product_id.id,
                'product_qty': line.quantity,
                # 'product_qty': 0,
                'uom_id': line.product_id.uom_id.id,
                'note': line.note if line.note else False,
            }) for line in self.requisition_order_ids],
        })

        # Abre el wizard
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitud de Stock'),
            'res_model': 'requi.stock.request.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new', # Abre como ventana modal
        }