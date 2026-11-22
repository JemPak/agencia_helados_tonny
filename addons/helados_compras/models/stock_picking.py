from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    validado_por_id = fields.Many2one(
        "res.users",
        string="Validado por",
        readonly=True,
        copy=False,
        help="Usuario que validó la transferencia (p. ej. el bodeguero que recibió la mercancía).",
    )

    def _action_done(self):
        res = super()._action_done()
        self.filtered(lambda p: p.state == "done").write({"validado_por_id": self.env.uid})
        return res
