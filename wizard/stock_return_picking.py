from odoo import models, api

class StockReturnPicking(models.TransientModel):
    _inherit = "stock.return.picking"

    def create_returns(self):
        # Ejecutamos el comportamiento estándar (crea el picking y los movimientos)
        res = super().create_returns()

        # Obtenemos el picking de devolución recién creado
        new_picking_id = res.get('res_id')
        if new_picking_id:
            new_picking = self.env['stock.picking'].browse(new_picking_id)
            self._copy_serial_numbers(new_picking)
        return res

    # Copia los números de serie desde los movimientos originales a los de devolución.
    def _copy_serial_numbers(self, return_picking):
        for return_move in return_picking.move_ids.filtered(lambda m: m.product_id.tracking == 'serial'):
            original_move = return_move.origin_returned_move_id
            if not original_move or not original_move.move_line_ids:
                continue

            # Eliminar líneas vacías creadas por defecto
            return_move.move_line_ids.unlink()

            # Cantidad a devolver en este movimiento
            qty_to_return = return_move.product_uom_qty
            remaining = qty_to_return

            # Copiamos líneas del movimiento original hasta completar la cantidad de retorno
            for original_line in original_move.move_line_ids:
                if remaining <= 0:
                    break
                # Tomamos la cantidad a devolver de este lote (máximo la original, pero limitado a lo que queda)
                take_qty = min(original_line.quantity, remaining)
                if take_qty <= 0:
                    continue

                self.env['stock.move.line'].create({
                    'move_id': return_move.id,
                    'picking_id': return_picking.id,
                    'product_id': original_line.product_id.id,
                    'lot_id': original_line.lot_id.id,
                    'quantity': take_qty,
                    'location_id': return_move.location_id.id,
                    'location_dest_id': return_move.location_dest_id.id,
                })
                remaining -= take_qty