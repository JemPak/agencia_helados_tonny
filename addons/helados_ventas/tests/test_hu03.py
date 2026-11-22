"""Pruebas de aceptación de la HU03 – Pedidos a domicilio y traslado a ruta."""

from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "hu03")
class TestHU03(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.cava = cls.env.ref("stock.stock_location_stock")
        cls.camion = cls.env.ref("helados_base.location_camion")
        cls.moto_1 = cls.env.ref("helados_base.location_moto_1")
        cls.konito = cls.env["product.product"].search([("default_code", "=", "CON-KON")])
        cls.iris = cls.env["product.product"].search([("default_code", "=", "PAL-IRI")])
        cls.cliente = cls.env["res.partner"].create({"name": "Tienda de prueba", "city": "Jardín"})
        cls.repartidor = new_test_user(cls.env, login="repartidor_hu03", groups="base.group_user")
        cls.bodeguero = new_test_user(cls.env, login="bodeguero_hu03", groups="stock.group_stock_user")
        for product, cantidad in ((cls.konito, 20), (cls.iris, 10)):
            quant = cls.env["stock.quant"].with_context(inventory_mode=True).create({
                "product_id": product.id, "location_id": cls.cava.id, "inventory_quantity": cantidad,
            })
            quant.action_apply_inventory()

    # --- utilidades ----------------------------------------------------------

    def _pedido(self, lineas, **valores):
        datos = {
            "partner_id": self.cliente.id,
            "order_line": [(0, 0, {"product_id": p.id, "product_uom_qty": q}) for p, q in lineas],
        }
        datos.update(valores)
        return self.env["sale.order"].create(datos)

    def _libre_en(self, product, ubicacion):
        return product.with_context(location=ubicacion.id).free_qty

    def _a_mano_en(self, product, ubicacion):
        return product.with_context(location=ubicacion.id).qty_available

    def _validar(self, picking, usuario):
        picking = picking.with_user(usuario)
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.move_ids.picked = True
        picking.button_validate()

    # --- Configuración ---------------------------------------------------------

    def test_entregas_en_dos_pasos(self):
        self.assertEqual(self.warehouse.delivery_steps, "pick_ship")
        self.assertTrue(self.warehouse.int_type_id.active)
        self.assertEqual(self.camion.location_id.location_id, self.warehouse.wh_output_stock_loc_id)

    # --- Escenario 1: crear pedido y reservar en la Cava ----------------------

    def test_e1_pedido_reserva_en_cava_y_genera_entrega(self):
        pedido = self._pedido(
            [(self.konito, 5)],
            repartidor_id=self.repartidor.id, vehiculo_id=self.camion.id,
        )
        self.assertEqual(pedido.municipio_entrega, "Jardín")
        pedido.action_confirm()

        cargue = pedido._helados_cargues()
        self.assertEqual(len(cargue), 1)
        # Reserva en la Cava: las unidades siguen ahí pero ya no están libres
        self.assertEqual(cargue.state, "assigned")
        self.assertEqual(cargue.location_id, self.cava)
        self.assertEqual(self._a_mano_en(self.konito, self.cava), 20)
        self.assertEqual(self._libre_en(self.konito, self.cava), 15)
        # Ruta asignada: el cargue termina en el camión
        self.assertEqual(cargue.location_dest_id, self.camion)
        self.assertEqual(cargue.repartidor_id, self.repartidor)
        self.assertEqual(cargue.vehiculo_id, self.camion)
        # La entrega al cliente se genera al cargar y sale del camión
        self._validar(cargue, self.bodeguero)
        entrega = pedido._helados_entregas()
        self.assertEqual(len(entrega), 1)
        self.assertEqual(entrega.location_id, self.camion)
        self.assertEqual(entrega.location_dest_id, self.env.ref("stock.stock_location_customers"))
        self.assertEqual(entrega.repartidor_id, self.repartidor)
        self.assertEqual(entrega.vehiculo_id, self.camion)
        self.assertEqual(entrega.municipio_entrega, "Jardín")

    def test_e1_asignar_o_cambiar_vehiculo_despues_de_confirmar(self):
        pedido = self._pedido([(self.konito, 5)])
        pedido.action_confirm()
        pedido.write({"vehiculo_id": self.moto_1.id, "repartidor_id": self.repartidor.id})

        self.assertEqual(pedido._helados_cargues().location_dest_id, self.moto_1)
        self.assertEqual(pedido._helados_cargues().move_ids.move_line_ids.location_dest_id, self.moto_1)
        self.assertEqual(pedido._helados_cargues().repartidor_id, self.repartidor)

        pedido.vehiculo_id = self.camion
        self.assertEqual(pedido._helados_cargues().location_dest_id, self.camion)

    # --- Escenario 2: falta de stock en la Cava -------------------------------

    def test_e2_advertencia_al_digitar_cantidad_mayor(self):
        with Form(self.env["sale.order"]) as form:
            form.partner_id = self.cliente
            with form.order_line.new() as linea:
                linea.product_id = self.iris
                with self.assertLogs("odoo.tests.form.onchange", level="WARNING") as log:
                    linea.product_uom_qty = 11
            self.assertIn("Existencias insuficientes en la Cava", log.output[0])
            with form.order_line.edit(0) as linea:
                linea.product_uom_qty = 10

    def test_e2_no_confirma_sin_existencias(self):
        pedido = self._pedido([(self.iris, 11)])
        with self.assertRaises(UserError):
            pedido.action_confirm()
        self.assertEqual(pedido.state, "draft")
        self.assertFalse(pedido.picking_ids)

    def test_e2_cuenta_lo_ya_reservado_por_otros_pedidos(self):
        self._pedido([(self.iris, 7)]).action_confirm()
        with self.assertRaises(UserError):
            self._pedido([(self.iris, 4)]).action_confirm()  # libres: 3
        self._pedido([(self.iris, 3)]).action_confirm()

    def test_e2_suma_lineas_repetidas_del_mismo_producto(self):
        with self.assertRaises(UserError):
            self._pedido([(self.iris, 6), (self.iris, 5)]).action_confirm()

    # --- Escenario 3: cargue al vehículo ---------------------------------------

    def test_e3_cargue_descuenta_cava_y_carga_vehiculo(self):
        pedido = self._pedido([(self.konito, 5)], vehiculo_id=self.camion.id)
        pedido.action_confirm()
        self._validar(pedido._helados_cargues(), self.bodeguero)

        self.assertEqual(pedido._helados_cargues().state, "done")
        self.assertEqual(self._a_mano_en(self.konito, self.cava), 15)
        self.assertEqual(self._a_mano_en(self.konito, self.camion), 5)
        # La entrega queda lista para salir del camión
        entrega = pedido._helados_entregas()
        self.assertEqual(entrega.state, "assigned")
        self.assertEqual(entrega.move_ids.move_line_ids.location_id, self.camion)

    def test_e3_no_hay_doble_descuento(self):
        """La unidad sale una sola vez: Cava -> camión -> cliente."""
        total_inicial = self.konito.with_context(warehouse_id=self.warehouse.id).qty_available
        pedido = self._pedido([(self.konito, 5)], vehiculo_id=self.camion.id)
        pedido.action_confirm()
        self._validar(pedido._helados_cargues(), self.bodeguero)
        self._validar(pedido._helados_entregas(), self.bodeguero)

        self.assertEqual(self._a_mano_en(self.konito, self.camion), 0)
        self.assertEqual(self._a_mano_en(self.konito, self.cava), 15)
        self.assertEqual(
            self.konito.with_context(warehouse_id=self.warehouse.id).qty_available,
            total_inicial - 5,
        )
        self.assertEqual(pedido.order_line.qty_delivered, 5)

    def test_e3_no_valida_cargue_sin_vehiculo(self):
        pedido = self._pedido([(self.konito, 5)])
        pedido.action_confirm()
        with self.assertRaises(UserError):
            self._validar(pedido._helados_cargues(), self.bodeguero)

    def test_e3_no_cambia_vehiculo_ya_cargado(self):
        pedido = self._pedido([(self.konito, 5)], vehiculo_id=self.camion.id)
        pedido.action_confirm()
        self._validar(pedido._helados_cargues(), self.bodeguero)
        with self.assertRaises(UserError):
            pedido.vehiculo_id = self.moto_1
