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
        ('draft', 'En proceso'),
        ('delivery_created', 'Entrega creada'),
        ('in_transit', 'En tránsito'),
        ('done_exact', 'Trasladado'),
        ('done_partial', 'Parcialmente trasladado'),
        ('done_adjusted', 'Trasladado con ajustes'),
        ('cancel', 'Cancelado')
    ], string="Estado", default="draft", tracking=True)

    # Campo para la alerta en la vista
    delivery_alert = fields.Selection([
        ('exact', 'Exacto'),
        ('less', 'Faltante/Retirado'),
        ('more', 'Excedente/Añadido'),
        ('cancelled', 'Cancelado')
    ], string="Alerta de Entrega", readonly=True, copy=False)

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

    def action_button_draft(self):
        for req in self:
            req.write({
                'state': 'draft',
                'delivery_alert': False  # Limpiamos la alerta al regresar
            })

    def action_create_delivery(self):
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

        # Validar numeros de serie
        for line in self.line_ids:
            if line.has_tracking == 'serial' and not line.lot_ids:
                raise UserError(f"Faltan números de serie para: {line.product_id.name}")

        # if not self.line_ids and not self.manual_line_ids:
        #     raise ValidationError(_("La solicitud no puede estar vacía."))

        # Picking de entrega
        delivery_vals = {
            'picking_type_id': self.picking_type_id.id,
            'location_id': self.location_id.id,
            'location_dest_id': transit_location.id, # Definido anteriormente
            'stock_request_id': self.id,
            'origin': self.name,
            'move_ids': [(0, 0, {
                'name': line.product_id.name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_qty,
                'product_uom': line.product_uom_id.id,
                'location_id': self.location_id.id,
                'location_dest_id': transit_location.id,
                'stock_request_line_id': line.id,  # Para trazabilidad
            }) for line in self.line_ids]
        }

        delivery_picking = self.env['stock.picking'].create(delivery_vals)
        # Inyecta los num series
        self._assign_serial_numbers_to_picking(delivery_picking)
        delivery_picking.action_confirm()

        self.write({
            'state': 'delivery_created',
            'request_date': fields.Datetime.now()
        })

    # Vincula las series seleccionadas en la solicitud con las líneas de entrega (stock.move.line)
    def _assign_serial_numbers_to_picking(self, picking):
        for line in self.line_ids:
            if line.has_tracking == 'serial' and line.lot_ids:
                # Busca el movimiento (stock.move) correspondiente a esta línea
                move = picking.move_ids.filtered(lambda m: m.product_id == line.product_id)
                if move:
                    # Limpia cualquier línea vacía que Odoo cree por defecto
                    move.move_line_ids.unlink()

                    # Crea una línea de movimiento por cada número de serie
                    for lot in line.lot_ids:
                        self.env['stock.move.line'].create({
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': line.product_id.id,
                            'lot_id': lot.id,
                            'quantity': 1,  # En series siempre es 1
                            'location_id': move.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                        })

    # Metodo que será llamado desde stock.picking cuando se valide
    def _process_picking_validation(self, picking):
        self.ensure_one()

        transit_location = self.picking_type_id.default_location_dest_id or self.picking_type_dest_id.default_location_src_id

        # CASO A: Se valida el albarán de ENTREGA (Origen -> Tránsito)
        if picking.location_dest_id.id == transit_location.id:
            alert_type = self._calculate_differences(picking)
            self.write({
                'state': 'in_transit',
                'delivery_alert': alert_type
            })
            self._create_receipt_picking(picking)

        # CASO B: Se valida el albarán de RECEPCIÓN (Tránsito -> Destino)
        elif picking.location_id.id == transit_location.id:
            alert_type = self._calculate_differences(picking)
            final_state = 'done_exact'
            if alert_type == 'less':
                final_state = 'done_partial'
            elif alert_type == 'more':
                final_state = 'done_adjusted'

            self.write({'state': final_state})

    # Metodo usado por si se cancela la entrega
    def _process_picking_cancel(self, picking):
        self.ensure_one()
        # Verificamos que sea el picking de entrega el que se canceló
        if picking.location_id.id == self.location_id.id:
            self.write({
                'delivery_alert': 'cancelled'
            })

    # Compara lo solicitado vs lo que realmente se movió (quantity done)
    def _calculate_differences(self, picking):
        requested = {}
        for line in self.line_ids:
            requested[line.product_id.id] = requested.get(line.product_id.id, 0) + line.product_qty

        delivered = {}
        # En Odoo 17, 'quantity' en stock.move guarda la cantidad hecha cuando el move está 'done'
        for move in picking.move_ids.filtered(lambda m: m.state == 'done'):
            delivered[move.product_id.id] = delivered.get(move.product_id.id, 0) + move.quantity

        has_less, has_more = False, False

        for prod_id, req_qty in requested.items():
            del_qty = delivered.get(prod_id, 0)
            if del_qty < req_qty:
                has_less = True
            elif del_qty > req_qty:
                has_more = True

        for prod_id, del_qty in delivered.items():
            if prod_id not in requested and del_qty > 0:
                has_more = True

        if has_more: return 'more'
        if has_less: return 'less'
        return 'exact'

    # Crea la recepción basándose en lo que salió en la entrega
    def _create_receipt_picking(self, delivery_picking):

        receipt_vals = {
            'picking_type_id': self.picking_type_dest_id.id,
            'location_id': delivery_picking.location_dest_id.id,  # Desde tránsito
            'location_dest_id': self.location_dest_id.id,  # Al destino final
            'stock_request_id': self.id,
            'origin': f"Recepción de: {self.name}",
            'move_ids': [(0, 0, {
                'name': move.product_id.name,
                'product_id': move.product_id.id,
                'product_uom_qty': move.quantity,  # La cantidad exacta que salió
                'product_uom': move.product_uom.id,
                'location_id': delivery_picking.location_dest_id.id,
                'location_dest_id': self.location_dest_id.id,
            }) for move in delivery_picking.move_ids.filtered(lambda m: m.state == 'done' and m.quantity > 0)]
        }

        receipt_picking = self.env['stock.picking'].create(receipt_vals)
        receipt_picking.action_confirm()

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

    ## Metodos action ##

    # Metodos para visualizar los stock.picking de entrega/recepcion
    # def action_view_outgoing(self):
    #     self.ensure_one()
    #
    #     action = self.env.ref('stock.action_picking_tree_all').sudo().read()[0]
    #     action['domain'] = [('stock_request_id', '=', self.id), ('location_id', '=', self.location_id.id)]
    #
    #     return action
    #
    # def action_view_incoming(self):
    #     self.ensure_one()
    #
    #     action = self.env.ref('stock.action_picking_tree_all').sudo().read()[0]
    #     action['domain'] = [('stock_request_id', '=', self.id), ('location_dest_id', '=', self.location_dest_id.id)]
    #
    #     return action

    def action_view_outgoing(self):
        self.ensure_one()
        # Leemos la acción estándar
        action = self.env.ref('stock.action_picking_tree_all').sudo().read()[0]

        # Filtramos por nuestra solicitud y ubicación de origen
        action['domain'] = [('stock_request_id', '=', self.id), ('location_id', '=', self.location_id.id)]

        # Usamos safe_eval pasando el contexto actual para que reconozca 'allowed_company_ids'
        eval_context = self.env.context.copy()

        # Obtenemos el contexto actual de la acción (si existe) y le añadimos el bloqueo de creación
        context = eval(action.get('context', '{}'), eval_context)
        context.update({
            'create': False,  # Esto elimina el botón "Nuevo" o "Crear"
        })
        action['context'] = context

        return action

    def action_view_incoming(self):
        self.ensure_one()
        # Leemos la acción estándar
        action = self.env.ref('stock.action_picking_tree_all').sudo().read()[0]

        # Filtramos por nuestra solicitud y ubicación de destino
        action['domain'] = [('stock_request_id', '=', self.id), ('location_dest_id', '=', self.location_dest_id.id)]

        # Usamos safe_eval pasando el contexto actual para que reconozca 'allowed_company_ids'
        eval_context = self.env.context.copy()

        # Obtenemos el contexto actual y añadimos el bloqueo de creación
        context = eval(action.get('context', '{}'), eval_context)
        context.update({
            'create': False,  # Esto elimina el botón "Nuevo" o "Crear"
        })
        action['context'] = context

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

