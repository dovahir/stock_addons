from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
# from dateutil.relativedelta import relativedelta
# from datetime import date, time, datetime, timedelta


class StockRequest(models.Model):
    _name = "stock.request"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = "name"
    _order = "name desc"
    _description = "Stock Request"


    name = fields.Char(string='Nueva solicitud', required=True, copy=False, index=True,
                       default=lambda self: _('Nueva solicitud'),
                       tracking=True, readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirm', 'Confirmado'),
        ('validate', 'Validado'),
        ('cancel', 'Cancelado')
    ], string="Estado", default="draft", tracking=True)
    company_id = fields.Many2one(comodel_name="res.company", string="Compañía", default=lambda self: self.env.company,
                                 readonly=True)
    warehouse_id = fields.Many2one(comodel_name="stock.warehouse", string="Almacén", required=True, tracking=True)
    picking_type_id = fields.Many2one(comodel_name="stock.picking.type", string="Tipo de operación (Origen)", required=True,
                                      tracking=True)
    location_id = fields.Many2one(comodel_name="stock.location", string="Ubicación de origen", required=True, tracking=True)
    location_dest_id = fields.Many2one(comodel_name="stock.location", string="Ubicación destino", required=True,
                                       tracking=True)
    warehouse_dest_id = fields.Many2one(comodel_name="stock.warehouse", related="location_dest_id.warehouse_id",
                                        string="Almacén", store=True)
    picking_type_dest_id = fields.Many2one(comodel_name="stock.picking.type", string="Tipo de operación (Destino)",
                                           required=True, tracking=True)
    request_uid = fields.Many2one(comodel_name="res.users", string="Solicitado por", default=lambda self: self.env.user,
                                  readonly=True)
    request_date = fields.Date(string="Fecha de solicitud", default=lambda self: fields.Date.context_today(self),
                               readonly=True)
    scheduled_date = fields.Datetime(string="Fecha programada", default=fields.Datetime.now, required=True)
    notes = fields.Text(string="Notas")
    line_stock_ids = fields.One2many(comodel_name="stock.request.line", inverse_name="request_id", string="Request List")
    picking_ids = fields.One2many(comodel_name="stock.picking", inverse_name="stock_request_id", string="Operaciones")
    outgoing_count = fields.Integer('Entrega', compute="_compute_transfer_count")
    incoming_count = fields.Integer('Recepcion', compute="_compute_transfer_count")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nueva solicitud')) == _('Nueva solicitud'):
                vals['name'] = (self.env['ir.sequence'].next_by_code('stock.request'))
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_if_cancelled(self):
        for rec in self:
            if not rec.state == 'cancel':
                raise UserError(_('Para eliminar una solicitud, primero debes cancelarla.'))

    @api.onchange('warehouse_id')
    def _onchange_warehouse(self):
        for rec in self:
            if rec.warehouse_id:
                rec.location_id = rec.warehouse_id.lot_stock_id.id
            else:
                rec.location_id = False

    def button_confirm(self):
        self.ensure_one()

        if not self.line_stock_ids:
            raise ValidationError(_("La solicitud no puede estar vacía.\nPor favor, añade productos a la solicitud."))

        self.state = 'confirm'

    def button_validate(self):
        self.ensure_one()

        if not self.line_stock_ids:
            raise ValidationError(_("La solicitud no puede estar vacía.\nPor favor, añade productos a la solicitud."))

        # Definimos la ubicación de transito
        location_transit_id = self.env['stock.location'].search([
            ('usage', '=', 'transit'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        if not location_transit_id:
            raise ValidationError(_("Transit Location for Company '%s' is not found!\n"
                                    "Please configure a Transit location in Inventory > Configuration > Locations.") % self.company_id.name)

        # Definimos los tipos de operación para entrega y recepción
        # Deben ser de tipo transferencia interna
        outgoing_picking_type_id = self.picking_type_id
        incoming_picking_type_id = self.picking_type_dest_id

        if not outgoing_picking_type_id:
            raise ValidationError(_("Operations Type 'Internal Transfer' for Warehouse '%s' is not found!\n"
                                    "Please check warehouse configuration.") % self.location_id.warehouse_id.name)

        if not incoming_picking_type_id:
            raise ValidationError(_("Operations Type 'Internal Transfer' for Warehouse '%s' is not found!\n"
                                    "Please check warehouse configuration.") % self.location_dest_id.warehouse_id.name)

        # Se crea un diccionario que contendrá todos los stock.move de la solicitud
        outgoing_move_vals = []
        for line in self.line_stock_ids:
            outgoing_move_vals.append((0, 0, {
                'stock_request_line_id': line.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_qty,
                'product_uom': line.product_uom_id.id,
                'name': line.name,
                'company_id': outgoing_picking_type_id.company_id.id,
                'date_deadline': self.scheduled_date,
                'date': self.scheduled_date,
                'location_id': self.location_id.id,
                'location_dest_id': location_transit_id.id,
                'picking_type_id': outgoing_picking_type_id.id,
            }))

        # Se crea un stock.picking con los campos de la solicitud
        outgoing_picking_id = self.env['stock.picking'].create({
            'stock_request_id': self.id, #Relacion con la solicitud
            'scheduled_date': self.scheduled_date,
            'origin': self.name, #Nombre de la solicitud
            'company_id': outgoing_picking_type_id.company_id.id,
            'picking_type_id': outgoing_picking_type_id.id,
            'location_id': self.location_id.id,
            'location_dest_id': location_transit_id.id,
            'move_ids_without_package': outgoing_move_vals #Los stock.move anteriores
        })

        #Se autoconfirma el stock.picking pasando a "En espera" o "Listo"
        outgoing_picking_id.action_confirm()

        incoming_move_vals = []
        for line in self.line_stock_ids:
            incoming_move_vals.append((0, 0, {
                'stock_request_line_id': line.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_qty,
                'product_uom': line.product_uom_id.id,
                'name': line.name,
                'company_id': incoming_picking_type_id.company_id.id,
                'date_deadline': self.scheduled_date,
                'date': self.scheduled_date,
                'location_id': location_transit_id.id,
                'location_dest_id': self.location_dest_id.id,
                'picking_type_id': incoming_picking_type_id.id,
            }))

        incoming_picking_id = self.env['stock.picking'].create({
            'stock_request_id': self.id,
            'scheduled_date': self.scheduled_date,
            'origin': self.name,
            'company_id': incoming_picking_type_id.company_id.id,
            'picking_type_id': incoming_picking_type_id.id,
            'location_id': location_transit_id.id,
            'location_dest_id': self.location_dest_id.id,
            'move_ids_without_package': incoming_move_vals
        })
        incoming_picking_id.action_confirm()

        self.state = 'validate'

    def button_cancel(self):
        self.ensure_one()

        self.state = 'cancel'

    def button_draft(self):
        self.ensure_one()

        self.state = 'draft'

    def _compute_transfer_count(self):
        for rec in self:
            rec.outgoing_count = len(rec.picking_ids.filtered(lambda p: p.location_id.id == rec.location_id.id))
            rec.incoming_count = len(
                rec.picking_ids.filtered(lambda p: p.location_dest_id.id == rec.location_dest_id.id))

    def action_view_outgoing(self):
        self.ensure_one()

        action = self.env.ref('stock.action_picking_tree_all').sudo().read()[0]
        action['domain'] = [('stock_request_id', '=', self.id), ('location_id', '=', self.location_id.id)]
        return action

    def action_view_incoming(self):
        self.ensure_one()

        action = self.env.ref('stock.action_picking_tree_all').sudo().read()[0]
        action['domain'] = [('stock_request_id', '=', self.id), ('location_dest_id', '=', self.location_dest_id.id)]
        return action

