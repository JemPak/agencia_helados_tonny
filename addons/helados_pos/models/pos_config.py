from odoo import api, fields, models

# (xmlid de la ubicación, nombre del PdV, código corto)
PUNTOS_DE_VENTA = [
    ("helados_base.location_camion", "Camión", "CAM"),
    ("helados_base.location_moto_1", "Moto 1", "MO1"),
    ("helados_base.location_moto_2", "Moto 2", "MO2"),
    ("helados_base.location_local", "Local", "LOC"),
]
TOPE_DIFERENCIA_CAJA = 5000


class PosConfig(models.Model):
    _inherit = "pos.config"

    ubicacion_id = fields.Many2one(
        "stock.location",
        string="Ubicación de venta",
        related="picking_type_id.default_location_src_id",
        help="Ubicación de la que salen los productos vendidos en este Punto de Venta.",
    )
    es_vehiculo = fields.Boolean(compute="_compute_es_vehiculo")

    @api.depends("ubicacion_id")
    def _compute_es_vehiculo(self):
        vehiculos = self.env.ref("helados_base.location_vehiculos", raise_if_not_found=False)
        for config in self:
            config.es_vehiculo = bool(
                vehiculos and config.ubicacion_id and config.ubicacion_id._child_of(vehiculos)
            )

    @api.model
    def _helados_configurar_puntos_venta(self):
        company = self.env.company
        # En una base nueva el plan de cuentas se carga al final de la instalación
        # y borra los diarios creados antes (con sus cajas y Puntos de Venta).
        # Se carga aquí primero; si ya existe (p. ej. l10n_co), no se toca.
        if not company.chart_template:
            ChartTemplate = self.env["account.chart.template"]
            ChartTemplate.try_loading(
                ChartTemplate._guess_chart_template(company.country_id), company, install_demo=False,
            )
        warehouse = self.env.ref("stock.warehouse0")
        clientes = self.env.ref("stock.stock_location_customers")
        IrModelData = self.env["ir.model.data"]

        for ubicacion_xmlid, nombre, codigo in PUNTOS_DE_VENTA:
            slug = ubicacion_xmlid.split(".location_")[1]
            if self.env.ref(f"helados_pos.pos_config_{slug}", raise_if_not_found=False):
                continue
            ubicacion = self.env.ref(ubicacion_xmlid)
            tipo = self.env["stock.picking.type"].create({
                "name": f"PdV {nombre}",
                "code": "outgoing",
                "sequence_code": f"PDV-{codigo}",
                "warehouse_id": warehouse.id,
                "company_id": company.id,
                "default_location_src_id": ubicacion.id,
                "default_location_dest_id": clientes.id,
            })
            diario = self.env["account.journal"].create({
                "name": f"Efectivo {nombre}",
                "type": "cash",
                "code": f"E{codigo}",
                "company_id": company.id,
            })
            metodo = self.env["pos.payment.method"].create({
                "name": f"Efectivo {nombre}",
                "journal_id": diario.id,
                "company_id": company.id,
            })
            config = self.create({
                "name": nombre,
                "company_id": company.id,
                "picking_type_id": tipo.id,
                "payment_method_ids": [(6, 0, metodo.ids)],
                "set_maximum_difference": True,
                "amount_authorized_diff": TOPE_DIFERENCIA_CAJA,
            })
            IrModelData.create({
                "module": "helados_pos", "name": f"pos_config_{slug}",
                "model": "pos.config", "res_id": config.id, "noupdate": True,
            })

        # El catálogo de la agencia se vende en todos los Puntos de Venta
        categoria = self.env.ref("helados_base.categoria_helados", raise_if_not_found=False)
        if categoria:
            self.env["product.template"].search([
                ("categ_id", "child_of", categoria.id),
            ]).write({"available_in_pos": True})
