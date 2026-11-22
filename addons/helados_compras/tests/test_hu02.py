"""Pruebas de aceptación de la HU02 – Reabastecimiento y recepciones."""

from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "hu02")
class TestHU02(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.cava = cls.env.ref("stock.stock_location_stock")
        cls.camion = cls.env.ref("helados_base.location_camion")
        cls.clientes = cls.env.ref("stock.stock_location_customers")
        cls.tonny = cls.env.ref("helados_compras.partner_helados_tonny")
        cls.konito = cls.env["product.product"].search([("default_code", "=", "CON-KON")])
        cls.regla = cls.env["stock.warehouse.orderpoint"].search([
            ("product_id", "=", cls.konito.id), ("location_id", "=", cls.cava.id),
        ])
        cls.regla.write({"product_min_qty": 5, "product_max_qty": 20})
        cls.bodeguero = new_test_user(
            cls.env, login="bodeguero_hu02", groups="stock.group_stock_user",
        )

    # --- utilidades ----------------------------------------------------------

    def _ajustar_cava(self, product, cantidad):
        quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": product.id,
            "location_id": self.cava.id,
            "inventory_quantity": cantidad,
        })
        quant.action_apply_inventory()

    def _sacar_de_cava(self, product, cantidad, destino=None):
        destino = destino or self.clientes
        tipo = self.warehouse.int_type_id if destino.usage == "internal" else self.warehouse.out_type_id
        picking = self.env["stock.picking"].create({
            "picking_type_id": tipo.id,
            "location_id": self.cava.id,
            "location_dest_id": destino.id,
            "move_ids": [(0, 0, {
                "product_id": product.id,
                "product_uom_qty": cantidad,
                "product_uom": product.uom_id.id,
                "location_id": self.cava.id,
                "location_dest_id": destino.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.quantity = cantidad
        picking.move_ids.picked = True
        picking.button_validate()
        return picking

    def _solicitudes_tonny(self, product):
        return self.env["purchase.order.line"].search([
            ("product_id", "=", product.id),
            ("order_id.partner_id", "=", self.tonny.id),
            ("order_id.state", "in", ("draft", "sent")),
        ])

    # --- Configuración ---------------------------------------------------------

    def test_catalogo_configurado_para_compra(self):
        catalogo = self.env["product.product"].search([
            ("categ_id", "child_of", self.env.ref("helados_base.categoria_helados").id),
        ])
        self.assertEqual(len(catalogo), 16)
        self.assertTrue(self.warehouse.buy_to_resupply)
        for product in catalogo:
            proveedor = product.seller_ids.filtered(lambda s: s.partner_id == self.tonny)
            self.assertEqual(proveedor.price, product.standard_price, product.default_code)
            self.assertEqual(
                self.env["stock.warehouse.orderpoint"].search_count([
                    ("product_id", "=", product.id), ("location_id", "=", self.cava.id),
                ]), 1, product.default_code,
            )

    def test_min_max_desde_demanda_mensual(self):
        """Konito: 165/mes -> 5,5 por día. Mínimo 5,5 × (3+2) = 28; máximo 5,5 × 12 = 66."""
        template = self.konito.product_tmpl_id
        self.assertEqual(template.demanda_mensual, 165)
        template.action_helados_recalcular_reglas()
        self.assertEqual((self.regla.product_min_qty, self.regla.product_max_qty), (28, 66))

    def test_recalcula_al_cambiar_parametros(self):
        self.env["ir.config_parameter"].sudo().set_param("helados_compras.dias_ciclo", 14)
        self.konito.product_tmpl_id.action_helados_recalcular_reglas()
        self.assertEqual((self.regla.product_min_qty, self.regla.product_max_qty), (28, 105))

    # --- Escenario 1: solicitud automática por stock mínimo -----------------

    def test_e1_solicitud_automatica_al_bajar_del_minimo(self):
        self._ajustar_cava(self.konito, 12)
        self.assertFalse(self._solicitudes_tonny(self.konito))

        self._sacar_de_cava(self.konito, 8)  # quedan 4 < mínimo 5

        linea = self._solicitudes_tonny(self.konito)
        self.assertEqual(len(linea), 1)
        self.assertEqual(linea.product_qty, 16)  # hasta el máximo: 20 - 4
        self.assertEqual(linea.price_unit, self.konito.standard_price)

    def test_e1_cargue_a_vehiculo_tambien_dispara(self):
        """Pasar mercancía de la Cava al camión también baja las existencias de la Cava."""
        self._ajustar_cava(self.konito, 12)
        self._sacar_de_cava(self.konito, 10, destino=self.camion)  # quedan 2
        self.assertEqual(self._solicitudes_tonny(self.konito).product_qty, 18)

    def test_e1_no_pide_si_sigue_sobre_el_minimo(self):
        self._ajustar_cava(self.konito, 12)
        self._sacar_de_cava(self.konito, 5)  # quedan 7 >= 5
        self.assertFalse(self._solicitudes_tonny(self.konito))

    def test_e1_no_duplica_solicitudes(self):
        self._ajustar_cava(self.konito, 12)
        self._sacar_de_cava(self.konito, 8)  # quedan 4 -> pide 16
        self._sacar_de_cava(self.konito, 1)  # quedan 3, pero hay 16 en camino
        linea = self._solicitudes_tonny(self.konito)
        self.assertEqual(len(linea), 1)
        self.assertEqual(linea.product_qty, 16)

    # --- Escenario 2: confirmar orden de compra --------------------------------

    def _confirmar_orden(self):
        self._ajustar_cava(self.konito, 12)
        self._sacar_de_cava(self.konito, 8)
        orden = self._solicitudes_tonny(self.konito).order_id
        orden.button_confirm()
        return orden

    def test_e2_confirmar_genera_recepcion_pendiente_en_cava(self):
        orden = self._confirmar_orden()
        self.assertEqual(orden.state, "purchase")
        recepcion = orden.picking_ids
        self.assertEqual(len(recepcion), 1)
        self.assertEqual(recepcion.state, "assigned")
        self.assertEqual(recepcion.location_dest_id, self.cava)
        self.assertEqual(recepcion.move_ids.product_uom_qty, 16)

    # --- Escenario 3: registrar recepción en la Cava -----------------------------

    def _recibir(self, orden, cantidad):
        recepcion = orden.picking_ids.filtered(lambda p: p.state == "assigned").with_user(self.bodeguero)
        recepcion.move_ids.quantity = cantidad
        recepcion.move_ids.picked = True
        resultado = recepcion.button_validate()
        if isinstance(resultado, dict) and resultado.get("res_model") == "stock.backorder.confirmation":
            self.env["stock.backorder.confirmation"].with_user(self.bodeguero).with_context(
                resultado["context"]
            ).create({}).process()
        return recepcion

    def test_e3_recepcion_suma_a_la_cava_y_registra_responsable(self):
        orden = self._confirmar_orden()
        recepcion = self._recibir(orden, 16)

        self.assertEqual(recepcion.state, "done")
        self.assertEqual(self.konito.qty_cava, 4 + 16)
        self.assertEqual(recepcion.partner_id, self.tonny)
        self.assertTrue(recepcion.date_done)
        self.assertEqual(recepcion.validado_por_id, self.bodeguero)
        self.assertEqual(orden.order_line.qty_received, 16)

    def test_e3_recepcion_parcial_deja_pendiente(self):
        """Si Tonny entrega menos de lo pedido, queda una recepción pendiente por la diferencia."""
        orden = self._confirmar_orden()
        self._recibir(orden, 10)

        self.assertEqual(self.konito.qty_cava, 4 + 10)
        self.assertEqual(orden.order_line.qty_received, 10)
        pendiente = orden.picking_ids.filtered(lambda p: p.state == "assigned")
        self.assertEqual(len(pendiente), 1)
        self.assertEqual(pendiente.move_ids.product_uom_qty, 6)
