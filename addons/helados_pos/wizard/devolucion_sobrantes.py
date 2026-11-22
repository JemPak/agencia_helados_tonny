from odoo import api, fields, models
from odoo.exceptions import UserError


class DevolucionSobrantes(models.TransientModel):
    """HU04 escenario 3: devolver a la Cava lo que no se vendió y registrar lo que falta."""

    _name = "helados.devolucion.sobrantes"
    _description = "Devolución de sobrantes a la Cava"

    session_id = fields.Many2one("pos.session", required=True, readonly=True)
    ubicacion_id = fields.Many2one(related="session_id.config_id.ubicacion_id", string="Vehículo")
    linea_ids = fields.One2many("helados.devolucion.sobrantes.linea", "wizard_id", string="Productos")

    @api.model
    def _crear_para_sesion(self, session):
        """Una línea por producto con existencias en el vehículo; lo esperado es lo
        que dice Odoo que queda (cargado − vendido) y se propone devolverlo todo."""
        lineas = {}
        for quant in session._helados_stock_en_vehiculo():
            lineas.setdefault(quant.product_id, 0.0)
            lineas[quant.product_id] += quant.quantity
        return self.create({
            "session_id": session.id,
            "linea_ids": [
                (0, 0, {"product_id": product.id, "esperado": qty, "devuelto": qty})
                for product, qty in lineas.items()
            ],
        })

    def action_confirmar(self):
        self.ensure_one()
        session = self.session_id
        if session.sobrantes_registrados:
            raise UserError(self.env._("Los sobrantes de esta sesión ya fueron registrados."))
        for linea in self.linea_ids:
            if linea.devuelto < 0 or linea.product_id.uom_id.compare(linea.devuelto, linea.esperado) > 0:
                raise UserError(self.env._(
                    "%(producto)s: lo devuelto (%(devuelto)s) debe estar entre 0 y lo esperado (%(esperado)s).",
                    producto=linea.product_id.display_name, devuelto=linea.devuelto, esperado=linea.esperado,
                ))

        env = self.env(su=True)
        vehiculo = self.ubicacion_id
        cava = env.ref("stock.stock_location_stock")
        warehouse = env.ref("stock.warehouse0")

        # Pedidos a domicilio no entregados: liberar su reserva en el vehículo para
        # que la mercancía pueda volver a la Cava (la entrega queda pendiente).
        env["stock.picking"].search([
            ("location_id", "=", vehiculo.id),
            ("picking_type_code", "=", "outgoing"),
            ("state", "=", "assigned"),
        ]).do_unreserve()

        devolucion = env["stock.picking"]
        a_devolver = self.linea_ids.filtered(lambda l: l.devuelto > 0)
        if a_devolver:
            devolucion = env["stock.picking"].create({
                "picking_type_id": warehouse.int_type_id.id,
                "location_id": vehiculo.id,
                "location_dest_id": cava.id,
                "origin": session.name,
                "move_ids": [(0, 0, {
                    "product_id": linea.product_id.id,
                    "product_uom_qty": linea.devuelto,
                    "product_uom": linea.product_id.uom_id.id,
                    "location_id": vehiculo.id,
                    "location_dest_id": cava.id,
                }) for linea in a_devolver],
            })
            devolucion.action_confirm()
            devolucion.action_assign()
            for move in devolucion.move_ids:
                move.quantity = move.product_uom_qty
            devolucion.move_ids.picked = True
            devolucion.with_context(skip_backorder=True, cancel_backorder=True).button_validate()

        # Lo que no volvió se registra como faltante a nombre del responsable de la
        # sesión y se da de baja del vehículo, que queda en cero.
        faltantes = []
        for linea in self.linea_ids.filtered(lambda l: l.faltante > 0):
            faltantes.append({
                "session_id": session.id,
                "repartidor_id": session.user_id.id,
                "product_id": linea.product_id.id,
                "esperado": linea.esperado,
                "devuelto": linea.devuelto,
                "cantidad": linea.faltante,
                "precio_unitario": linea.product_id.lst_price,
            })
        env["helados.faltante"].create(faltantes)
        restantes = env["stock.quant"].search([("location_id", "=", vehiculo.id), ("quantity", ">", 0)])
        if restantes:
            restantes.with_context(inventory_mode=True).write({"inventory_quantity": 0, "inventory_quantity_set": True})
            restantes.with_context(inventory_name=self.env._("Faltante %s", session.name)).action_apply_inventory()

        session.sudo().write({"sobrantes_registrados": True, "devolucion_picking_id": devolucion.id})
        if faltantes:
            session.sudo().message_post(body=self.env._(
                "Devolución de sobrantes con faltantes por %s.",
                session.currency_id.format(session.faltante_valor),
            ))
        return {"type": "ir.actions.act_window_close"}


class DevolucionSobrantesLinea(models.TransientModel):
    _name = "helados.devolucion.sobrantes.linea"
    _description = "Línea de devolución de sobrantes"

    wizard_id = fields.Many2one("helados.devolucion.sobrantes", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Producto", required=True, readonly=True)
    esperado = fields.Float(digits="Product Unit", readonly=True)
    devuelto = fields.Float(digits="Product Unit")
    faltante = fields.Float(compute="_compute_faltante", digits="Product Unit")

    @api.depends("esperado", "devuelto")
    def _compute_faltante(self):
        for linea in self:
            linea.faltante = max(linea.esperado - linea.devuelto, 0.0)
