from odoo import api, models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    @api.model
    def _helados_configurar_entregas(self):
        warehouse = self.env.ref("stock.warehouse0", raise_if_not_found=False)
        if not warehouse:
            return
        warehouse.delivery_steps = "pick_ship"
        warehouse.pick_type_id.name = "Cargue de vehículo"
        warehouse.out_type_id.name = "Entregas a domicilio"
        # Transferencias internas: cargue extra a vehículos para venta en ruta y
        # devolución de sobrantes a la Cava (HU04).
        warehouse.int_type_id.active = True
        # Los vehículos pasan a estar dentro de la ubicación de salida (WH/Output).
        # Así, al validar el cargue hacia un vehículo, Odoo aplica su regla estándar
        # Salida -> Cliente y crea la entrega desde ese vehículo.
        vehiculos = self.env.ref("helados_base.location_vehiculos", raise_if_not_found=False)
        if vehiculos:
            vehiculos.location_id = warehouse.wh_output_stock_loc_id
