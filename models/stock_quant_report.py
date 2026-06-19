from odoo import api, fields, models, tools

class StockQuantReport(models.Model):
    _name = "stock.quant.report"
    _description = "Stock quant report"
    _auto = False
    
    quant_id = fields.Many2one(comodel_name='stock.quant', string='Cantidad',readonly=True)
    product_id = fields.Many2one(comodel_name='product.product', string='Producto',readonly=True)
    product_tmpl_id = fields.Many2one(comodel_name='product.template', string='Plantilla de producto', readonly=True)
    categ_id = fields.Many2one(comodel_name='product.category', string='Categoria', readonly=True)
    product_uom_id = fields.Many2one(comodel_name='uom.uom', string='Unidad', readonly=True)
    company_id = fields.Many2one(comodel_name='res.company', string='Empresa', readonly=True)
    location_id = fields.Many2one(comodel_name='stock.location', string='Ubicacion', readonly=True)
    lot_id = fields.Many2one(comodel_name='stock.lot', string='Num. Serie', readonly=True)
    owner_id = fields.Many2one(comodel_name='res.partner', string='Propietario', readonly=True)
    quantity = fields.Float(string='Existencia', readonly=True, digits='Product Unit of Measure')
    reserved_quantity = fields.Float(string='Reservado', readonly=True, digits='Product Unit of Measure')
    forecast_quantity = fields.Float(string='Pronosticado', readonly=True, digits='Product Unit of Measure')
    tracking = fields.Char(string="Seguimiento", readonly=True)
    barcode = fields.Char(string='Código de barras', readonly=True)
    default_code = fields.Char(string='Código', readonly=True)

    value = fields.Float(string='Costo', groups='stock.group_stock_manager', group_operator='avg')
    value_sum = fields.Float(string='Costo total', groups='stock.group_stock_manager')

    zarah_negj_price = fields.Float(string=u'Precio x unidad venta', groups='stock.group_stock_manager')
    zarah_niit_price = fields.Float(string=u'Total precio de venta', groups='stock.group_stock_manager')
    bohir_ashig = fields.Float(string=u'Margen ganacia', groups='stock.group_stock_manager')

    def _select(self):
        return """
            SELECT
                sq.id as id,
                sq.id as quant_id,
                sq.product_id,
                pp.product_tmpl_id,
                pt.uom_id as product_uom_id,
                sq.company_id,
                sq.location_id,
                sq.lot_id,
                sq.owner_id,
                sq.quantity,
                sq.reserved_quantity,
                sq.quantity-sq.reserved_quantity as forecast_quantity,
                pt.tracking,
                pp.barcode,
                pp.default_code,
                pt.categ_id,
                ip.value_float as value
                ,sq.quantity*ip.value_float as value_sum
                ,pt.list_price as zarah_negj_price
                ,sq.quantity*pt.list_price as zarah_niit_price
                ,(sq.quantity*pt.list_price)-(sq.quantity*ip.value_float) as bohir_ashig
        """

    def _from(self):
        return """
            FROM stock_quant AS sq
            LEFT JOIN product_product pp ON (pp.id=sq.product_id)
            LEFT JOIN product_template pt ON (pp.product_tmpl_id=pt.id)
            LEFT JOIN stock_location sl ON (sl.id=sq.location_id)
            LEFT JOIN ir_property as ip on (ip.res_id = 'product.product,'||sq.product_id and ip.name = 'standard_price' and sq.company_id=ip.company_id)
        """

    def _group_by(self):
        return """
            
        """

    def _having(self):
        return """
           
        """

    def _where(self):
        return """"""

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                %s
                %s
                %s
                %s
                %s
            )
        """ % (self._table, self._select(), self._from(), self._where(), self._group_by(),self._having())
        )

    def reserved_quantity_view(self):
        sml_ids = self.env['stock.move.line'].search([
                ('product_id','=',self.product_id.id),
                ('location_id','=',self.location_id.id),
                ('lot_id','=',self.lot_id.id),
                ('state','not in',['done','cancel']),
                ('quantity','>',0)
                ])
        return self.view_reserved_quantity_sml(sml_ids)

    def view_reserved_quantity_sml(self, sml_ids):
        context = {'create': False, 'edit': False}
        tree_view_id = self.env.ref('stock.view_move_line_tree').id
        form_view_id = self.env.ref('stock.view_move_line_form').id
        action = {
                'name': 'Reserved',
                'res_model': 'stock.move.line',
                'views': [(tree_view_id, 'tree'),(form_view_id,'form')],
                'view_id': tree_view_id,
                'domain': [('id','in',sml_ids.ids)],
                'type': 'ir.actions.act_window',
                'context': context,
                'target': 'current'
            }
        return action

    def action_view_stock_moves(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("stock.stock_move_line_action")
        action['domain'] = [
            ('product_id', '=', self.product_id.id),
            ('location_id', '=', self.location_id.id)
        ]
        action['context'] = {
            'search_default_done': 1,
            'create': False,
            'edit': False
        }
        return action