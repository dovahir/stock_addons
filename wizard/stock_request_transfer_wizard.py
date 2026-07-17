# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from markupsafe import Markup

class StockRequestTransferWizard(models.TransientModel):
    _name = 'stock.request.transfer.wizard'
    _description = 'Transferir líneas pendientes a otra solicitud'

    original_request_id = fields.Many2one(
        comodel_name='stock.request',
        string='Solicitud origen',
        required=True,
        default=lambda self: self.env.context.get('active_id')
    )
    backorder_id = fields.Many2one(
        comodel_name='stock.picking',
        string='Backorder',
        help='Seleccione el backorder del cual transferir líneas'
    )
    line_ids = fields.One2many(
        comodel_name='stock.request.transfer.wizard.line',
        inverse_name='wizard_id',
        string='Líneas a transferir'
    )
    cancel_backorder = fields.Boolean(
        string='Cancelar backorder completo',
        default=False,
        help='Si se activa, se cancelará todo el backorder después de transferir las líneas seleccionadas'
    )
    cancellation_reason = fields.Text(
        string='Motivo de cancelación',
        help='Motivo que se publicará al cancelar el backorder completo'
    )
    dest_request_id = fields.Many2one(
        comodel_name='stock.request',
        string='Solicitud destino',
        help='Solicitud de suministro a la que se agregarán las líneas, en caso de no aparecer ninguna, creela'
    )

    # Campos para domain en vista
    original_location_dest_id = fields.Many2one(
        comodel_name='stock.location',
        string='Ubicación destino original',
        related='original_request_id.location_dest_id',
        store=True,
        readonly=True
    )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        original_id = self.env.context.get('default_original_request_id')
        if original_id:
            original = self.env['stock.request'].browse(original_id)
            if original.exists():
                # Último backorder
                backorder = self.env['stock.picking'].search([
                    ('stock_request_id', '=', original.id),
                    ('state', 'not in', ['done', 'cancel']),
                    ('picking_type_id.code', 'in', ['outgoing', 'internal']),
                ], order='scheduled_date desc, id desc', limit=1)
                defaults['backorder_id'] = backorder.id if backorder else False

                # Última solicitud destino válida
                dest_request = self.env['stock.request'].search([
                    ('state', '=', 'draft'),
                    ('location_dest_id', '=', original.location_dest_id.id),
                    ('id', '!=', original.id),
                ], order='id desc', limit=1)
                defaults['dest_request_id'] = dest_request.id if dest_request else False

        return defaults

    def action_transfer(self):
        self.ensure_one()
        # Validaciones
        if not self.dest_request_id:
            raise UserError(_('Debe seleccionar una solicitud destino.'))
        if self.dest_request_id == self.original_request_id:
            raise UserError(_('La solicitud destino no puede ser la misma que la origen.'))
        if self.dest_request_id.state != 'draft':
            raise UserError(_('La solicitud destino debe estar en borrador.'))
        if self.dest_request_id.location_dest_id != self.original_request_id.location_dest_id:
            raise UserError(_('La solicitud destino debe tener la misma ubicación de destino.'))
        selected = self.line_ids.filtered('selected')
        if not selected:
            raise UserError(_('Seleccione al menos una línea para transferir.'))
        if self.cancel_backorder and not self.cancellation_reason:
            raise UserError(_('El motivo de cancelación es obligatorio para cancelar el backorder.'))

        # Transferir líneas
        StockRequestLine = self.env['stock.request.line']
        for line in selected:
            move = line.move_id
            qty = line.pending_qty
            original_line = move.stock_request_line_id
            requester = original_line.requester_name if original_line else ''
            vals = {
                'request_id': self.dest_request_id.id,
                'product_id': move.product_id.id,
                'product_qty': qty,
                'product_uom_id': move.product_uom.id,
                'name': move.product_id.display_name,
                'requisition_line_id': move.requisition_line_id.id,
                'source_request_id': self.original_request_id.id,
                'note': move.stock_request_line_id.note or '' if move.stock_request_line_id else '',
                'is_manual': not bool(move.requisition_line_id),  # si no hay requisición, es manual
                'requester_name': requester,
            }
            # create ya aplica la lógica de fusión existente
            StockRequestLine.create(vals)

        # Gestión del backorder
        # backorder = self.backorder_id
        # if self.cancel_backorder:
        #     backorder.with_context(
        #         mail_notrack=True, cancel_reason=self.cancellation_reason
        #     )._action_cancel()
        #     backorder.message_post(
        #         body=_(
        #             'Backorder cancelado. Motivo: %(reason)s. '
        #             'Líneas transferidas a solicitud %(dest)s.'
        #         ) % {'reason': self.cancellation_reason, 'dest': self.dest_request_id.name}
        #     )
        # else:
        #     # Cancelar solo los movimientos seleccionados
        #     selected_moves = selected.move_id
        #     selected_moves._action_cancel()
        #     backorder.message_post(
        #         body=_(
        #             'Movimientos cancelados por transferencia a solicitud %(dest)s.'
        #         ) % {'dest': self.dest_request_id.name}
        #     )
        #     # Si el backorder se queda sin movimientos activos, cancelarlo
        #     if not backorder.move_ids.filtered(
        #         lambda m: m.state not in ('done', 'cancel')
        #     ):
        #         backorder.with_context(mail_notrack=True).action_cancel()
        #         backorder.message_post(body=_('Backorder cancelado automáticamente por quedar vacío.'))

        # --- Eliminar las líneas de la solicitud origen y los movimientos del backorder ---
        backorder = self.backorder_id
        for line in selected:
            move = line.move_id
            qty = line.pending_qty
            # Obtener la línea original en la solicitud de origen
            original_line = move.stock_request_line_id
            if original_line:
                # Registrar en el chatter de la solicitud origen
                self.original_request_id.message_post(
                    body=Markup(
                        "🔀 Línea transferida a solicitud %s<br/>"
                        "• Producto: %s<br/>"
                        "• Cantidad: %s %s"
                    ) % (
                             self.dest_request_id.name,
                             original_line.product_id.display_name,
                             qty,
                             original_line.product_uom_id.name,
                         )
                )
                # Eliminar la línea de la solicitud original
                original_line.unlink()
            # Cancelar y eliminar el movimiento del backorder
            move._action_cancel()
            move.sudo().unlink()

        # Si el backorder se queda sin movimientos activos, cancelarlo automáticamente
        if not backorder.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            backorder.with_context(
                mail_notrack=True, cancel_reason="Backorder cancelado automáticamente por quedar vacío.")._action_cancel()

        elif not self.cancel_backorder:
            # Si no se canceló todo y aún quedan movimientos, publicar un resumen
            backorder.message_post(
                body=_("Se eliminaron los productos transferidos a solicitud %s.") % self.dest_request_id.name
            )
        else:
            # Si se marcó cancelar el backorder completo, se cancelan los movimientos restantes
            backorder.with_context(
                mail_notrack=True, cancel_reason=self.cancellation_reason
            )._action_cancel()
            backorder.message_post(
                body=_(
                    "Backorder cancelado. Motivo: %(reason)s. "
                    "Líneas transferidas a solicitud %(dest)s."
                ) % {'reason': self.cancellation_reason, 'dest': self.dest_request_id.name}
            )

        # Mensajes de trazabilidad
        # self.original_request_id.message_post(
        #     body=_('Se transfirieron líneas a solicitud %(dest)s.') % {'dest': self.dest_request_id.name}
        # )
        # self.dest_request_id.message_post(
        #     body=_('Se agregaron líneas desde la solicitud %(orig)s.') % {'orig': self.original_request_id.name}
        # )

        # Marcar que la solicitud original ha transferido líneas
        self.original_request_id.write({'has_transferred_lines': True})

        # Recalcular estado de la solicitud original
        self.original_request_id._compute_overall_state()

        return {'type': 'ir.actions.act_window_close'}


class StockRequestTransferWizardLine(models.TransientModel):
    _name = 'stock.request.transfer.wizard.line'
    _description = 'Línea del wizard de transferencia'

    wizard_id = fields.Many2one('stock.request.transfer.wizard')
    move_id = fields.Many2one(comodel_name='stock.move', string='Movimiento')
    selected = fields.Boolean(string='Transferir')
    product_id = fields.Many2one(related='move_id.product_id', readonly=True)
    requisition_name = fields.Char(
        related='move_id.requisition_line_id.requisition_product_id.name',
        string='Requisición',
        readonly=True
    )

    original_qty = fields.Float(
        compute='_compute_qty', store=False, string='Cant. solicitada')
    sent_qty = fields.Float(
        compute='_compute_qty', store=False, string='Cant. enviada')
    pending_qty = fields.Float(
        compute='_compute_qty', store=False, string='Cant. pendiente')

    @api.depends('move_id', 'move_id.stock_request_line_id', 'move_id.stock_request_line_id.product_qty',
                 'move_id.state', 'move_id.quantity', 'move_id.picking_id.state')
    def _compute_qty(self):
        for rec in self:
            if not rec.move_id:
                rec.original_qty = rec.sent_qty = rec.pending_qty = 0.0
                continue
            # Cantidad solicitada en la línea de la solicitud original
            request_line = rec.move_id.stock_request_line_id
            original = request_line.product_qty if request_line else rec.move_id.product_uom_qty
            # Cantidad ya enviada: sumar product_uom_qty de todos los movimientos en 'done' y sean 'internal'
            sent = 0.0
            if request_line:
                sent = sum(
                    self.env['stock.move'].search([
                        ('stock_request_line_id', '=', request_line.id),
                        ('picking_code', 'in', ('outgoing', 'internal')),
                        ('state', '=', 'done'),
                        ('id', '!=', rec.move_id.id)
                    ]).mapped('product_uom_qty')
                )
            rec.original_qty = original
            rec.sent_qty = sent
            rec.pending_qty = original - sent