# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    stock_request_line_id = fields.Many2one(comodel_name="stock.request.line", string="Stock Request List")
    requisition_line_id = fields.Many2one(comodel_name='requisition.order', string='Línea de requisición (origen)')
    requisition_id = fields.Many2one(comodel_name='employee.purchase.requisition', related='requisition_line_id.requisition_product_id', store=True)

    requisition_ids = fields.Many2many(
        comodel_name='employee.purchase.requisition',
        string='Requisiciones origen',
        help='Requisiciones que contribuyen a este movimiento'
    )

    line_number = fields.Integer(compute='_compute_line_number', string='N.º Línea', store=False)

    @api.depends('picking_id', 'picking_id.move_ids', 'sequence')
    def _compute_line_number(self):
        for move in self:
            if not move.picking_id:
                move.line_number = 1  # sin picking, asigna 1
                continue
            ordered = move.picking_id.move_ids.sorted(key=lambda m: (m.sequence, m.id or 0))
            # Intentar encontrar la posición del movimiento actual por su ID
            try:
                pos = ordered.ids.index(move.id)
                move.line_number = pos + 1
            except ValueError:
                # Si no está en la lista asigna el número siguiente al último, para que nunca sea 0
                move.line_number = len(ordered) + 1

    # Evitar fusionar líneas de SR
    def _prepare_merge_moves_distinct_fields(self):
        distinct_fields = super()._prepare_merge_moves_distinct_fields()
        # Añadimos el campo que diferencia líneas de solicitud
        distinct_fields.append('stock_request_line_id')
        return distinct_fields

    ## Evitar que se muestren num de series que no estén en disponibilidad
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
        de origen (y todas sus sub-ubicaciones hijas) para movimientos de salida o traslados.
        Se ejecuta en lote (batch) agrupando por ubicaciones raíz únicas.
        En recepciones (origen no interno), muestra todos los lotes existentes del producto.
        """
        internal_moves = self.filtered(
            lambda m: m.product_id and m.location_id and m.location_id.usage == 'internal'
        )
        non_internal_moves = self - internal_moves
        non_internal_moves.is_internal_origin = False
        if non_internal_moves:
            non_int_with_prod = non_internal_moves.filtered(lambda m: m.product_id)
            if non_int_with_prod:
                all_lots = self.env['stock.lot'].search([
                    ('product_id', 'in', non_int_with_prod.mapped('product_id').ids)
                ])
                lots_by_prod = defaultdict(lambda: self.env['stock.lot'])
                for lot in all_lots:
                    lots_by_prod[lot.product_id.id] |= lot
                for move in non_int_with_prod:
                    move.available_lot_ids = lots_by_prod.get(move.product_id.id, self.env['stock.lot'])
            (non_internal_moves - non_int_with_prod).available_lot_ids = False

        internal_moves.is_internal_origin = True

        if not internal_moves:
            return

        # 1. Obtener todas las ubicaciones hijas en una sola consulta por lote
        unique_locations = internal_moves.location_id
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
        product_ids = internal_moves.mapped('product_id').ids
        companies = internal_moves.mapped('company_id').ids

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

        # 4. Asignar a cada movimiento los lotes de su ubicación y todas sus hijas
        for move in internal_moves:
            child_loc_ids = loc_to_child_ids.get(move.location_id.id, {move.location_id.id})
            lots = self.env['stock.lot']
            prod_id = move.product_id.id
            for loc_id in child_loc_ids:
                lots |= lots_by_prod_loc.get((prod_id, loc_id), self.env['stock.lot'])

            # Si el movimiento ya tiene lotes asignados previamente, conservarlos
            if move.lot_ids:
                lots |= move.lot_ids

            move.available_lot_ids = lots