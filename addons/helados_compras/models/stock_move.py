from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        moves._helados_reabastecer_cava()
        return moves

    def _helados_reabastecer_cava(self):
        """HU02 escenario 1: cuando sale producto de la Cava, revisar de inmediato
        sus reglas de mínimo/máximo en lugar de esperar al planificador diario.

        Si las existencias previstas quedan por debajo del mínimo, Odoo crea (o
        completa) la solicitud de presupuesto al proveedor hasta llegar al
        máximo. Las cantidades ya pedidas cuentan en el previsto, así que no se
        duplican pedidos.
        """
        cava = self.env.ref("stock.stock_location_stock", raise_if_not_found=False)
        if not cava:
            return
        salidas = self.filtered(
            lambda m: m.state == "done"
            and m.location_id._child_of(cava)
            and not m.location_dest_id._child_of(cava)
        )
        if not salidas:
            return
        orderpoints = self.env["stock.warehouse.orderpoint"].sudo().search([
            ("product_id", "in", salidas.product_id.ids),
            ("location_id", "=", cava.id),
            ("trigger", "=", "auto"),
        ])
        if not orderpoints:
            return
        orderpoints._compute_qty_to_order_computed()
        for company in orderpoints.company_id:
            orderpoints.filtered(lambda o: o.company_id == company)._procure_orderpoint_confirm(
                company_id=company.id, raise_user_error=False,
            )
