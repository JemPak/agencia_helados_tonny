"""Pruebas de aceptación de la HU04 – Ventas y cierre de sesión en el Punto de Venta."""

import uuid

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "hu04")
class TestHU04(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cava = cls.env.ref("stock.stock_location_stock")
        cls.camion = cls.env.ref("helados_base.location_camion")
        cls.config = cls.env.ref("helados_pos.pos_config_camion")
        cls.efectivo = cls.config.payment_method_ids
        cls.konito = cls.env["product.product"].search([("default_code", "=", "CON-KON")])
        cls.iris = cls.env["product.product"].search([("default_code", "=", "PAL-IRI")])
        cls.cliente = cls.env["res.partner"].create({"name": "Tienda de prueba", "city": "Jardín"})
        cls.repartidor = new_test_user(
            cls.env, login="repartidor_hu04",
            groups="point_of_sale.group_pos_user,stock.group_stock_user",
        )
        # 20 en la Cava y el camión cargado con 10 Konito y 5 Paleta Iris
        for product, ubicacion, cantidad in (
            (cls.konito, cls.cava, 20), (cls.konito, cls.camion, 10), (cls.iris, cls.camion, 5),
        ):
            quant = cls.env["stock.quant"].with_context(inventory_mode=True).create({
                "product_id": product.id, "location_id": ubicacion.id, "inventory_quantity": cantidad,
            })
            quant.action_apply_inventory()

    # --- utilidades ----------------------------------------------------------

    def _abrir(self, base=50000, usuario=None):
        config = self.config.with_user(usuario) if usuario else self.config
        config.open_ui()
        session = config.current_session_id
        session.set_opening_control(base, "")
        return session

    def _vender(self, session, lineas, cliente=None, facturar=False, pagado=None):
        """Simula una venta enviada por la pantalla del PdV.
        lineas: [(producto, cantidad)] o [(producto, cantidad, línea de pedido de venta)]"""
        ui_lines, total = [], 0.0
        for linea in lineas:
            product, qty = linea[0], linea[1]
            so_line = linea[2] if len(linea) > 2 else None
            precio = so_line.price_unit if so_line else product.lst_price
            total += precio * qty
            vals = {
                "product_id": product.id, "qty": qty, "price_unit": precio, "discount": 0,
                "price_subtotal": precio * qty, "price_subtotal_incl": precio * qty,
                "tax_ids": [], "pack_lot_ids": [],
            }
            if so_line:
                vals.update(sale_order_line_id=so_line.id, sale_order_origin_id=so_line.order_id.id)
            ui_lines.append(Command.create(vals))
        uid = str(uuid.uuid4())
        session.env["pos.order"].sync_from_ui([{
            "uuid": uid, "name": f"Order {uid}",
            "session_id": session.id, "user_id": session.env.uid,
            "date_order": fields.Datetime.to_string(fields.Datetime.now()),
            "partner_id": cliente.id if cliente else False,
            "fiscal_position_id": False, "pricelist_id": self.config.pricelist_id.id,
            "lines": ui_lines,
            "payment_ids": [Command.create({
                "amount": total if pagado is None else pagado,
                "name": fields.Datetime.now(), "payment_method_id": self.efectivo.id,
            })],
            "amount_paid": total, "amount_total": total, "amount_tax": 0, "amount_return": 0,
            "to_invoice": facturar, "last_order_preparation_change": "{}",
        }])
        return self.env["pos.order"].search([("uuid", "=", uid)])

    def _en(self, product, ubicacion):
        return product.with_context(location=ubicacion.id).qty_available

    def _devolver(self, session, devuelto=None, usuario=None):
        wizard = self.env["helados.devolucion.sobrantes"]._crear_para_sesion(session)
        for linea in wizard.linea_ids:
            if devuelto and linea.product_id in devuelto:
                linea.devuelto = devuelto[linea.product_id]
        (wizard.with_user(usuario) if usuario else wizard).action_confirmar()

    def _cerrar(self, session, contado):
        session.post_closing_cash_details(contado)
        session.update_closing_control_state_session("")
        return session.close_session_from_ui()

    # --- Configuración ---------------------------------------------------------

    def test_un_punto_de_venta_por_vehiculo(self):
        for slug, ubicacion in (
            ("camion", "location_camion"), ("moto_1", "location_moto_1"),
            ("moto_2", "location_moto_2"), ("local", "location_local"),
        ):
            config = self.env.ref(f"helados_pos.pos_config_{slug}")
            self.assertEqual(config.ubicacion_id, self.env.ref(f"helados_base.{ubicacion}"))
            self.assertTrue(config.cash_control)
            self.assertEqual(config.amount_authorized_diff, 5000)
        self.assertTrue(self.config.es_vehiculo)
        self.assertFalse(self.env.ref("helados_pos.pos_config_local").es_vehiculo)
        self.assertTrue(self.konito.available_in_pos)

    # --- Escenario 1: abrir sesión con base de efectivo ------------------------

    def test_e1_abrir_sesion_con_base(self):
        session = self._abrir(50000, usuario=self.repartidor)
        self.assertEqual(session.state, "opened")
        self.assertEqual(session.cash_register_balance_start, 50000)
        self.assertEqual(session.user_id, self.repartidor)
        self.assertEqual(session.config_id.ubicacion_id, self.camion)

    # --- Escenario 2: venta, pago y factura -------------------------------------

    def test_e2_venta_factura_y_descuenta_del_vehiculo(self):
        session = self._abrir()
        orden = self._vender(session, [(self.konito, 3)], cliente=self.cliente, facturar=True)

        self.assertTrue(orden.is_invoiced)
        self.assertEqual(orden.state, "done")
        self.assertEqual(orden.account_move.state, "posted")
        self.assertEqual(orden.account_move.amount_total, 3 * self.konito.lst_price)
        self.assertEqual(sum(orden.payment_ids.mapped("amount")), 3 * self.konito.lst_price)
        self.assertEqual(self._en(self.konito, self.camion), 7)
        self.assertEqual(self._en(self.konito, self.cava), 20)

    def test_e2_cobrar_pedido_a_domicilio_sin_doble_descuento(self):
        """Pedido de la HU03 cargado al camión y cobrado desde el PdV del camión."""
        pedido = self.env["sale.order"].create({
            "partner_id": self.cliente.id, "vehiculo_id": self.camion.id,
            "order_line": [Command.create({"product_id": self.konito.id, "product_uom_qty": 4})],
        })
        pedido.action_confirm()
        cargue = pedido._helados_cargues()
        cargue.move_ids.quantity = 4
        cargue.move_ids.picked = True
        cargue.button_validate()
        self.assertEqual(self._en(self.konito, self.camion), 14)

        session = self._abrir()
        self._vender(session, [(self.konito, 4, pedido.order_line)], cliente=self.cliente, facturar=True)

        self.assertEqual(self._en(self.konito, self.camion), 10)
        self.assertEqual(self._en(self.konito, self.cava), 16)
        self.assertEqual(pedido._helados_entregas().state, "cancel")
        self.assertEqual(pedido.order_line.qty_delivered, 4)

    # --- Escenario 3: devolver sobrantes y cerrar caja --------------------------

    def test_e3_cierre_cuadrado(self):
        session = self._abrir(50000)
        self._vender(session, [(self.konito, 3)])
        self._devolver(session)  # vuelven 7 Konito y 5 Paleta Iris

        self.assertEqual(self._en(self.konito, self.camion), 0)
        self.assertEqual(self._en(self.konito, self.cava), 27)
        self.assertEqual(self._en(self.iris, self.cava), 5)
        self.assertFalse(session.faltante_ids)

        esperado = 50000 + 3 * self.konito.lst_price
        resultado = self._cerrar(session, esperado)
        self.assertTrue(resultado["successful"], resultado)
        self.assertEqual(session.state, "closed")
        self.assertEqual(session.cash_register_difference, 0)

    def test_e3_faltante_de_producto(self):
        session = self._abrir()
        self._vender(session, [(self.konito, 3)])
        self._devolver(session, {self.konito: 5, self.iris: 4})  # faltan 2 Konito y 1 Iris

        self.assertEqual(self._en(self.konito, self.cava), 25)
        self.assertEqual(self._en(self.konito, self.camion), 0)
        self.assertEqual(self._en(self.iris, self.camion), 0)
        faltantes = {f.product_id: f for f in session.faltante_ids}
        self.assertEqual(faltantes[self.konito].cantidad, 2)
        self.assertEqual(faltantes[self.konito].esperado, 7)
        self.assertEqual(faltantes[self.iris].cantidad, 1)
        self.assertEqual(session.faltante_valor, 2 * self.konito.lst_price + self.iris.lst_price)
        self.assertEqual(faltantes[self.konito].repartidor_id, session.user_id)

    def test_e3_no_cierra_sin_devolver_sobrantes(self):
        session = self._abrir()
        self._vender(session, [(self.konito, 3)])
        resultado = session.close_session_from_ui()
        self.assertFalse(resultado["successful"])
        self.assertIn("sobrantes", resultado["message"])
        with self.assertRaises(UserError):
            session.action_pos_session_closing_control()

    def test_e3_no_devuelve_mas_de_lo_esperado(self):
        session = self._abrir()
        with self.assertRaises(UserError):
            self._devolver(session, {self.konito: 11})

    def test_e3_diferencia_de_caja_sobre_el_tope(self):
        """Faltan $10.000 en caja: el repartidor no puede cerrar; el gerente sí, y queda registrada."""
        session = self._abrir(50000, usuario=self.repartidor)
        session = session.with_user(self.repartidor)
        self._vender(session, [(self.konito, 1)])
        self._devolver(session, usuario=self.repartidor)
        esperado = 50000 + self.konito.lst_price

        with self.assertRaises(UserError):
            self._cerrar(session, esperado - 10000)

        session = session.with_user(self.env.ref("base.user_admin"))
        resultado = self._cerrar(session, esperado - 10000)
        self.assertTrue(resultado["successful"], resultado)
        self.assertEqual(session.cash_register_difference, -10000)

    def test_e3_diferencia_menor_al_tope_la_cierra_el_repartidor(self):
        session = self._abrir(50000, usuario=self.repartidor).with_user(self.repartidor)
        self._vender(session, [(self.konito, 1)])
        self._devolver(session, usuario=self.repartidor)
        resultado = self._cerrar(session, 50000 + self.konito.lst_price - 2000)
        self.assertTrue(resultado["successful"], resultado)
        self.assertEqual(session.cash_register_difference, -2000)
