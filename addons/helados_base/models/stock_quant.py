from odoo import _, api, models
from odoo.exceptions import ValidationError


class StockQuant(models.Model):
    _inherit = "stock.quant"

    @api.constrains("inventory_quantity", "inventory_quantity_set")
    def _check_cantidad_contada_no_negativa(self):
        """Una cantidad contada en un ajuste de inventario no puede ser negativa.

        No se restringe `quantity` (el saldo teórico), que Odoo puede dejar
        negativo de forma legítima al validar movimientos.
        """
        for quant in self:
            if quant.inventory_quantity_set and quant.inventory_quantity < 0:
                raise ValidationError(_(
                    "La cantidad contada de «%(producto)s» en %(ubicacion)s no puede ser negativa.",
                    producto=quant.product_id.display_name,
                    ubicacion=quant.location_id.display_name,
                ))
