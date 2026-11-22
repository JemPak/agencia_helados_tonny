from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _helados_configurar_compras(self, proveedor_id, reglas):
        """Configura compra y reabastecimiento de los productos del catálogo.

        La ruta Comprar no se asigna por producto: en Odoo 19 se activa para todo
        el almacén (`buy_to_resupply`, ya activo en el almacén principal).

        Para cada (código, mínimo, máximo) en `reglas`:
        - registra a `proveedor_id` como proveedor, con el precio de compra
          (`standard_price`) del producto, si aún no lo tiene;
        - crea la regla de stock mínimo/máximo en la Cava, si aún no existe.
        """
        cava = self.env.ref("stock.stock_location_stock")
        warehouse = self.env.ref("stock.warehouse0")
        Orderpoint = self.env["stock.warehouse.orderpoint"].with_context(active_test=False)

        for codigo, minimo, maximo in reglas:
            product = self.env["product.product"].search([("default_code", "=", codigo)], limit=1)
            if not product:
                continue
            template = product.product_tmpl_id
            if not template.seller_ids.filtered(lambda s: s.partner_id.id == proveedor_id):
                self.env["product.supplierinfo"].create({
                    "partner_id": proveedor_id,
                    "product_tmpl_id": template.id,
                    "price": template.standard_price,
                    "min_qty": 1,
                    "delay": 1,
                })
            if not Orderpoint.search_count([
                ("product_id", "=", product.id), ("location_id", "=", cava.id),
            ], limit=1):
                Orderpoint.create({
                    "product_id": product.id,
                    "warehouse_id": warehouse.id,
                    "location_id": cava.id,
                    "product_min_qty": minimo,
                    "product_max_qty": maximo,
                    "trigger": "auto",
                })
