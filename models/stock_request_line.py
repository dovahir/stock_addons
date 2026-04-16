from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

# Clase para los campos de las lineas de stock_request
class StockRequestLine(models.Model):
    _name = "stock.request.line"
    _inherit = ['mail.thread', 'mail.activity.mixin', "analytic.mixin"]
    _rec_name = "product_id"
    _description = "Stock Request List"

    # Ligado a un stock_request
    request_id = fields.Many2one(string="Solicitud", required=True, ondelete='cascade',
                                 comodel_name="stock.request")

    is_manual = fields.Boolean(string='Manual', default=False)
    # Ligas para la requisicion
    requisition_line_id = fields.Many2one(comodel_name='requisition.order', string='Línea de requisición origen')
    requisition_id = fields.Many2one(comodel_name='employee.purchase.requisition', string='Requisición origen',
                                     related='requisition_line_id.requisition_product_id', store=True)

    requisition_deadline = fields.Date(
        string='Fecha de entrega',
        related='requisition_line_id.requisition_product_id.requisition_deadline',
        store=True,
        help='Fecha de entrega de la requisición origen'
    )

    # Campos principales
    product_id = fields.Many2one(comodel_name="product.product", string="Producto", required=True)
    name = fields.Char('Descripción')
    product_qty = fields.Float(string="Cantidad", digits='Product Unit of Measure', default=1.0)
    product_uom_id = fields.Many2one(comodel_name="uom.uom", string="UoM", required=True)
    source_move_id = fields.Many2one(comodel_name='stock.move', string='Movimiento origen', readonly=True)
    note = fields.Char(string='Notas')
    # Solicitante
    requester_name = fields.Char(string='Solicitado por', readonly=True)

    # Campo para que el usuario elija las series
    lot_ids = fields.Many2many(
        comodel_name='stock.lot',
        string='Números de Serie',
        domain="[('product_id', '=', product_id), ('location_id', '=', parent.location_id)]"
    )

    # Para saber si el producto requiere serie sin tener que adivinar
    has_tracking = fields.Selection(related='product_id.tracking')

    @api.constrains('lot_ids', 'product_qty')
    def _check_lots_quantity(self):
        for line in self:
            if line.has_tracking == 'serial' and len(line.lot_ids) != line.product_qty:
                raise UserError("Para el producto %s, debe seleccionar exactamente %s números de serie."
                                % (line.product_id.display_name, line.product_qty))

    @api.constrains('product_qty')
    def _check_quantity(self):
        for rec in self:
            if rec.product_qty <= 0:
                raise ValidationError(_("La cantidad del producto debe ser mayor a cero"))

    @api.onchange("product_id")
    def _onchange_product(self):
        for rec in self:
            if rec.product_id:
                rec.product_uom_id = rec.product_id.uom_id.id
                rec.name = rec.product_id.display_name

    @api.model_create_multi
    def create(self, vals_list):
        updated_vals_list = []
        for vals in vals_list:
            request_id = vals.get('request_id')
            product_id = vals.get('product_id')
            qty = vals.get('product_qty', 0.0)
            requisition_line_id = vals.get('requisition_line_id')  # ID de la línea de requisición origen

            # Buscar línea existente que sea "compatible" para fusionar
            # Solo fusionar si:
            # - Tienen el mismo request_id y product_id
            # - Y ambas tienen el mismo requisition_line_id (o ambas son None)
            domain = [
                ('request_id', '=', request_id),
                ('product_id', '=', product_id)
            ]
            if requisition_line_id:
                domain.append(('requisition_line_id', '=', requisition_line_id))
            else:
                domain.append(('requisition_line_id', '=', False))

            existing = self.search(domain, limit=1)

            if existing:
                # Sumar cantidad a la línea existente
                existing.product_qty += qty
                # Actualizar otros campos si se proporcionan (ej. unidad de medida)
                if 'product_uom_id' in vals:
                    existing.product_uom_id = vals['product_uom_id']
                if 'name' in vals:
                    existing.name = vals['name']
                # No agregar esta línea a la lista de creación
                continue

            # Si no existe línea compatible, crear una nueva
            updated_vals_list.append(vals)

        records = super().create(updated_vals_list)
        # Sincronizar las solicitudes padre (para actualizar el campo requisition_ids)
        records.mapped('request_id')._sync_requisition_ids()
        return records

    def unlink(self):
        requests = self.mapped('request_id')
        res = super().unlink()
        requests._sync_requisition_ids()
        return res

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if 'requester_name' in fields and not res.get('requester_name'):
            res['requester_name'] = self.env.user.name

        return res

