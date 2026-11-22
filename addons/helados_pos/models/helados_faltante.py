from odoo import api, fields, models


class HeladosFaltante(models.Model):
    """Producto que debía volver a la Cava al cierre de la ruta y no volvió."""

    _name = "helados.faltante"
    _description = "Faltante de producto al cierre de ruta"
    _order = "fecha desc, id desc"

    session_id = fields.Many2one("pos.session", string="Sesión", required=True, ondelete="cascade", index=True)
    config_id = fields.Many2one(related="session_id.config_id", string="Punto de Venta", store=True)
    repartidor_id = fields.Many2one("res.users", string="Responsable", required=True)
    fecha = fields.Datetime(default=fields.Datetime.now, required=True)
    product_id = fields.Many2one("product.product", string="Producto", required=True)
    esperado = fields.Float(digits="Product Unit")
    devuelto = fields.Float(digits="Product Unit")
    cantidad = fields.Float(string="Faltante", digits="Product Unit", required=True)
    precio_unitario = fields.Float(string="Precio de venta", digits="Product Price")
    currency_id = fields.Many2one(related="session_id.currency_id")
    valor = fields.Monetary(compute="_compute_valor", store=True)

    @api.depends("cantidad", "precio_unitario")
    def _compute_valor(self):
        for faltante in self:
            faltante.valor = faltante.cantidad * faltante.precio_unitario
