from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class StockRequest(models.Model):
    _name = "stock.request"
    _inherit = ['mail.thread', 'mail.activity.mixin', "analytic.mixin"]
    _rec_name = "name"
    _order = "name desc"
    _description = "Stock Request"

    name = fields.Char(string='Solicitud', required=True, copy=False, index=True,
                       default=lambda self: _('Solicitud'),
                       tracking=True, readonly=True)

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirm', 'Confirmado'),
        ('validate', 'Validado'),
        ('cancel', 'Cancelado')
    ], string="Estado", default="draft", tracking=True)

    ## Campos de informacion ##

    request_uid = fields.Many2one(comodel_name="res.users",
                                  string="Solicitado por",
                                  default=lambda self: self.env.user,
                                  readonly=True)

    request_date = fields.Datetime(string="Fecha de solicitud", readonly=True,
                                   help="La fecha y hora será asignada al momento de validar la solicitud")

    scheduled_date = fields.Datetime(string="Fecha de entrega",
                                     default=fields.Datetime.now,
                                     required=True)

    notes = fields.Text(string="Notas")

    requisition_ids = fields.Many2many(comodel_name='employee.purchase.requisition',
                                       string='Requisiciones origen')

    company_id = fields.Many2one(comodel_name="res.company",
                                 string="Compañía",
                                 default=lambda self: self.env.company,
                                 readonly=True)

    #### Campos de origen ####

    picking_type_id = fields.Many2one(comodel_name="stock.picking.type",
                                      string="Tipo de operación (Origen)",
                                      required=True,
                                      tracking=True)

    warehouse_id = fields.Many2one(comodel_name="stock.warehouse",
                                   string="Almacén",
                                   required=True,
                                   tracking=True)

    location_id = fields.Many2one(comodel_name="stock.location",
                                  string="Ubicación de origen",
                                  required=True,
                                  tracking=True)

    #### Campos de destino ####

    picking_type_dest_id = fields.Many2one(comodel_name="stock.picking.type",
                                           string="Tipo de operación (Destino)",
                                           required=True,
                                           tracking=True)

    location_dest_id = fields.Many2one(comodel_name="stock.location",
                                       string="Ubicación destino",
                                       required=True,
                                       tracking=True)

    warehouse_dest_id = fields.Many2one(comodel_name="stock.warehouse",
                                        related="location_dest_id.warehouse_id", # Siempre relativo al destino
                                        string="Almacén",
                                        store=True)

############################################################################################

    line_ids = fields.One2many(comodel_name="stock.request.line",
                               inverse_name="request_id",
                               string="Lineas de requisicion")

    picking_ids = fields.One2many(comodel_name="stock.picking",
                                  inverse_name="stock_request_id",
                                  string="Operaciones")

    outgoing_count = fields.Integer(string='Entrega',
                                    compute="_compute_transfer_count")

    incoming_count = fields.Integer(string='Recepcion',
                                    compute="_compute_transfer_count")

    ##  ##

    rejected_user_id = fields.Many2one(comodel_name='res.users', string='Rechazado por',
                                       readonly=True, copy=False,
                                       help='user who rejected the requisition')

    # confirmed_date = fields.Date(string='Fecha de confirmacion', readonly=True, copy=False,
    #                              help='Date of Requisition Confirmation')
    #
    # approval_date = fields.Date(string='Approved Date', readonly=True, copy=False,
    #                             help='Requisition Approval Date')
    #
    # reject_date = fields.Date(string='Fecha de rechazo', readonly=True, copy=False,
    #                           help='Requisition Rejected Date')

    ## Metodos de estado ##

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nueva solicitud')) == _('Nueva solicitud'):
                vals['name'] = (self.env['ir.sequence'].next_by_code('stock.request'))
        return super().create(vals_list)

    def button_draft(self):
        self.ensure_one()

        self.state = 'draft'

    def button_confirm(self):
        self.ensure_one()

        if not self.line_ids:
            raise ValidationError(_("La solicitud no puede estar vacía.\nPor favor, añade productos a la solicitud."))

        # Obtener ubicación de tránsito desde los tipos de operación
        # Lo toma desde el destino predeterminado dentro del tipo de operacion
        transit_location = self.picking_type_id.default_location_dest_id or self.picking_type_dest_id.default_location_src_id

        if not transit_location:
            raise ValidationError(_(
                "No se ha definido una ubicación de tránsito.\n"
                "Configura 'Ubicación destino' en el tipo de operación de origen,\n"
                "o 'Ubicación origen' en el tipo de operación de destino."
            ))

        # Verificar que ambas coincidan si están definidas
        if (self.picking_type_id.default_location_dest_id and
                self.picking_type_dest_id.default_location_src_id and
                self.picking_type_id.default_location_dest_id != self.picking_type_dest_id.default_location_src_id):
            raise ValidationError(_(
                "La ubicación de tránsito no coincide entre los tipos de operación.\n"
                "Origen destino: %s\nDestino origen: %s"
            ) % (self.picking_type_id.default_location_dest_id.display_name,
                 self.picking_type_dest_id.default_location_src_id.display_name))

        if self.picking_type_id.default_dest_picking_type != self.picking_type_dest_id:
            raise ValidationError(_(
                "El tipo de operación origen no es compatible con el tipo de operación destino.\n"
                "Origen: %s\nDestino: %s"
            ) % (self.picking_type_id.display_name,
                 self.picking_type_dest_id.display_name))


        self.state = 'confirm'

    # En este metodo se lleva a cabo la mayoria de acciones
    def button_validate(self):
        self.ensure_one()

        # if not self.line_ids and not self.manual_line_ids:
        #     raise ValidationError(_("La solicitud no puede estar vacía."))

        # Obtener ubicación de tránsito desde los tipos de operación
        # Nota: Lo toma segun su Ubicacion de destino predeterminada, en Ubicaciones
        transit_location = self.picking_type_id.default_location_dest_id or self.picking_type_dest_id.default_location_src_id

        # Preparar movimientos combinando líneas de requisicion y stock

        # Lista para los mov de almacén
        outgoing_move_vals = []
        incoming_move_vals = []

        # Líneas de requisiciones
        for line in self.line_ids:
            outgoing_move_vals.append(self._prepare_move_vals(line, 'outgoing', transit_location))
            incoming_move_vals.append(self._prepare_move_vals(line, 'incoming', transit_location))

        # Crea el stock.picking de entrega (origen a transito)
        outgoing_picking = self.env['stock.picking'].create({
            'stock_request_id': self.id,
            'scheduled_date': self.request_date,
            'origin': self.name,
            'company_id': self.picking_type_id.company_id.id,
            'picking_type_id': self.picking_type_id.id,
            'location_id': self.location_id.id,
            'location_dest_id': transit_location.id, # Definido anteriormente
            'move_ids_without_package': outgoing_move_vals, # Aqui se agregan los mov de almacen
        })
        outgoing_picking.action_confirm()

        # # Lo mismo que antes pero para la recepcion
        incoming_picking = self.env['stock.picking'].create({
            'stock_request_id': self.id,
            'scheduled_date': self.scheduled_date,
            'origin': self.name,
            'company_id': self.picking_type_dest_id.company_id.id,
            'picking_type_id': self.picking_type_dest_id.id,
            'location_id': transit_location.id, # Ahora el origen es el transito
            'location_dest_id': self.location_dest_id.id,
            'move_ids_without_package': incoming_move_vals,
        })
        incoming_picking.action_confirm()

        self.write({
            'state': 'validate',
            'request_date': fields.Datetime.now()
        })

    # Para líneas de requi (stock.request.line)
    def _prepare_move_vals(self, line, direction, transit_location):
        vals = {
            'stock_request_line_id': line.id,
            'product_id': line.product_id.id,
            'product_uom_qty': line.product_qty,
            'product_uom': line.product_uom_id.id,
            'name': line.name,
            'company_id': self.picking_type_id.company_id.id if direction == 'outgoing' else self.picking_type_dest_id.company_id.id,
            'date_deadline': self.scheduled_date,
            'date': self.scheduled_date,
        }
        if direction == 'outgoing':
            vals.update({
                'location_id': self.location_id.id,
                'location_dest_id': transit_location.id,
                'picking_type_id': self.picking_type_id.id,
            })
        else:
            vals.update({
                'location_id': transit_location.id,
                'location_dest_id': self.location_dest_id.id,
                'picking_type_id': self.picking_type_dest_id.id,
            })
        return (0, 0, vals)

    def button_cancel(self):
        self.ensure_one()

        self.state = 'cancel'

    @api.ondelete(at_uninstall=False)
    def _unlink_if_cancelled(self):
        for rec in self:
            if not rec.state == 'cancel':
                raise UserError(_('Para eliminar una solicitud, primero debes cancelarla.'))

    ## Metodos onchange ##

    # Al cambiar el tipo de operación origen, actualizar almacén y ubicación origen
    @api.onchange('picking_type_id')
    def _onchange_picking_type_id(self):
        if self.picking_type_id:
            # Ubicación origen por defecto del tipo
            self.location_id = self.picking_type_id.default_location_src_id
            # Almacén asociado a esa ubicación
            self.warehouse_id = self.picking_type_id.warehouse_id.id if self.location_id else False

            # Tipo de operacion destino para este origen
            self.picking_type_dest_id = self.picking_type_id.default_dest_picking_type
        else:
            self.location_id = False
            self.warehouse_id = False

    # Al cambiar el tipo de operación destino, actualizar ubicación destino
    @api.onchange('picking_type_dest_id')
    def _onchange_picking_type_dest_id(self):
        if self.picking_type_dest_id:
            self.location_dest_id = self.picking_type_dest_id.default_location_dest_id
        else:
            self.location_dest_id = False

    # Al cambiar el almacén (origen), cambia su ubicacion de existencias
    @api.onchange('warehouse_id')
    def _onchange_warehouse(self):
        for rec in self:
            if rec.warehouse_id:
                rec.location_id = rec.warehouse_id.lot_stock_id.id
            else:
                rec.location_id = False

    ## Metodos _compute ##

    # Contadores para botones de entrega/recepcion
    def _compute_transfer_count(self):
        for rec in self:
            rec.outgoing_count = len(
                rec.picking_ids.filtered(lambda p: p.location_id.id == rec.location_id.id))
            rec.incoming_count = len(
                rec.picking_ids.filtered(lambda p: p.location_dest_id.id == rec.location_dest_id.id))

    # Suma un día a la fecha de solicitud y convierte a Datetime
    # def _compute_scheduled_date(self):
    #     for record in self:
    #         if record.request_date:
    #             record.scheduled_date = record.request_date + timedelta(days=1)

    ## Metodos action ##

    # Metodos para visualizar los stock.picking de entrega/recepcion
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

    # Metodo de botones

    def action_button_cancel(self):

        return {
            'type': 'ir.actions.act_window',
            'name': _('Cancelar solicitud'),
            'res_model': 'stock.request.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
            }
        }