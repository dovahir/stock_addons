# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    to_migrate = fields.Boolean(
        string="Migrar",
        default=False,
        help="Indica si este producto es válido o está marcado para migrar.",
        index=True,
    )
