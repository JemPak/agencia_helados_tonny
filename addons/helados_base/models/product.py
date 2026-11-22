from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _escapar_like(valor):
    return valor.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.constrains("list_price")
    def _check_list_price_no_negativo(self):
        for template in self:
            if template.list_price < 0:
                raise ValidationError(
                    _("El precio de venta de «%s» no puede ser negativo.", template.name)
                )


class ProductProduct(models.Model):
    _inherit = "product.product"

    qty_cava = fields.Float(
        string="Cantidad en Cava",
        compute="_compute_qty_cava",
        digits="Product Unit",
        help="Unidades disponibles físicamente en la Cava (no incluye Local ni vehículos).",
    )

    def _compute_qty_cava(self):
        cava = self.env.ref("stock.stock_location_stock", raise_if_not_found=False)
        if not cava:
            self.qty_cava = 0.0
            return
        en_cava = self.with_context(location=cava.id)
        for product, product_cava in zip(self, en_cava):
            product.qty_cava = product_cava.qty_available

    @api.constrains("default_code")
    def _check_default_code_unico(self):
        """El código del producto es único, sin distinguir mayúsculas ni espacios
        y contando también los productos archivados."""
        for product in self.filtered("default_code"):
            codigo = product.default_code.strip()
            duplicado = self.with_context(active_test=False).search([
                ("id", "!=", product.id),
                ("default_code", "=ilike", _escapar_like(codigo)),
            ], limit=1)
            if duplicado:
                raise ValidationError(_(
                    "Ya existe un producto con el código «%(codigo)s»: %(producto)s.",
                    codigo=codigo,
                    producto=duplicado.display_name,
                ))
