from odoo import models, fields, api, _

class StockRequestCancelWizard(models.TransientModel):
    _name = 'stock.request.cancel.wizard'
    _description = 'Wizard para solicitud'

    request_id = fields.Many2one(
        comodel_name='stock.request',
        string='Solicitud a cancelar',
        required=True,
        default=lambda self: self.env.context.get('active_id'))

    cancellation_reason = fields.Text(
        string='Motivo de cancelación',
        required=True,
        help="Describe el motivo por el cual se cancela esta solicitud y sus documentos relacionados."
    )

    # cancel_purchases = fields.Boolean(
    #     string='Cancelar Órdenes de Compra Relacionadas',
    #     default=True,
    #     help="Si está activado, se cancelarán las órdenes de compra relacionadas con la requisición."
    # )

    cancel_stock_moves = fields.Boolean(
        string='Cancelar movimientos de almacén relacionados',
        default=True,
        help="Si está activado, se cancelarán los movimientos de almacén relacionados"
    )

    def action_confirm_cancel(self):
        """
        Cancela la solicitud y sus documentos relacionados según las opciones seleccionadas.
        Publica el motivo en el chatter de todos los documentos afectados.
        """
        self.ensure_one()
        request = self.request_id
        reason = self.cancellation_reason

        # 1. Cancelar movimientos de almacén relacionados si está activado
        if self.cancel_stock_moves:
            related_pickings = self.env['stock.picking'].search([
                ('stock_request_id', '=', request.id),
                ('state', 'in', ['draft', 'confirmed', 'assigned'])
            ])

            if related_pickings:
                picking_names = ', '.join(related_pickings.mapped('name'))
                for picking in related_pickings:
                    # Usamos mail_notrack para evitar mensajes de tracking automáticos y agregar uno personalizado
                    picking.with_context(mail_notrack=True).action_cancel()
                    picking.message_post(
                        body=_("Cancelado automáticamente desde la solicitud %s con el motivo: %s") % (request.name, reason)
                    )
                # Publicar un resumen en la requisición
                request.message_post(
                    body=_("Se cancelaron los siguientes movimientos de almacén: %s") % picking_names
                )

        # # 2. Cancelar órdenes de compra relacionadas si está activado
        # if self.cancel_purchases:
        #     related_orders = self.env['purchase.order'].search([
        #         ('requisition_ids', 'in', requisition.id),
        #         ('state', 'in', ['draft', 'sent'])
        #     ])
        #
        #     if related_orders:
        #         order_names = ', '.join(related_orders.mapped('name'))
        #         for order in related_orders:
        #             order.with_context(mail_notrack=True).button_cancel()
        #             order.message_post(
        #                 body=_("Cancelado automáticamente desde la requisición %s con el motivo: %s") % (requisition.name, reason)
        #             )
        #         # Publicar un resumen en la requisición
        #         requisition.message_post(
        #             body=_("Se cancelaron las siguientes órdenes de compra: %s") % order_names
        #         )

        # 3. Cancelar la requisición
        request.with_context(mail_notrack=True).write({
            'state': 'cancel',
            'rejected_user_id': self.env.uid,
            'reject_date': fields.Date.today(),
        })

        # 4. Publicar el motivo principal en el chatter de la requisición
        request.message_post(
            body=_("Solicitud cancelada con el motivo: %s") % reason
        )

        # 5. Eliminar actividades pendientes
        request.activity_unlink(['mail.mail_activity_data_todo'])

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cancelado'),
                'message': _('La requisición y sus documentos relacionados han sido cancelados.'),
                'type': 'info',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window_close',
                },
            }
        }
