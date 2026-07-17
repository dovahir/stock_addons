from odoo import fields, models, api, _
from odoo.exceptions import UserError

############### Modelo usado principalmente para extender a otros modelos ##################

class StockPicking(models.Model):
    _inherit = "stock.picking"

    stock_request_id = fields.Many2one(comodel_name="stock.request", string="Solicitudes de suministro")

    # Action para smartbutton en un picking vinculado a un stock_request
    def action_open_stock_request(self):
        self.ensure_one()
        if not self.stock_request_id:
            raise UserError(_('Este movimiento no está vinculado a ninguna solicitud de stock.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Suministro origen'),
            'res_model': 'stock.request',
            'res_id': self.stock_request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # Imprime el reporte personalizado para este albarán
    def action_print_report(self):
        self.ensure_one()
        return self.env.ref('stock_addons.action_reporte_traspaso').report_action(self)

    can_be_returned = fields.Boolean(compute='_compute_can_be_returned')

    @api.depends('stock_request_id.state', 'stock_request_id')
    def _compute_can_be_returned(self):
        for picking in self:
            if picking.stock_request_id and picking.stock_request_id.state in ('done_exact', 'done_partial',
                                                                               'done_adjusted'):
                picking.can_be_returned = False
            else:
                picking.can_be_returned = True

    # Sobreescritura de la validacion en un picking
    def _action_done(self):
        res = super(StockPicking, self)._action_done()

        for picking in self:
            # Interceptamos cuando el movimiento de stock finaliza para actualizar el estado de stock_request
            if picking.stock_request_id and picking.state == 'done':
                picking.stock_request_id._process_picking_validation(picking)

        return res

    # Devuelve True si el picking es una devolución
    # (tiene return_id o sus movimientos tienen origin_returned_move_id)
    def _is_return_picking(self):
        if self.return_id:
            return True
        for move in self.move_ids:
            if move.origin_returned_move_id:
                return True
        return False

    # Interceptamos la cancelación para notificar al stock_request
    def action_cancel(self):
        res = super(StockPicking, self).action_cancel()

        for picking in self:
            if picking.stock_request_id and picking.state == 'cancel':
                picking.stock_request_id._process_picking_cancel(picking)

        return res

    # Metodo para que sean requeridos ciertos campos (se puede poner en requisiciones/stock_picking.py)
    def button_validate(self):
        for picking in self:
            # Obligatorio para órdenes de entrega Y para cualquier tipo que contenga "resguardo"
            is_resguardo = 'resguardo' in picking.picking_type_id.name.lower()
            if picking.picking_type_id.code == 'outgoing' or is_resguardo:
                if not picking.emp:
                    raise UserError(_('El campo "Solicita" es obligatorio para este tipo de operación.'))
                if not picking.partner_id:
                    raise UserError(_('El campo "Dirección de entrega/Contacto" es obligatorio para este tipo de operación.'))
        return super().button_validate()

