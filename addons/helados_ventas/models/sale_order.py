from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    repartidor_id = fields.Many2one(
        "res.users",
        string="Repartidor",
        domain=[("share", "=", False)],
        tracking=True,
        copy=False,
    )
    vehiculo_id = fields.Many2one(
        "stock.location",
        string="Vehículo",
        domain=lambda self: self._domain_vehiculo(),
        tracking=True,
        copy=False,
    )
    municipio_entrega = fields.Char(
        string="Municipio de entrega",
        related="partner_shipping_id.city",
        store=True,
    )

    @api.model
    def _domain_vehiculo(self):
        vehiculos = self.env.ref("helados_base.location_vehiculos", raise_if_not_found=False)
        if not vehiculos:
            return [("id", "=", False)]
        return [("id", "child_of", vehiculos.id), ("usage", "=", "internal")]

    # --- HU03 escenario 2: no comprometer productos sin existencias ------------

    def _helados_faltantes_en_cava(self):
        """Devuelve [(producto, pedido, disponible)] de las líneas que piden más de
        lo que hay libre (sin reservar) en la Cava."""
        self.ensure_one()
        cava = self.env.ref("stock.stock_location_stock")
        pedido_por_producto = {}
        for line in self.order_line.filtered(lambda l: l.product_id.is_storable):
            qty = line.product_uom_id._compute_quantity(line.product_uom_qty, line.product_id.uom_id)
            pedido_por_producto[line.product_id] = pedido_por_producto.get(line.product_id, 0.0) + qty
        faltantes = []
        for product, pedido in pedido_por_producto.items():
            disponible = product.with_context(location=cava.id).free_qty
            if product.uom_id.compare(pedido, disponible) > 0:
                faltantes.append((product, pedido, disponible))
        return faltantes

    def action_confirm(self):
        for order in self:
            faltantes = order._helados_faltantes_en_cava()
            if faltantes:
                detalle = "\n".join(
                    self.env._("• %(producto)s: pedido %(pedido)s, disponible en Cava %(disponible)s",
                      producto=p.display_name, pedido=pedido, disponible=disponible)
                    for p, pedido, disponible in faltantes
                )
                raise UserError(self.env._(
                    "No se puede confirmar %(pedido)s: no hay existencias suficientes en la Cava.\n%(detalle)s",
                    pedido=order.name, detalle=detalle,
                ))
        res = super().action_confirm()
        self._helados_aplicar_ruta()
        return res

    # --- HU03 escenario 1: asignar repartidor y vehículo -----------------------

    def write(self, vals):
        if "vehiculo_id" in vals:
            cargados = self.filtered(lambda o: o._helados_cargues().filtered(lambda p: p.state == "done"))
            if cargados:
                raise UserError(self.env._(
                    "No se puede cambiar el vehículo de %s: la mercancía ya fue cargada.",
                    ", ".join(cargados.mapped("name")),
                ))
        res = super().write(vals)
        if {"vehiculo_id", "repartidor_id"} & set(vals):
            self._helados_aplicar_ruta()
        return res

    def _helados_cargues(self):
        self.ensure_one()
        return self.picking_ids.filtered(
            lambda p: p.picking_type_id == self.warehouse_id.pick_type_id
        )

    def _helados_entregas(self):
        self.ensure_one()
        return self.picking_ids.filtered(
            lambda p: p.picking_type_id == self.warehouse_id.out_type_id
        )

    def _helados_aplicar_ruta(self):
        """Lleva el repartidor y el vehículo del pedido a sus transferencias:
        el cargue termina en el vehículo y la entrega sale del vehículo.

        En Odoo 19 la entrega (segundo paso) se crea al validar el cargue, así
        que esto se llama al confirmar, al cambiar repartidor/vehículo y después
        de cada cargue."""
        for order in self.filtered(lambda o: o.state == "sale"):
            abiertos = order.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
            abiertos.write({
                "repartidor_id": order.repartidor_id.id,
                "vehiculo_id": order.vehiculo_id.id,
            })
            if not order.vehiculo_id:
                continue
            vehiculo = order.vehiculo_id
            for cargue in order._helados_cargues().filtered(lambda p: p.state not in ("done", "cancel")):
                cargue.location_dest_id = vehiculo
                cargue.move_ids.write({"location_dest_id": vehiculo.id})
                cargue.move_ids.move_line_ids.write({"location_dest_id": vehiculo.id})
            for entrega in order._helados_entregas().filtered(lambda p: p.state not in ("done", "cancel")):
                entrega.location_id = vehiculo
                entrega.move_ids.write({"location_id": vehiculo.id})


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.onchange("product_id", "product_uom_qty", "product_uom_id")
    def _onchange_helados_disponibilidad_cava(self):
        """HU03 escenario 2: advertir al digitar una cantidad mayor a la libre en la Cava."""
        if not (self.product_id and self.product_id.is_storable and self.product_uom_id):
            return
        cava = self.env.ref("stock.stock_location_stock", raise_if_not_found=False)
        if not cava:
            return
        product = self.product_id
        pedido = sum(
            line.product_uom_id._compute_quantity(line.product_uom_qty, product.uom_id)
            for line in self.order_id.order_line
            if line.product_id == product and line.product_uom_id
        )
        disponible = product.with_context(location=cava.id).free_qty
        if product.uom_id.compare(pedido, disponible) > 0:
            return {"warning": {
                "title": self.env._("Existencias insuficientes en la Cava"),
                "message": self.env._(
                    "%(producto)s: se piden %(pedido)s y hay %(disponible)s disponibles en la Cava. "
                    "El pedido no se podrá confirmar con esta cantidad.",
                    producto=product.display_name, pedido=pedido, disponible=disponible,
                ),
            }}
