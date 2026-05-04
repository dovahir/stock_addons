from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date, format_datetime
from markupsafe import Markup

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
    request_qty = fields.Float(string='Demanda', related='requisition_line_id.quantity', readonly=True, store=True,
                               help='Cantidad solicitada en la requisición de origen')
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
        domain="[('product_id', '=', product_id), ('location_id.warehouse_id', '=', parent.warehouse_id)]"
    )

    # Para saber si el producto requiere num. serie
    has_tracking = fields.Selection(related='product_id.tracking')

    @api.constrains('lot_ids', 'product_qty')
    def _check_lots_quantity(self):
        for line in self:
            # Saltar validación si la línea viene de una requisición
            if line.requisition_line_id:
                continue

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
            requisition_line_id = vals.get('requisition_line_id') # ID de la línea de requisición origen
            lot_ids = vals.get('lot_ids', [])

            # Buscar línea existente que sea "compatible" para fusionar
            # Solo fusionar si:
            # - Tienen el mismo request_id y product_id
            # - Ambas tienen el mismo requisition_line_id (o ambas son NULL)
            domain = [('request_id', '=', request_id), ('product_id', '=', product_id)]
            if requisition_line_id:
                domain.append(('requisition_line_id', '=', requisition_line_id))
            else:
                domain.append(('requisition_line_id', '=', False))

            existing = self.search(domain, limit=1)

            if existing:
                # Verificar si el producto requiere series
                product = self.env['product.product'].browse(product_id)
                if product.tracking == 'serial':
                    # Extraer los IDs de los lotes que se están intentando agregar (si vienen en formato de comandos)
                    new_lot_ids = []
                    # Los lotes pueden venir como [(6,0,[ids])], [(4,id)], o lista de IDs
                    if isinstance(lot_ids, list):
                        for cmd in lot_ids:
                            if cmd[0] == 6:  # replace
                                new_lot_ids.extend(cmd[2])
                            elif cmd[0] == 4:  # add
                                new_lot_ids.append(cmd[1])
                            elif isinstance(cmd, int):
                                new_lot_ids.append(cmd)
                    else:
                        new_lot_ids = lot_ids if isinstance(lot_ids, list) else [lot_ids]
                    # Fusionar lotes: añadir los nuevos a los existentes
                    if new_lot_ids:
                        # Obtener los lotes existentes y agregar los nuevos (evitar duplicados)
                        current_lot_ids = existing.lot_ids.ids
                        merged_lot_ids = list(set(current_lot_ids + new_lot_ids))
                        # Asignar la lista completa de lotes
                        existing.write({'lot_ids': [(6, 0, merged_lot_ids)]})
                # Sumar cantidad
                existing.product_qty += qty
                # Actualizar otros campos si se proporcionan
                if 'product_uom_id' in vals:
                    existing.product_uom_id = vals['product_uom_id']
                if 'name' in vals:
                    existing.name = vals['name']
                # No agregar nueva línea
                continue

            # Si no existe línea compatible, crear una nueva
            updated_vals_list.append(vals)

        records = super().create(updated_vals_list)
        # Notificar en el chatter de la solicitud padre
        for rec in records:
            if rec.request_id:
                rec.request_id.message_post(
                    body=Markup(
                        """<div style="font-family: Arial, sans-serif; line-height: 1.6;">
                            <b>📦 NUEVA LÍNEA AGREGADA</b><br/>
                            • Producto: %s<br/>
                            • Cantidad: %s %s<br/>
                            • Fecha de creación: %s
                        </div>"""
                    ) % (
                        rec.product_id.display_name,
                        rec.product_qty,
                        rec.product_uom_id.name,
                        format_datetime(self.env, rec.create_date) if rec.create_date else "N/A",
                    ),
                )
        records.mapped('request_id')._sync_requisition_ids()
        return records

    def write(self, vals):
        # Campos que generan seguimiento
        TRACKED_FIELDS = {'product_id', 'product_qty', 'product_uom_id',
                          'requisition_line_id', 'lot_ids', 'note', 'name'}
        tracked_vals = {k: v for k, v in vals.items() if k in TRACKED_FIELDS}

        if not tracked_vals:
            return super().write(vals)

        # Guardar valores antiguos
        old_data = {}
        for rec in self:
            old_data[rec.id] = {f: rec[f] for f in tracked_vals}

        result = super().write(vals)

        # Publicar cambios en el chatter de la solicitud
        for rec in self:
            if not rec.request_id:
                continue
            old = old_data.get(rec.id, {})
            new = {f: rec[f] for f in tracked_vals}
            changes = []
            for field_name, old_val in old.items():
                new_val = new[field_name]
                if old_val != new_val:
                    field_label = rec._fields[field_name].string or field_name
                    old_display = self._format_value_for_display(field_name, old_val)
                    new_display = self._format_value_for_display(field_name, new_val)
                    changes.append(f"<li>{field_label}: {old_display} → {new_display}</li>")
            if changes:
                changes_html = Markup("".join(changes))
                rec.request_id.message_post(
                    body=Markup(
                        """<div style="font-family: Arial, sans-serif; line-height: 1.6;">
                            <b>📦 LÍNEA DE SOLICITUD ACTUALIZADA</b><br/>
                            Cambios:<br/>
                            <ul>%s</ul>
                        </div>"""
                    ) % (
                        changes_html
                    ),
                )
        return result

    def unlink(self):
        # Guardar información antes de borrar
        messages = []
        for rec in self:
            if rec.request_id:
                messages.append((rec.request_id, rec.product_id.display_name, rec.product_qty, rec.product_uom_id.name))
        requests = self.mapped('request_id')
        res = super().unlink()
        # Publicar después del borrado
        for request, prod_name, qty, uom_name in messages:
            request.message_post(
                body=Markup(
                    """<div style="font-family: Arial, sans-serif; line-height: 1.6;">
                        <b>🗑️ LÍNEA DE SOLICITUD ELIMINADA</b><br/>
                        • Producto: %s<br/>
                        • Cantidad: %s %s
                    </div>"""
                ) % (prod_name, qty, uom_name),
            )
        requests._sync_requisition_ids()
        return res

    # Metodo auxiliar
    # Convierte valores técnicos en texto legible para el usuario.
    def _format_value_for_display(self, field_name, value):
        field = self._fields[field_name]

        # Para campos many2one
        if field.type == 'many2one':
            return value.display_name if value else _('None')

        # Para campos boolean
        elif field.type == 'boolean':
            return _('Sí') if value else _('No')

        # Para campos selection
        elif field.type == 'selection':
            if value is False or value is None:
                return ''  # Manejar valores vacíos

            # field._description_selection(self.env) nos da la lista de tuplas [(key, label), ...]
            # dict(...) la convierte en un diccionario {key: label, ...}
            selection_dict = dict(field._description_selection(self.env))

            # Buscamos la etiqueta usando la clave (el 'value' almacenado en BD)
            # Usamos .get() por si acaso el valor almacenado no existe en la definición actual
            display_label = selection_dict.get(value, str(value))
            return display_label

        # Para campos char o text
        elif value is False and field.type in ('char', 'text'):
            return ''

        # Para fechas tipo date
        elif field.type == 'date':
            return format_date(self.env, value) if value else ''

        # Para fechas tipo datetime
        elif field.type == 'datetime':
            return format_datetime(self.env, value) if value else ''

        # Para otros campos no listados arriba
        else:
            return str(value) if value is not None else _('None')

