# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    requisition_line_id = fields.Many2one(comodel_name='requisition.order', string='Línea de requisición')
    requisition_id = fields.Many2one(comodel_name='employee.purchase.requisition', related='requisition_line_id.requisition_product_id', store=True)

    ## Evitar que se muestren num de series que no estén en disponibilidad

    # Campo que contiene únicamente las series con stock en el origen
    available_lot_ids = fields.Many2many(
        comodel_name='stock.lot',
        compute='_compute_available_lot_ids',
        string='Lotes Disponibles en Origen'
    )
    is_internal_origin = fields.Boolean(
        string='Origen Interno',
        compute='_compute_available_lot_ids'
    )

    @api.depends('product_id', 'location_id', 'company_id')
    def _compute_available_lot_ids(self):
        """
        Determina los números de serie y lotes físicamente disponibles en la ubicación
        de origen (y todas sus sub-ubicaciones hijas) para líneas de operaciones detalladas.
        Se ejecuta en lote (batch) agrupando por ubicaciones raíz únicas.
        En recepciones (origen no interno), muestra todos los lotes existentes del producto.
        """
        internal_lines = self.filtered(
            lambda l: l.product_id and l.location_id and l.location_id.usage == 'internal'
        )
        non_internal_lines = self - internal_lines
        non_internal_lines.is_internal_origin = False
        if non_internal_lines:
            non_int_with_prod = non_internal_lines.filtered(lambda l: l.product_id)
            if non_int_with_prod:
                all_lots = self.env['stock.lot'].search([
                    ('product_id', 'in', non_int_with_prod.mapped('product_id').ids)
                ])
                lots_by_prod = defaultdict(lambda: self.env['stock.lot'])
                for lot in all_lots:
                    lots_by_prod[lot.product_id.id] |= lot
                for line in non_int_with_prod:
                    line.available_lot_ids = lots_by_prod.get(line.product_id.id, self.env['stock.lot'])
            (non_internal_lines - non_int_with_prod).available_lot_ids = False

        internal_lines.is_internal_origin = True

        if not internal_lines:
            return

        # 1. Obtener todas las ubicaciones hijas en una sola consulta por lote
        unique_locations = internal_lines.location_id
        all_child_locations = self.env['stock.location'].search([('id', 'child_of', unique_locations.ids)])

        loc_to_child_ids = {}
        for loc in unique_locations:
            prefix = loc.parent_path or f"{loc.id}/"
            loc_to_child_ids[loc.id] = {
                child.id for child in all_child_locations
                if child.parent_path and child.parent_path.startswith(prefix)
            } | {loc.id}

        all_child_location_ids = set(all_child_locations.ids)

        # 2. Consultar quants en lote con existencia física mayor a cero
        product_ids = internal_lines.mapped('product_id').ids
        companies = internal_lines.mapped('company_id').ids

        domain = [
            ('product_id', 'in', product_ids),
            ('location_id', 'in', list(all_child_location_ids)),
            ('lot_id', '!=', False),
            ('quantity', '>', 0),
        ]
        if companies:
            domain.append(('company_id', 'in', companies))

        quants = self.env['stock.quant'].search(domain)

        # 3. Mapear en memoria los lotes por (product_id, location_id)
        lots_by_prod_loc = defaultdict(lambda: self.env['stock.lot'])
        for quant in quants:
            lots_by_prod_loc[(quant.product_id.id, quant.location_id.id)] |= quant.lot_id

        # 4. Asignar a cada línea los lotes disponibles en su jerarquía de origen
        for line in internal_lines:
            child_loc_ids = loc_to_child_ids.get(line.location_id.id, {line.location_id.id})
            lots = self.env['stock.lot']
            prod_id = line.product_id.id
            for loc_id in child_loc_ids:
                lots |= lots_by_prod_loc.get((prod_id, loc_id), self.env['stock.lot'])

            # Si la línea ya tiene un lote asignado previamente, conservarlo
            if line.lot_id:
                lots |= line.lot_id

            line.available_lot_ids = lots
