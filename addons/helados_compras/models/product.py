import math

from odoo import api, fields, models

# Demanda mensual (unidades) entregada por la agencia, en el orden de su catálogo.
DEMANDA_INICIAL = {
    "LIT-18": 120, "LIT-10": 129, "LIT-05": 66, "CON-BIC": 120,
    "VAS-JUN": 102, "CON-KON": 165, "VAS-DER": 144, "VAS-GCI": 180,
    "CON-KMA": 105, "GAL-GAL": 105, "PAL-VAL": 72, "PAL-IRI": 165,
    "PAL-CHO": 72, "TUR-TUR": 84, "TUR-TCI": 84, "TUR-CRE": 75,
}

# Parámetros del cálculo (Ajustes > Técnico > Parámetros del sistema)
PARAMETROS = {
    "helados_compras.dias_mes": 30,        # días con venta en el mes
    "helados_compras.dias_entrega": 3,     # días que tarda Tonny en entregar
    "helados_compras.dias_seguridad": 2,   # colchón para picos de demanda
    "helados_compras.dias_ciclo": 7,       # cada cuánto se hace un pedido
}


class ProductTemplate(models.Model):
    _inherit = "product.template"

    demanda_mensual = fields.Float(
        string="Demanda mensual",
        digits="Product Unit",
        help="Unidades que la agencia vende en un mes. Con ella se calculan el "
             "mínimo y el máximo de la regla de reabastecimiento en la Cava.",
    )

    @api.model
    def _helados_parametro(self, clave):
        valor = self.env["ir.config_parameter"].sudo().get_param(clave)
        return float(valor) if valor else float(PARAMETROS[clave])

    def _helados_calcular_min_max(self):
        """Mínimo = demanda diaria × (días de entrega + días de seguridad).
        Máximo = mínimo + demanda diaria × días del ciclo de pedido.
        Se redondea hacia arriba a unidades completas."""
        self.ensure_one()
        diaria = self.demanda_mensual / self._helados_parametro("helados_compras.dias_mes")
        cobertura = (self._helados_parametro("helados_compras.dias_entrega")
                     + self._helados_parametro("helados_compras.dias_seguridad"))
        ciclo = self._helados_parametro("helados_compras.dias_ciclo")
        # round() evita que errores de coma flotante (20.000000000004) suban una unidad
        return (math.ceil(round(diaria * cobertura, 6)),
                math.ceil(round(diaria * (cobertura + ciclo), 6)))

    def action_helados_recalcular_reglas(self):
        """Recalcula mínimo y máximo de la regla en la Cava según la demanda mensual."""
        cava = self.env.ref("stock.stock_location_stock")
        Orderpoint = self.env["stock.warehouse.orderpoint"]
        for template in self.filtered("demanda_mensual"):
            minimo, maximo = template._helados_calcular_min_max()
            reglas = Orderpoint.search([
                ("product_id", "in", template.product_variant_ids.ids),
                ("location_id", "=", cava.id),
            ])
            reglas.write({"product_min_qty": minimo, "product_max_qty": maximo})

    @api.model
    def _helados_cargar_demanda_inicial(self):
        for codigo, demanda in DEMANDA_INICIAL.items():
            product = self.env["product.product"].search([("default_code", "=", codigo)], limit=1)
            if product:
                product.product_tmpl_id.demanda_mensual = demanda
        self.search([("demanda_mensual", ">", 0)]).action_helados_recalcular_reglas()

    @api.model
    def _helados_configurar_compras(self, proveedor_id):
        """Configura compra y reabastecimiento de los productos del catálogo.

        La ruta Comprar no se asigna por producto: en Odoo 19 se activa para todo
        el almacén (`buy_to_resupply`, ya activo en el almacén principal).

        Para cada producto con demanda inicial:
        - registra a `proveedor_id` como proveedor, con el precio de compra
          (`standard_price`) del producto, si aún no lo tiene;
        - crea la regla de reabastecimiento en la Cava, si aún no existe;
        - carga la demanda mensual y calcula mínimo y máximo.
        """
        cava = self.env.ref("stock.stock_location_stock")
        warehouse = self.env.ref("stock.warehouse0")
        Orderpoint = self.env["stock.warehouse.orderpoint"].with_context(active_test=False)

        for codigo in DEMANDA_INICIAL:
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
                    "product_min_qty": 0,
                    "product_max_qty": 0,
                    "trigger": "auto",
                })
        self._helados_cargar_demanda_inicial()
