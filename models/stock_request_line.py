from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

# Clase para los campos de las lineas de stock_request
class StockRequestLine(models.Model):
    _name = "stock.request.line"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = "product_id"
    _description = "Stock Request List"

    # Ligado a un stock_request
    request_id = fields.Many2one(
        comodel_name="stock.request",
        string="Solicitud",
        required=True,
        ondelete='cascade'
    )

    # Ligas para la requisicion
    requisition_line_id = fields.Many2one(comodel_name='requisition.order', string='Línea de requisición origen')
    requisition_id = fields.Many2one(comodel_name='employee.purchase.requisition', string='Requisición origen',
                                     related='requisition_line_id.requisition_product_id', store=True)

    # Campos principales
    product_id = fields.Many2one(comodel_name="product.product", string="Producto", required=True)
    name = fields.Char('Descripción')
    project_id = fields.Many2one(comodel_name='project.project', string='Proyecto')
    task_id = fields.Many2one(comodel_name='project.task', string='Tarea')
    product_qty = fields.Float(string="Cantidad", digits='Product Unit of Measure', default=1.0)
    product_uom_id = fields.Many2one(comodel_name="uom.uom", string="UoM", required=True)
    # analytic_distribution = fields.Json(string='Distribución analítica')
    source_move_id = fields.Many2one(comodel_name='stock.move', string='Movimiento origen', readonly=True)

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
        # Evita duplicados: si ya existe una línea con el mismo producto en la misma solicitud,
        # suma la cantidad a la línea existente en lugar de crear una nueva.
        updated_vals_list = []
        for vals in vals_list:
            request_id = vals.get('request_id')
            product_id = vals.get('product_id')
            qty = vals.get('product_qty', 0.0)

            # Solo buscar si tenemos los datos necesarios
            if request_id and product_id and qty:
                # Buscar línea existente en la misma solicitud
                existing = self.search([
                    ('request_id', '=', request_id),
                    ('product_id', '=', product_id)
                ], limit=1)

                if existing:
                    # Sumar la nueva cantidad a la línea existente
                    existing.product_qty += qty

                    # Actualizar otros campos si se proporcionan (ej. unidad de medida)
                    if 'product_uom_id' in vals:
                        existing.product_uom_id = vals['product_uom_id']
                    if 'name' in vals:
                        existing.name = vals['name']

                    # No agregar esta línea a la lista de creación
                    continue

            # Si no existía, o no se pudo sumar, proceder con la creación normal
            updated_vals_list.append(vals)

        return super().create(updated_vals_list)
