from odoo import api, fields, models
from odoo.exceptions import UserError


class PosSession(models.Model):
    _inherit = "pos.session"

    sobrantes_registrados = fields.Boolean(string="Sobrantes devueltos", readonly=True, copy=False)
    devolucion_picking_id = fields.Many2one(
        "stock.picking", string="Devolución a la Cava", readonly=True, copy=False,
    )
    faltante_ids = fields.One2many("helados.faltante", "session_id", string="Faltantes")
    faltante_valor = fields.Monetary(
        string="Valor faltante", compute="_compute_faltante_valor", store=True,
    )
    requiere_devolucion = fields.Boolean(compute="_compute_requiere_devolucion")

    @api.depends("faltante_ids.valor")
    def _compute_faltante_valor(self):
        for session in self:
            session.faltante_valor = sum(session.faltante_ids.mapped("valor"))

    def _helados_stock_en_vehiculo(self):
        self.ensure_one()
        ubicacion = self.config_id.ubicacion_id
        return self.env["stock.quant"].sudo().search([
            ("location_id", "=", ubicacion.id),
            ("quantity", ">", 0),
        ])

    @api.depends("config_id", "sobrantes_registrados", "state")
    def _compute_requiere_devolucion(self):
        for session in self:
            session.requiere_devolucion = bool(
                session.config_id.es_vehiculo
                and session.state in ("opened", "closing_control")
                and not session.sobrantes_registrados
                and session._helados_stock_en_vehiculo()
            )

    def _helados_mensaje_devolucion(self):
        return self.env._(
            "Antes de cerrar la caja de %s registre la devolución de sobrantes a la Cava "
            "(botón «Devolver sobrantes» en la sesión).",
            self.config_id.name,
        )

    def action_devolver_sobrantes(self):
        self.ensure_one()
        wizard = self.env["helados.devolucion.sobrantes"]._crear_para_sesion(self)
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Devolver sobrantes"),
            "res_model": "helados.devolucion.sobrantes",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    # --- Cierre -----------------------------------------------------------------

    def _cannot_close_session(self, bank_payment_method_diffs=None):
        res = super()._cannot_close_session(bank_payment_method_diffs)
        if res:
            return res
        if self.requiere_devolucion:
            return {"successful": False, "message": self._helados_mensaje_devolucion(), "redirect": False}
        return res

    def action_pos_session_closing_control(self, balancing_account=False, amount_to_balance=0,
                                           bank_payment_method_diffs=None):
        for session in self:
            if session.requiere_devolucion:
                raise UserError(session._helados_mensaje_devolucion())
        return super().action_pos_session_closing_control(
            balancing_account, amount_to_balance, bank_payment_method_diffs,
        )

    def _validate_session(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        """Odoo solo controla el tope de diferencia de caja en la pantalla del PdV.
        Aquí se controla también en el servidor: si la diferencia supera el tope,
        solo un gerente de Punto de Venta puede cerrar la sesión."""
        config = self.config_id
        if (
            config.cash_control
            and config.set_maximum_difference
            and self.currency_id.compare_amounts(abs(self.cash_register_difference), config.amount_authorized_diff) > 0
            and not self.env.user.has_group("point_of_sale.group_pos_manager")
        ):
            raise UserError(self.env._(
                "La diferencia de caja (%(diferencia)s) supera el tope permitido de %(tope)s. "
                "El cierre debe hacerlo un gerente.",
                diferencia=self.currency_id.format(self.cash_register_difference),
                tope=self.currency_id.format(config.amount_authorized_diff),
            ))
        return super()._validate_session(balancing_account, amount_to_balance, bank_payment_method_diffs)
