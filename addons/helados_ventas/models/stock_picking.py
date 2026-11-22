from odoo import fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    repartidor_id = fields.Many2one("res.users", string="Repartidor", copy=False, index=True)
    vehiculo_id = fields.Many2one("stock.location", string="Vehículo", copy=False, index=True)
    municipio_entrega = fields.Char(related="sale_id.municipio_entrega", string="Municipio")

    def button_validate(self):
        sin_vehiculo = self.filtered(
            lambda p: p.sale_id
            and p.picking_type_id == p.picking_type_id.warehouse_id.pick_type_id
            and not p.vehiculo_id
        )
        if sin_vehiculo:
            raise UserError(self.env._(
                "Asigne un vehículo al pedido antes de validar el cargue: %s",
                ", ".join(sin_vehiculo.mapped("name")),
            ))
        return super().button_validate()

    def _action_done(self):
        res = super()._action_done()
        # El cargue validado genera la entrega: pasarle repartidor y vehículo.
        self.sale_id._helados_aplicar_ruta()
        return res
