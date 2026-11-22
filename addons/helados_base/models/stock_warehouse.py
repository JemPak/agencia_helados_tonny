from odoo import api, models

# (xmlid, nombre, xmlid del padre o None = ubicación vista del almacén, uso)
UBICACIONES = [
    ("location_local", "Local", None, "internal"),
    ("location_vehiculos", "Vehículos", None, "view"),
    ("location_camion", "Camión", "location_vehiculos", "internal"),
    ("location_moto_1", "Moto 1", "location_vehiculos", "internal"),
    ("location_moto_2", "Moto 2", "location_vehiculos", "internal"),
]


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    @api.model
    def _helados_configurar_ubicaciones(self):
        """Crea la estructura de ubicaciones de la agencia en el almacén principal.

        Almacén
        ├── Cava       (ubicación de stock del almacén, renombrada)
        ├── Local
        └── Vehículos  (vista)
            ├── Camión
            ├── Moto 1
            └── Moto 2

        Es idempotente: si una ubicación ya tiene su xmlid, no se vuelve a crear.
        """
        warehouse = self.env.ref("stock.warehouse0", raise_if_not_found=False)
        if not warehouse:
            return
        warehouse.lot_stock_id.name = "Cava"

        IrModelData = self.env["ir.model.data"]
        for xmlid, nombre, padre_xmlid, uso in UBICACIONES:
            if self.env.ref(f"helados_base.{xmlid}", raise_if_not_found=False):
                continue
            padre = (
                self.env.ref(f"helados_base.{padre_xmlid}")
                if padre_xmlid
                else warehouse.view_location_id
            )
            ubicacion = self.env["stock.location"].create({
                "name": nombre,
                "usage": uso,
                "location_id": padre.id,
                "company_id": warehouse.company_id.id,
            })
            IrModelData.create({
                "module": "helados_base",
                "name": xmlid,
                "model": "stock.location",
                "res_id": ubicacion.id,
                "noupdate": True,
            })
