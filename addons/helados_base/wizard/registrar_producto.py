from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..models.product import _escapar_like


class RegistrarProducto(models.TransientModel):
    """HU01 – Registrar un producto del catálogo con su stock inicial en la Cava."""

    _name = "helados.registrar.producto"
    _description = "Registrar producto con stock inicial"

    default_code = fields.Char(string="Código", required=True)
    name = fields.Char(string="Nombre", required=True)
    categ_id = fields.Many2one(
        "product.category",
        string="Categoría",
        required=True,
        default=lambda self: self.env.ref(
            "helados_base.categoria_helados", raise_if_not_found=False
        ),
    )
    list_price = fields.Float(string="Precio de venta", required=True, digits="Product Price")
    cantidad_inicial = fields.Float(
        string="Cantidad inicial en Cava", required=True, digits="Product Unit"
    )

    @api.model
    def _cava(self):
        return self.env.ref("stock.stock_location_stock")

    def _validar(self):
        self.ensure_one()
        errores = []
        codigo = (self.default_code or "").strip()
        if not codigo:
            errores.append(_("El código es obligatorio."))
        elif self.env["product.product"].with_context(active_test=False).search_count(
            [("default_code", "=ilike", _escapar_like(codigo))],
            limit=1,
        ):
            errores.append(_("Ya existe un producto con el código «%s».", codigo))
        if not (self.name or "").strip():
            errores.append(_("El nombre es obligatorio."))
        if self.list_price < 0:
            errores.append(_("El precio de venta no puede ser negativo."))
        if self.cantidad_inicial < 0:
            errores.append(_("La cantidad inicial no puede ser negativa."))
        if errores:
            raise ValidationError("\n".join(errores))

    def _crear_producto(self):
        """Crea el producto y aplica el ajuste de inventario inicial en la Cava."""
        self._validar()
        template = self.env["product.template"].create({
            "name": self.name.strip(),
            "default_code": self.default_code.strip(),
            "categ_id": self.categ_id.id,
            "list_price": self.list_price,
            "type": "consu",
            "is_storable": True,
        })
        if self.cantidad_inicial:
            quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
                "product_id": template.product_variant_id.id,
                "location_id": self._cava().id,
                "inventory_quantity": self.cantidad_inicial,
            })
            quant.action_apply_inventory()
        return template

    def action_registrar(self):
        template = self._crear_producto()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("Producto guardado correctamente"),
                "message": _(
                    "[%(codigo)s] %(nombre)s – %(cantidad)s unidades registradas en la Cava.",
                    codigo=template.default_code,
                    nombre=template.name,
                    cantidad=self.cantidad_inicial,
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    @api.model
    def _cargar_catalogo(self, filas):
        """Registra varios productos a la vez. Lo usan los datos de demostración.

        `filas`: lista de tuplas (código, nombre, xmlid de categoría, precio, cantidad).
        Omite los códigos que ya existen, para poder ejecutarse más de una vez.
        """
        Product = self.env["product.product"].with_context(active_test=False)
        for codigo, nombre, categoria, precio, cantidad in filas:
            if Product.search_count([("default_code", "=", codigo)], limit=1):
                continue
            self.create({
                "default_code": codigo,
                "name": nombre,
                "categ_id": self.env.ref(categoria).id,
                "list_price": precio,
                "cantidad_inicial": cantidad,
            })._crear_producto()
